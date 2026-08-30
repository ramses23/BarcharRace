import copy
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pandas as pd
import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config.chart_config import ChartConfig
from config.dataset_config import DatasetConfig
from config.export_config import ExportConfig
from config.layout_config import get_layout_preset, list_layout_presets
from config.project_file_loader import ProjectFileError
from config.theme_config import get_theme
from config.typography_config import get_typography_preset
from config.value_format_config import list_value_formats
from core.fun_fact_scheduler import FunFactScheduleError, FunFactScheduler
from core.scene_geometry import build_scene_geometry
from core.timeline import Timeline
from studio.fun_fact_layout import (
    DEFAULT_FLOATING_CARD_HEIGHT_RATIO,
    DEFAULT_FLOATING_CARD_WIDTH_RATIO,
    DEFAULT_FUN_FACT_PANEL_WIDTH_RATIO,
)
from studio.fun_fact_loader import FunFactFileError, load_fun_fact_collection
from studio.package_paths import (
    ProjectPathError,
    resolve_project_path as resolve_portable_project_path,
)
from studio.preview import render_project_preview
from studio.layout_preview import build_studio_layout_preview
from studio.short_export import resolve_export_output_path, resolve_export_periods
from studio.project_bundle import (
    ProjectBundleError,
    build_project_bundle,
    import_project_bundle,
)
from studio.project_draft import ProjectDraft
from ui.category_editor import (
    CATEGORY_FILTERS,
    CATEGORY_PAGE_SIZES,
    filter_categories,
    paginate_categories,
    update_category_style,
)
from ui.dataset_cache import load_csv_dataset
from ui.bar_style_editor import bar_style_editor
from ui.editorial_layout_editor import (
    editorial_layout_component_state,
    editorial_layout_editor,
    reconcile_editorial_geometry,
)
from ui.font_picker import font_family_picker
from ui.floating_preview import floating_preview_controller
from ui.render_workflow import (
    BACKGROUND_RENDER_STATE,
    LAST_PREFLIGHT_STATE,
    LAST_RENDER_STATUS_STATE,
    render_workflow_panel,
    start_render_with_preflight,
)
from ui.studio_shell import (
    section_intro,
    show_dataset_snapshot,
    show_empty_preview,
    show_studio_header,
    show_welcome_header,
)
from ui.text_layout_editor import (
    text_layout_editor,
    text_layout_editor_positions,
)
from studio.project_builder import (
    BAR_STYLE_FIELDS,
    apply_category_logo_matches,
    build_project_data,
    category_values_from_dataframe,
    default_project_paths,
    inspect_dataframe,
    load_project_data,
    match_category_logos,
    preferred_column,
    project_defaults_from_csv_path,
    project_form_values,
    project_name_from_title,
    save_project_data,
    year_values,
    year_values_from_dataframe,
)
from studio.appearance_presets import (
    AppearancePresetError,
    apply_appearance_preset,
    build_appearance_preset,
    delete_appearance_preset,
    load_appearance_preset_catalog,
    save_appearance_preset,
)
from studio.workspace_paths import (
    AppRootWriteError,
    ProjectLocation,
    WorkspaceLayout,
    WorkspacePathError,
    assert_user_write_path,
    default_workspace_root,
    discover_project_locations,
    find_project_location,
    initialize_workspace,
    load_workspace_settings,
    project_location_from_path,
    safe_slug,
    save_workspace_settings,
)
from utils.file_size import format_file_size
from utils.video_duration import estimate_video_duration, format_video_duration


DEFAULT_CATEGORY_COLORS = (
    "#4E79A7",
    "#F28E2B",
    "#E15759",
    "#76B7B2",
    "#59A14F",
    "#EDC948",
    "#B07AA1",
    "#FF9DA7",
    "#9C755F",
    "#BAB0AC",
)
LOGO_FILE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_LOGO_FOLDER = "assets/logos"
DEFAULT_SECONDARY_LOGO_FOLDER = "assets/logos_secondary"
APPLIED_LOGO_MATCHES_STATE = "applied_logo_matches"
LOGO_FOLDER_OVERRIDE_STATE = "category_logo_folder_override"
APPLIED_SECONDARY_LOGO_MATCHES_STATE = "applied_secondary_logo_matches"
SECONDARY_LOGO_FOLDER_OVERRIDE_STATE = "category_secondary_logo_folder_override"
NEW_PROJECT_CSV_PATH_STATE = "new_project_csv_path"
NEW_PROJECT_CSV_PATH_OVERRIDE_STATE = "new_project_csv_path_override"
CUSTOM_TEXTURE_PATH_STATE = "custom_bar_texture_path"
BACKGROUND_IMAGE_PATH_STATE = "background_image_path"
SAVED_DRAFT_FINGERPRINT_STATE = "saved_project_draft_fingerprint"
SAVED_DRAFT_PENDING_STATE = "saved_project_draft_pending"
LAST_PREVIEW_STATE = "last_project_preview"
AUTO_PREVIEW_ENABLED_STATE = "auto_project_preview_enabled"
AUTO_PREVIEW_OBSERVED_STATE = "auto_project_preview_observed"
CATEGORY_STYLE_DRAFT_STATE = "category_style_draft"
CURRENT_DRAFT_FINGERPRINT_STATE = "current_project_draft_fingerprint"
CURRENT_DRAFT_STATE = "current_project_draft"
PENDING_PROJECT_ACTION_STATE = "pending_project_action"
PROJECT_BUNDLE_EXPORT_STATE = "project_bundle_export"
LAST_BUNDLE_IMPORT_STATE = "last_project_bundle_import"
BUNDLE_IMPORT_UPLOAD_NONCE_STATE = "project_bundle_import_upload_nonce"
PREVIEW_SETTINGS_STATE = "project_preview_settings"
CATEGORY_AREA_SPAN_OVERRIDE_STATE = "category_area_span_override"
APPEARANCE_PRESET_DIR_ENV = "BARCHARTSTUDIO_APPEARANCE_PRESETS_DIR"
APPEARANCE_PRESET_SELECTION_STATE = "appearance_preset_selection"
APPEARANCE_PRESET_NOTICE_STATE = "appearance_preset_notice"
APPEARANCE_PRESET_DELETE_STATE = "appearance_preset_delete"
AUTOLOAD_PROJECT_ENV = "BARCHARTSTUDIO_AUTOLOAD_PROJECT"
AUTOLOAD_TOKEN_ENV = "BARCHARTSTUDIO_AUTOLOAD_TOKEN"
AUTOLOAD_TOKEN_STATE = "autoload_consumed_token"
WORKSPACE_PATH_INPUT_STATE = "workspace_path_input"
WORKSPACE_NOTICE_STATE = "workspace_notice"
LOADED_PROJECT_IDENTIFIER_STATE = "loaded_project_identifier"
ACTIVE_PROJECT_ROOT_STATE = "active_project_root"
ACTIVE_PROJECT_KIND_STATE = "active_project_kind"
NEW_PROJECT_ROOT_STATE = "new_project_root"


st.set_page_config(
    page_title="BarChartStudio",
    page_icon=":material/animated_images:",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "BarChartStudio · Professional bar chart race editor",
    },
)
st.logo(
    ":material/animated_images:",
    icon_image=":material/animated_images:",
    size="large",
)


def main():
    _initialize_studio_state()
    layout = _current_workspace_layout()
    _autoload_requested_project(layout)
    header_slot = st.empty()

    with st.sidebar:
        _workspace_panel(layout)
        _project_source_panel(layout)

        loaded_project_data = st.session_state.get("loaded_project_data")
        loaded_project_path = st.session_state.get("loaded_project_path")
        values = _current_project_form_values(loaded_project_data)

        csv_path = _csv_source_panel(values, loaded_project_data, layout)

    if not csv_path:
        with header_slot.container():
            show_welcome_header()
        _show_empty_workspace()
        return

    _refresh_new_project_form_on_csv_change(csv_path, loaded_project_data)
    values = _project_values_for_csv(values, csv_path, loaded_project_data)
    project_root = _active_project_root(layout, csv_path=csv_path)

    try:
        resolved_csv_path = resolve_portable_project_path(
            csv_path,
            project_root=project_root,
            required=True,
            field_name="data_source.csv_path",
        )
        dataset = load_csv_dataset(str(resolved_csv_path))
        inspection = inspect_dataframe(dataset, path=csv_path)
    except (OSError, ValueError, ProjectPathError, pd.errors.ParserError) as exc:
        st.error(str(exc))
        return

    editor_column, stage_column = st.columns([1.72, 1], gap="large")
    with editor_column:
        section_intro(
            "Project settings",
            "Shape the data, canvas, bars, motion, and export from one workspace.",
            icon="tune",
        )
        project_data, project_file, preview_settings = _project_form(
            csv_path,
            inspection,
            values,
            loaded_project_data,
            loaded_project_path,
            dataset,
        )

    draft = ProjectDraft.create(
        project_data,
        project_file,
        preview_settings,
    )
    _initialize_saved_draft(draft)
    st.session_state[CURRENT_DRAFT_FINGERPRINT_STATE] = draft.fingerprint
    st.session_state[CURRENT_DRAFT_STATE] = {
        "project_data": copy.deepcopy(draft.project_data),
        "project_file": draft.project_file,
    }
    saved_fingerprint = st.session_state.get(SAVED_DRAFT_FINGERPRINT_STATE)
    with header_slot.container():
        show_studio_header(
            project_name=project_data.get("name", "Untitled project"),
            project_file=project_file,
            is_dirty=draft.is_dirty(saved_fingerprint),
            row_count=inspection.row_count,
            column_count=len(inspection.columns),
        )

    with stage_column:
        section_intro(
            "Preview and output",
            "Save, inspect, render, and package the current project.",
            icon="movie_edit",
        )
        _project_actions(draft)
        render_workflow_panel()
        if not _show_persistent_preview(draft):
            show_empty_preview()

        with st.expander(
            "Dataset snapshot",
            icon=":material/table_view:",
        ):
            dataset_config = project_data.get("dataset", {})
            show_dataset_snapshot(
                dataset,
                inspection,
                year_column=dataset_config.get("year_column", ""),
                name_column=dataset_config.get("name_column", ""),
            )

        with st.expander(
            "Generated project JSON",
            icon=":material/data_object:",
        ):
            st.json(project_data, expanded=False)

    floating_preview_controller(key="latest_preview_controller")


def _initialize_studio_state():
    st.session_state.setdefault("form_version", 0)
    st.session_state.setdefault(SAVED_DRAFT_FINGERPRINT_STATE, None)
    st.session_state.setdefault(SAVED_DRAFT_PENDING_STATE, False)
    st.session_state.setdefault(LAST_PREVIEW_STATE, None)
    st.session_state.setdefault(AUTO_PREVIEW_OBSERVED_STATE, None)
    st.session_state.setdefault(CURRENT_DRAFT_FINGERPRINT_STATE, None)
    st.session_state.setdefault(CURRENT_DRAFT_STATE, None)
    st.session_state.setdefault(PENDING_PROJECT_ACTION_STATE, None)
    st.session_state.setdefault(BACKGROUND_RENDER_STATE, None)
    st.session_state.setdefault(LAST_RENDER_STATUS_STATE, None)
    st.session_state.setdefault(LAST_PREFLIGHT_STATE, None)
    st.session_state.setdefault(PROJECT_BUNDLE_EXPORT_STATE, None)
    st.session_state.setdefault(LAST_BUNDLE_IMPORT_STATE, None)
    st.session_state.setdefault(BUNDLE_IMPORT_UPLOAD_NONCE_STATE, 0)
    st.session_state.setdefault(PREVIEW_SETTINGS_STATE, None)
    st.session_state.setdefault(APPEARANCE_PRESET_SELECTION_STATE, None)
    st.session_state.setdefault(APPEARANCE_PRESET_NOTICE_STATE, None)
    st.session_state.setdefault(APPEARANCE_PRESET_DELETE_STATE, None)
    st.session_state.setdefault(AUTOLOAD_TOKEN_STATE, None)
    st.session_state.setdefault(WORKSPACE_NOTICE_STATE, None)
    st.session_state.setdefault(LOADED_PROJECT_IDENTIFIER_STATE, None)
    st.session_state.setdefault(ACTIVE_PROJECT_ROOT_STATE, None)
    st.session_state.setdefault(ACTIVE_PROJECT_KIND_STATE, None)
    st.session_state.setdefault(NEW_PROJECT_ROOT_STATE, None)


def _autoload_requested_project(layout):
    requested_project = os.environ.get(AUTOLOAD_PROJECT_ENV)
    token = os.environ.get(AUTOLOAD_TOKEN_ENV)
    if requested_project is None and token is None:
        return

    token = token or ""
    if st.session_state.get(AUTOLOAD_TOKEN_STATE) == token:
        return
    st.session_state[AUTOLOAD_TOKEN_STATE] = token

    if not token.strip():
        st.error(
            "Auto-load request rejected: the launch token is missing."
        )
        return
    if requested_project is None or not requested_project.strip():
        st.error(
            "Auto-load request rejected: the project path is missing."
        )
        return

    try:
        selected_project = _validated_autoload_project(requested_project, layout)
    except (OSError, ValueError) as exc:
        st.error(f"Auto-load request rejected: {exc}")
        return

    _load_selected_project(selected_project, layout=layout)


def _validated_autoload_project(requested_project, layout):
    location = find_project_location(requested_project, layout)
    return _project_option_value(location, layout)


def _initialize_saved_draft(draft):
    pending = st.session_state.get(SAVED_DRAFT_PENDING_STATE, False)

    if pending:
        st.session_state[SAVED_DRAFT_FINGERPRINT_STATE] = draft.fingerprint
        st.session_state[SAVED_DRAFT_PENDING_STATE] = False


def _show_empty_workspace():
    with st.container(
        border=True,
        horizontal_alignment="center",
        gap="xsmall",
        key="empty_workspace",
    ):
        st.markdown("## :material/folder_open: Start a project")
        st.caption(
            "Use the project library in the sidebar to open a JSON project, "
            "import a portable ZIP, or choose a CSV for a new project."
        )
        st.badge(
            "Project library",
            icon=":material/arrow_back:",
            color="primary",
        )


def _project_actions(draft):
    background_render = st.session_state.get(BACKGROUND_RENDER_STATE)
    render_active = bool(
        background_render is not None and background_render.is_running()
    )
    with st.container(border=True, gap="xsmall", key="project_actions"):
        st.caption("Project actions")
        action_row = st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
            gap="xsmall",
        )
        save_project = action_row.button(
            "Save project",
            icon=":material/save:",
            width="content",
            help="Save the current project JSON.",
        )
        render_preview = action_row.button(
            "Render preview",
            icon=":material/visibility:",
            width="content",
            help="Render the selected preview frame.",
        )
        render_video = action_row.button(
            "Render video",
            icon=":material/movie:",
            type="primary",
            width="content",
            disabled=render_active,
            help="Render the final MP4 in an isolated process.",
        )
        auto_preview = st.toggle(
            "Auto preview",
            value=True,
            key=AUTO_PREVIEW_ENABLED_STATE,
            help=(
                "Automatically update the preview after changes in Canvas, "
                "Bars, Fun facts, categories, or the selected preview frame."
            ),
        )
        st.caption(
            "Auto preview watches visual settings only. Changes in Data or "
            "Export can still be reviewed with Render preview."
        )

    if save_project:
        _save_draft(draft)

    if render_preview:
        preview_path = _render_preview(
            draft.project_file,
            draft.preview_settings,
            project_data=draft.project_data,
        )

        if preview_path is not None:
            _store_preview(draft, preview_path, automatic=False)

    auto_render_preview = _should_auto_render_preview(
        draft,
        enabled=(
            auto_preview
            and not render_preview
            and not render_active
        ),
    )
    if auto_render_preview:
        with st.spinner("Updating preview..."):
            preview_path = _render_preview(
                draft.project_file,
                draft.preview_settings,
                project_data=draft.project_data,
            )

        if preview_path is not None:
            _store_preview(draft, preview_path, automatic=True)

    if render_video:
        saved_path = _save_draft(draft, show_success=False)
        if saved_path is not None:
            layout = _current_workspace_layout()
            project_root = _active_project_root(layout)
            start_render_with_preflight(
                saved_path,
                project_root=project_root,
                output_root=project_root,
                app_root=layout.app_root,
                job_root=layout.cache_root / "render_jobs",
            )

    saved_fingerprint = st.session_state.get(SAVED_DRAFT_FINGERPRINT_STATE)
    if draft.is_dirty(saved_fingerprint):
        st.caption(":orange-badge[Unsaved changes] Save before closing the app.")
    else:
        st.caption(f":green-badge[Saved] {draft.project_file}")

    _portable_bundle_export_panel(draft, render_active=render_active)


def _should_auto_render_preview(draft, *, enabled):
    previous_fingerprint = st.session_state.get(
        AUTO_PREVIEW_OBSERVED_STATE
    )
    if previous_fingerprint is None:
        st.session_state[AUTO_PREVIEW_OBSERVED_STATE] = (
            draft.auto_preview_fingerprint
        )
        return False

    if not enabled:
        return False

    st.session_state[AUTO_PREVIEW_OBSERVED_STATE] = (
        draft.auto_preview_fingerprint
    )
    return bool(
        previous_fingerprint != draft.auto_preview_fingerprint
    )


def _store_preview(draft, preview_path, *, automatic):
    st.session_state[AUTO_PREVIEW_OBSERVED_STATE] = (
        draft.auto_preview_fingerprint
    )
    st.session_state[LAST_PREVIEW_STATE] = {
        "path": str(preview_path),
        "fingerprint": draft.fingerprint,
        "preview_fingerprint": draft.preview_fingerprint,
        "auto_preview_fingerprint": draft.auto_preview_fingerprint,
        "automatic": bool(automatic),
    }


def _portable_bundle_export_panel(draft, *, render_active):
    with st.expander(
        "Portable project bundle",
        icon=":material/folder_zip:",
    ):
        st.caption(
            "Package the project JSON, dataset, background, custom texture, "
            "and both logo slots into one verified ZIP."
        )
        if st.button(
            "Prepare portable ZIP",
            icon=":material/folder_zip:",
            width="stretch",
            disabled=render_active,
            key="prepare_project_bundle",
        ):
            saved_path = _save_draft(draft, show_success=False)
            if saved_path is None:
                return
            bundle_project_data = st.session_state.get(
                "loaded_project_data",
                draft.project_data,
            )
            try:
                with st.spinner("Collecting project files..."):
                    exported = build_project_bundle(
                        bundle_project_data,
                        root_dir=_active_project_root(
                            _current_workspace_layout()
                        ),
                    )
            except (OSError, ValueError, ProjectBundleError) as exc:
                st.session_state[PROJECT_BUNDLE_EXPORT_STATE] = None
                st.error(str(exc))
            else:
                st.session_state[PROJECT_BUNDLE_EXPORT_STATE] = {
                    "fingerprint": draft.fingerprint,
                    "data": exported.data,
                    "filename": exported.filename,
                    "file_count": exported.file_count,
                    "uncompressed_size": exported.uncompressed_size,
                }

        prepared = st.session_state.get(PROJECT_BUNDLE_EXPORT_STATE)
        if not isinstance(prepared, dict):
            return
        if prepared.get("fingerprint") != draft.fingerprint:
            st.info(
                "The prepared ZIP is out of date. Prepare it again to include "
                "the current project settings."
            )
            return

        st.caption(
            f"{prepared.get('file_count', 0):,} files · "
            f"{format_file_size(prepared.get('uncompressed_size', 0))} unpacked"
        )
        st.download_button(
            "Download portable ZIP",
            data=prepared["data"],
            file_name=prepared["filename"],
            mime="application/zip",
            icon=":material/download:",
            width="stretch",
            on_click="ignore",
        )


def _show_persistent_preview(draft):
    preview = st.session_state.get(LAST_PREVIEW_STATE)

    if not isinstance(preview, dict):
        return False

    preview_path = Path(str(preview.get("path", "")))

    if not preview_path.is_file():
        st.session_state[LAST_PREVIEW_STATE] = None
        return False

    with st.container(border=True, gap="xsmall", key="latest_preview"):
        st.subheader(":material/preview: Latest preview")

        preview_fingerprint = preview.get("preview_fingerprint")
        if preview_fingerprint is None:
            preview_is_outdated = (
                preview.get("fingerprint") != draft.fingerprint
            )
        else:
            preview_is_outdated = (
                preview_fingerprint != draft.preview_fingerprint
            )

        if preview_is_outdated:
            st.warning(
                "This preview is out of date. Render it again to include "
                "changes outside the automatic visual update scope.",
                icon=":material/update:",
            )

        st.image(str(preview_path), width="stretch")

    return True


def _current_workspace_layout():
    try:
        settings = load_workspace_settings(app_root=ROOT_DIR)
        workspace_root = settings.workspace_root
    except (OSError, WorkspacePathError) as exc:
        st.error(f"Workspace settings could not be loaded: {exc}")
        workspace_root = default_workspace_root(ROOT_DIR)
    return WorkspaceLayout(
        app_root=ROOT_DIR.resolve(),
        workspace_root=workspace_root.resolve(strict=False),
    )


def _workspace_panel(layout):
    with st.expander(
        "Workspace",
        icon=":material/workspaces:",
        expanded=True,
    ):
        st.caption("Current workspace")
        st.code(str(layout.workspace_root), language=None)
        workspace_value = st.text_input(
            "Workspace path",
            value=str(layout.workspace_root),
            key=WORKSPACE_PATH_INPUT_STATE,
            help="Use an absolute path outside the BarChartStudio repository.",
        )
        action_row = st.container(
            horizontal=True,
            horizontal_alignment="left",
            gap="xsmall",
        )
        change_workspace = action_row.button(
            "Change workspace",
            icon=":material/drive_file_move:",
            width="content",
            key="change_workspace",
        )
        initialize = action_row.button(
            "Initialize workspace",
            icon=":material/create_new_folder:",
            width="content",
            key="initialize_workspace",
        )
        open_folder = st.button(
            "Open workspace folder",
            icon=":material/folder_open:",
            width="content",
            disabled=not layout.workspace_root.is_dir(),
            key="open_workspace_folder",
        )
        try:
            preferences = load_workspace_settings(app_root=ROOT_DIR)
            preference_enabled = preferences.render_cpu_limit_enabled
            preference_percent = preferences.render_cpu_limit_percent
        except (OSError, WorkspacePathError):
            preference_enabled = True
            preference_percent = 95
        st.divider()
        performance_panel = st.container(border=True)
        performance_panel.markdown("**Render performance**")
        performance_panel.caption("Application-level preference for every render job.")
        cpu_enabled = performance_panel.toggle(
            "Use a soft CPU ceiling",
            value=preference_enabled,
            help="Cooperatively yields between frames and limits FFmpeg threads.",
            key="render_cpu_limit_enabled",
        )
        cpu_percent = performance_panel.slider(
            "CPU ceiling",
            min_value=50,
            max_value=100,
            value=preference_percent,
            step=1,
            format="%d%%",
            help="100% disables limiting.",
            key="render_cpu_limit_percent",
        )
        save_performance = performance_panel.button(
            "Save render preference",
            icon=":material/save:",
            key="save_render_cpu_preference",
        )

        if save_performance:
            save_workspace_settings(
                layout.workspace_root,
                app_root=ROOT_DIR,
                render_cpu_limit_enabled=cpu_enabled,
                render_cpu_limit_percent=cpu_percent,
            )
            st.success("Render preference saved for this application.")

        if change_workspace or initialize:
            try:
                saved = save_workspace_settings(
                    workspace_value,
                    app_root=ROOT_DIR,
                )
                if initialize:
                    initialize_workspace(
                        saved.workspace_root,
                        app_root=ROOT_DIR,
                    )
            except (OSError, WorkspacePathError) as exc:
                st.error(str(exc))
            else:
                st.session_state[WORKSPACE_NOTICE_STATE] = (
                    "Workspace initialized."
                    if initialize
                    else "Workspace changed."
                )
                _reset_workspace_project_state()
                st.rerun()

        if open_folder:
            try:
                _open_workspace_folder(layout.workspace_root)
            except OSError as exc:
                st.error(f"Could not open the workspace folder: {exc}")

        notice = st.session_state.pop(WORKSPACE_NOTICE_STATE, None)
        if notice:
            st.success(notice)
        if not layout.workspace_root.exists():
            st.info("Initialize this workspace before creating user content.")


def _project_source_panel(layout):
    st.caption("My projects and productions")
    st.subheader(":material/folder_open: Project library")
    _pending_project_action_panel()
    project_locations = discover_project_locations(layout)
    project_files = tuple(
        _project_option_value(location, layout)
        for location in project_locations
    )
    project_labels = _project_display_labels(project_locations, layout)
    project_options = ("", *project_files)
    current_project = st.session_state.get(LOADED_PROJECT_IDENTIFIER_STATE, "")
    selected_project = st.selectbox(
        "Open project",
        project_options,
        index=_option_index(project_options, current_project),
        format_func=lambda path: project_labels.get(path, "New project"),
    )
    if selected_project:
        try:
            selected_location = find_project_location(selected_project, layout)
        except WorkspacePathError:
            selected_location = None
        if selected_location is not None:
            with st.container(border=True):
                st.caption("Selected project")
                st.markdown(f"**{selected_location.absolute_path.stem}**")
                st.caption("Location")
                st.markdown(selected_location.kind.title())
                st.caption("Path")
                st.code(selected_project, language=None)
    background_render = st.session_state.get(BACKGROUND_RENDER_STATE)
    render_active = bool(
        background_render is not None and background_render.is_running()
    )

    project_action_row = st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        gap="xsmall",
    )
    if project_action_row.button(
        "Load project",
        icon=":material/folder_open:",
        width="content",
        disabled=not selected_project or render_active,
    ):
        _request_project_action("load", project=selected_project)

    if project_action_row.button(
        "New project",
        icon=":material/note_add:",
        width="content",
        disabled=render_active,
    ):
        _request_project_action("new")

    if render_active:
        st.caption("Project switching is disabled while a render is active.")

    if st.session_state.get("loaded_project_path"):
        st.badge(
            "Project loaded",
            icon=":material/edit_document:",
            color="green",
        )
        kind = st.session_state.get(ACTIVE_PROJECT_KIND_STATE, "project")
        st.caption(
            f"{kind.title()} · "
            f"{st.session_state.get(LOADED_PROJECT_IDENTIFIER_STATE, '')}"
        )

    _portable_bundle_import_panel(render_active=render_active)


def _portable_bundle_import_panel(*, render_active):
    with st.expander(
        "Import production package",
        icon=":material/unarchive:",
        expanded=False,
        type="compact",
    ):
        imported = st.session_state.get(LAST_BUNDLE_IMPORT_STATE)
        if isinstance(imported, dict):
            st.success(
                f"Imported project {imported.get('name', 'project bundle')}",
                icon=":material/inventory_2:",
            )
            st.caption(
                f"Editable project: `{imported.get('project', '')}` · "
                f"{imported.get('files', 0):,} verified files · "
                f"{format_file_size(imported.get('uncompressed_size', 0))} unpacked"
            )

        source = st.segmented_control(
            "Package source",
            options=("ZIP file", "Local folder"),
            default="ZIP file",
            key="project_bundle_import_source",
            width="stretch",
        )
        uploaded = None
        folder_path = ""
        with st.form(
            "project_bundle_import_form",
            clear_on_submit=False,
            border=False,
        ):
            if source == "Local folder":
                folder_path = st.text_input(
                    "Production folder path",
                    key=_widget_key("project_bundle_folder_path"),
                    help=(
                        "Local path to an extracted production package. "
                        "The source folder is never modified."
                    ),
                )
            else:
                upload_nonce = st.session_state.get(
                    BUNDLE_IMPORT_UPLOAD_NONCE_STATE,
                    0,
                )
                uploaded = st.file_uploader(
                    "Project bundle",
                    type=["zip"],
                    help="Select a .barchart.zip file exported by BarChartStudio.",
                    key=f"project_bundle_upload_{upload_nonce}",
                )
            submitted = st.form_submit_button(
                "Import and open",
                icon=":material/unarchive:",
                width="stretch",
                disabled=render_active,
            )

        if not submitted:
            return
        if source == "Local folder":
            folder_path = folder_path.strip()
            if not folder_path:
                st.error("Enter a local production folder path.")
                return
            _request_project_action(
                "import_bundle",
                bundle=Path(folder_path),
                filename=folder_path,
            )
            return
        if uploaded is None:
            st.error("Select a production package ZIP.")
            return
        _request_project_action(
            "import_bundle",
            bundle=uploaded.getvalue(),
            filename=uploaded.name,
        )


def _request_project_action(action, **payload):
    if _has_unsaved_draft():
        st.session_state[PENDING_PROJECT_ACTION_STATE] = {
            "action": action,
            "draft": copy.deepcopy(
                st.session_state.get(CURRENT_DRAFT_STATE)
            ),
            **payload,
        }
        st.rerun()

    _execute_project_action({"action": action, **payload})


def _pending_project_action_panel():
    pending_action = st.session_state.get(PENDING_PROJECT_ACTION_STATE)
    if not isinstance(pending_action, dict):
        return

    _pending_project_action_dialog()


@st.dialog(
    "Unsaved changes",
    icon=":material/warning:",
    dismissible=False,
)
def _pending_project_action_dialog():
    pending_action = st.session_state.get(PENDING_PROJECT_ACTION_STATE)
    if not isinstance(pending_action, dict):
        return

    st.warning(
        "You have unsaved changes in the current draft. "
        "Discard them to continue, or return to the editor.",
        icon=":material/edit_note:",
    )
    action_row = st.container(
        horizontal=True,
        horizontal_alignment="right",
        gap="xsmall",
    )
    if action_row.button(
        "Discard & continue",
        type="primary",
        width="content",
        key="discard_pending_project_action",
    ):
        st.session_state[PENDING_PROJECT_ACTION_STATE] = None
        _execute_project_action(pending_action)

    if action_row.button(
        "Keep editing",
        width="content",
        key="cancel_pending_project_action",
    ):
        current_draft = pending_action.get("draft")
        if isinstance(current_draft, dict) and isinstance(
            current_draft.get("project_data"),
            dict,
        ):
            restored_draft = copy.deepcopy(current_draft)
            st.session_state["loaded_project_data"] = copy.deepcopy(
                restored_draft["project_data"]
            )
            st.session_state[CURRENT_DRAFT_STATE] = restored_draft
            st.session_state[SAVED_DRAFT_PENDING_STATE] = False

        if pending_action.get("action") == "change_csv":
            previous_csv = pending_action.get("previous_csv", "")
            st.session_state[_widget_key("csv_path")] = previous_csv
            st.session_state[_widget_key("csv_upload")] = None
            st.session_state[NEW_PROJECT_CSV_PATH_OVERRIDE_STATE] = previous_csv

        st.session_state[PENDING_PROJECT_ACTION_STATE] = None
        _refresh_form()
        st.rerun()


def _execute_project_action(action):
    action_name = action.get("action")
    if action_name == "load":
        _load_selected_project(action.get("project", ""))
    elif action_name == "new":
        _start_new_project()
    elif action_name == "change_csv":
        _apply_new_project_csv_change(action.get("csv_path", ""))
    elif action_name == "import_bundle":
        _import_project_bundle_action(
            action.get("bundle", b""),
            filename=action.get("filename", "project bundle"),
        )


def _import_project_bundle_action(bundle, *, filename):
    layout = _current_workspace_layout()
    try:
        imported = import_project_bundle(
            bundle,
            workspace_root=layout.workspace_root,
            app_root=layout.app_root,
        )
    except (OSError, ValueError, ProjectBundleError) as exc:
        st.error(f"Could not import {filename}: {exc}")
        return

    try:
        location = project_location_from_path(imported.project_path, layout)
    except (OSError, WorkspacePathError) as exc:
        st.error(f"Imported project could not be located: {exc}")
        return
    project_path = _project_option_value(location, layout)
    st.session_state[LAST_BUNDLE_IMPORT_STATE] = {
        "name": Path(project_path).stem,
        "project": project_path,
        "files": imported.file_count,
        "uncompressed_size": imported.uncompressed_size,
    }
    st.session_state[BUNDLE_IMPORT_UPLOAD_NONCE_STATE] = (
        st.session_state.get(BUNDLE_IMPORT_UPLOAD_NONCE_STATE, 0) + 1
    )
    _load_selected_project(
        project_path,
        preserve_bundle_import=True,
        layout=layout,
    )


def _load_selected_project(
    selected_project,
    *,
    preserve_bundle_import=False,
    layout=None,
):
    layout = layout or _current_workspace_layout()
    try:
        location = find_project_location(selected_project, layout)
        project_data = load_project_data(location.absolute_path)
    except (OSError, ValueError, WorkspacePathError) as exc:
        st.error(str(exc))
        return

    st.session_state["loaded_project_data"] = project_data
    st.session_state["loaded_project_path"] = location.relative_path
    st.session_state[LOADED_PROJECT_IDENTIFIER_STATE] = _project_option_value(
        location,
        layout,
    )
    st.session_state[ACTIVE_PROJECT_ROOT_STATE] = str(location.project_root)
    st.session_state[ACTIVE_PROJECT_KIND_STATE] = location.kind
    st.session_state[NEW_PROJECT_ROOT_STATE] = None
    st.session_state[SAVED_DRAFT_FINGERPRINT_STATE] = None
    st.session_state[SAVED_DRAFT_PENDING_STATE] = True
    if not preserve_bundle_import:
        st.session_state[LAST_BUNDLE_IMPORT_STATE] = None
    _reset_project_editor_state()
    st.session_state.pop(NEW_PROJECT_CSV_PATH_STATE, None)
    st.session_state.pop(NEW_PROJECT_CSV_PATH_OVERRIDE_STATE, None)
    _refresh_form()
    st.rerun()


def _start_new_project():
    st.session_state.pop("loaded_project_data", None)
    st.session_state.pop("loaded_project_path", None)
    st.session_state[LOADED_PROJECT_IDENTIFIER_STATE] = None
    st.session_state[ACTIVE_PROJECT_ROOT_STATE] = None
    st.session_state[ACTIVE_PROJECT_KIND_STATE] = "scratch"
    st.session_state[NEW_PROJECT_ROOT_STATE] = None
    st.session_state[SAVED_DRAFT_FINGERPRINT_STATE] = None
    st.session_state[SAVED_DRAFT_PENDING_STATE] = False
    st.session_state[LAST_BUNDLE_IMPORT_STATE] = None
    _reset_project_editor_state()
    st.session_state.pop(NEW_PROJECT_CSV_PATH_STATE, None)
    st.session_state.pop(NEW_PROJECT_CSV_PATH_OVERRIDE_STATE, None)
    _refresh_form()
    st.rerun()


def _reset_project_editor_state():
    st.session_state[CURRENT_DRAFT_FINGERPRINT_STATE] = None
    st.session_state[CURRENT_DRAFT_STATE] = None
    st.session_state[LAST_PREVIEW_STATE] = None
    st.session_state[AUTO_PREVIEW_OBSERVED_STATE] = None
    st.session_state[LAST_PREFLIGHT_STATE] = None
    st.session_state[LAST_RENDER_STATUS_STATE] = None
    st.session_state[PROJECT_BUNDLE_EXPORT_STATE] = None
    st.session_state[PREVIEW_SETTINGS_STATE] = None
    st.session_state.pop(CATEGORY_STYLE_DRAFT_STATE, None)
    _clear_logo_session_overrides()


def _has_unsaved_draft():
    current_fingerprint = st.session_state.get(CURRENT_DRAFT_FINGERPRINT_STATE)
    saved_fingerprint = st.session_state.get(SAVED_DRAFT_FINGERPRINT_STATE)
    return bool(
        current_fingerprint
        and current_fingerprint != saved_fingerprint
    )


def _csv_source_panel(values, loaded_project_data, layout):
    st.subheader(":material/database: Dataset source")
    uploaded_file = st.file_uploader(
        "CSV file",
        type=["csv"],
        key=_widget_key("csv_upload"),
    )
    default_csv = values["csv_path"]

    if not loaded_project_data:
        default_csv = st.session_state.get(
            NEW_PROJECT_CSV_PATH_OVERRIDE_STATE,
            default_csv,
        )

    if uploaded_file is not None:
        project_root = _writable_project_root(
            layout,
            hint=Path(uploaded_file.name).stem,
        )
        datasets_dir = assert_user_write_path(
            project_root / "data",
            app_root=layout.app_root,
            workspace_root=layout.workspace_root,
            operation="Dataset upload",
        )
        datasets_dir.mkdir(parents=True, exist_ok=True)
        filename = (
            f"{_safe_filename_key(Path(uploaded_file.name).stem) or 'dataset'}.csv"
        )
        csv_path = datasets_dir / filename
        csv_path.write_bytes(uploaded_file.getbuffer())
        csv_path = csv_path.relative_to(project_root).as_posix()

        if not loaded_project_data:
            st.session_state[NEW_PROJECT_CSV_PATH_OVERRIDE_STATE] = csv_path

        return csv_path

    csv_path = st.text_input(
        "CSV path",
        value=default_csv,
        key=_widget_key("csv_path"),
        help="Path relative to the active production or scratch project root.",
    )
    st.caption("CSV uploads are copied into the active project `data/` folder.")
    return csv_path


def _current_project_form_values(loaded_project_data):
    current_draft = st.session_state.get(CURRENT_DRAFT_STATE)
    if isinstance(current_draft, dict) and isinstance(
        current_draft.get("project_data"),
        dict,
    ):
        return project_form_values(current_draft["project_data"])

    return project_form_values(loaded_project_data)


def _project_form(
    csv_path,
    inspection,
    values,
    loaded_project_data,
    loaded_project_path,
    dataset,
):
    _appearance_presets_panel(
        loaded_project_data=loaded_project_data,
        loaded_project_path=loaded_project_path,
    )
    theme, theme_settings = _resolved_theme(values)
    typography_preset, typography_settings = _resolved_typography(values)
    active_section = st.segmented_control(
        "Editor section",
        options=("Data", "Canvas", "Bars", "Fun facts", "Export"),
        default="Data",
        key="studio_editor_section",
        label_visibility="collapsed",
        width="stretch",
    ) or "Data"

    data_settings = _data_settings_from_values(
        inspection,
        values,
        dataset,
    )
    if active_section == "Data":
        data_settings = _data_content_section(
            csv_path,
            inspection,
            values,
            dataset,
        )

    paths = default_project_paths(data_settings["project_name"])
    canvas_settings = _canvas_settings_from_values(
        values,
        theme_settings=theme_settings,
        typography_settings=typography_settings,
    )
    if active_section == "Canvas":
        canvas_settings = _canvas_text_section(
            values=values,
            title=data_settings["title"],
            source_label=data_settings["source_label"],
            theme_settings=theme_settings,
            typography_settings=typography_settings,
        )

    bars_settings = _bars_settings_from_values(values)
    if active_section == "Bars":
        bars_settings = _bars_categories_section(
            csv_path=csv_path,
            name_column=data_settings["name_column"],
            values=values,
            theme_settings=theme_settings,
            background_color=canvas_settings["background"]["color"],
            dataset=dataset,
        )

    fun_fact_settings = _fun_fact_settings_from_values(
        values,
        layout_preset=canvas_settings["layout_preset"],
    )
    if active_section == "Fun facts":
        fun_fact_settings = _fun_facts_section(
            values=values,
            dataset=dataset,
            data_settings=data_settings,
            layout_preset=canvas_settings["layout_preset"],
        )

    render_settings = _render_settings_from_values(
        values,
        paths=paths,
        loaded_project_path=loaded_project_path,
        available_years=data_settings["available_years"],
    )
    if active_section == "Export":
        render_settings = _animation_output_section(
            csv_path=csv_path,
            year_column=data_settings["year_column"],
            available_years=data_settings["available_years"],
            values=values,
            paths=paths,
            loaded_project_path=loaded_project_path,
        )

    project_data = build_project_data(
        name=data_settings["project_name"],
        csv_path=csv_path,
        year_column=data_settings["year_column"],
        name_column=data_settings["name_column"],
        value_column=data_settings["value_column"],
        title=data_settings["title"],
        source_label=data_settings["source_label"],
        output_file=render_settings["output_file"],
        frames_dir=render_settings["frames_dir"],
        layout_preset=canvas_settings["layout_preset"],
        theme=theme,
        background_mode=canvas_settings["background"]["mode"],
        background_color_override=canvas_settings["background"]["color"],
        background_image_path=canvas_settings["background"]["image_path"],
        background_image_fit=canvas_settings["background"]["image_fit"],
        background_motion=canvas_settings["background"]["motion"],
        background_motion_speed=canvas_settings["background"]["motion_speed"],
        background_motion_intensity=canvas_settings["background"]["motion_intensity"],
        value_grid_enabled=canvas_settings["value_axis"]["enabled"],
        value_grid_mode=canvas_settings["value_axis"]["mode"],
        value_grid_tick_labels_enabled=canvas_settings["value_axis"]["show_labels"],
        value_grid_tick_value_format=(
            canvas_settings["value_axis"]["tick_value_format"]
        ),
        value_grid_line_color=canvas_settings["value_axis"]["line_color"],
        value_grid_line_opacity=canvas_settings["value_axis"]["line_opacity"],
        value_grid_line_thickness=canvas_settings["value_axis"]["line_thickness"],
        value_grid_tick_text_color=canvas_settings["value_axis"]["text_color"],
        value_grid_tick_text_opacity=canvas_settings["value_axis"]["text_opacity"],
        value_grid_tick_font_size=canvas_settings["value_axis"]["font_size"],
        value_grid_tick_font_weight=canvas_settings["value_axis"]["font_weight"],
        value_grid_tick_font_style=canvas_settings["value_axis"]["font_style"],
        value_grid_target_tick_count=canvas_settings["value_axis"]["target_tick_count"],
        typography_preset=typography_preset,
        value_format=bars_settings["value_format"],
        fps=render_settings["fps"],
        steps_per_transition=render_settings["steps"],
        top_n=bars_settings["top_n"],
        max_visible_bars=canvas_settings["max_visible"],
        bar_vertical_layout_mode=canvas_settings["bar_vertical_layout_mode"],
        bar_vertical_top_padding=canvas_settings["bar_vertical_top_padding"],
        bar_vertical_bottom_padding=canvas_settings["bar_vertical_bottom_padding"],
        bar_gap=bars_settings["bar_gap"],
        bar_color_source=bars_settings["bar_color_source"],
        primary_logo_min_size=bars_settings["primary_logo_min_size"],
        png_compress_level=render_settings["png_compress_level"],
        frame_output_mode=render_settings["frame_output_mode"],
        motion_mode=render_settings["motion_mode"],
        bar_style=bars_settings["bar_style"],
        title_font_family=canvas_settings["title_font_family"],
        subtitle_font_family=canvas_settings["subtitle_font_family"],
        label_font_family=canvas_settings["label_font_family"],
        value_font_family=canvas_settings["value_font_family"],
        time_label_font_family=canvas_settings["time_label_font_family"],
        source_font_family=canvas_settings["source_font_family"],
        rank_label_font_family=canvas_settings["rank_label_font_family"],
        title_text_color=canvas_settings["title_text_color"],
        title_text_opacity=canvas_settings["title_text_opacity"],
        subtitle_text_color=canvas_settings["subtitle_text_color"],
        subtitle_text_opacity=canvas_settings["subtitle_text_opacity"],
        label_text_color=bars_settings["label_text_color"],
        label_text_opacity=bars_settings["label_text_opacity"],
        value_text_color=bars_settings["value_text_color"],
        value_text_opacity=bars_settings["value_text_opacity"],
        time_label_text_color=canvas_settings["time_label_text_color"],
        time_label_opacity=canvas_settings["time_label_opacity"],
        source_text_color=canvas_settings["source_text_color"],
        source_text_opacity=canvas_settings["source_text_opacity"],
        rank_label_text_color=bars_settings["rank_label_text_color"],
        rank_label_text_opacity=bars_settings["rank_label_text_opacity"],
        title_font_size=canvas_settings["title_font_size"],
        subtitle_font_size=canvas_settings["subtitle_font_size"],
        label_font_size=canvas_settings["label_font_size"],
        value_font_size=canvas_settings["value_font_size"],
        time_label_font_size=canvas_settings["time_label_font_size"],
        source_font_size=canvas_settings["source_font_size"],
        rank_label_font_size=canvas_settings["rank_label_font_size"],
        text_styles=canvas_settings["text_styles"],
        title_enabled=canvas_settings["title_enabled"],
        subtitle_enabled=canvas_settings["subtitle_enabled"],
        time_label_enabled=canvas_settings["time_label_enabled"],
        source_label_enabled=canvas_settings["source_label_enabled"],
        rank_labels_enabled=canvas_settings["rank_labels_enabled"],
        category_labels_enabled=canvas_settings["category_labels_enabled"],
        value_labels_enabled=canvas_settings["value_labels_enabled"],
        title_x=canvas_settings["title_x"],
        title_y=canvas_settings["title_y"],
        subtitle_x=canvas_settings["subtitle_x"],
        subtitle_y=canvas_settings["subtitle_y"],
        time_label_x=canvas_settings["time_label_x"],
        time_label_y=canvas_settings["time_label_y"],
        source_x=canvas_settings["source_x"],
        source_y=canvas_settings["source_y"],
        label_min_x=canvas_settings["label_min_x"],
        left_margin=canvas_settings["left_margin"],
        rank_label_gap=canvas_settings["rank_label_gap"],
        aggregate_other=bars_settings["aggregate_other"],
        category_styles=bars_settings["category_styles"],
        fun_facts={
            key: value
            for key, value in fun_fact_settings.items()
            if not key.startswith("_")
        },
        export_settings=render_settings["export"],
        time_label_column=data_settings.get("time_label_column"),
        base_project_data=loaded_project_data,
    )

    if active_section == "Canvas":
        _mount_text_layout_editor(
            project_data=project_data,
            dataset=dataset,
            preview_settings=render_settings["preview_settings"],
            canvas_settings=canvas_settings,
        )
    if active_section == "Fun facts":
        _mount_editorial_layout_editor(
            project_data=project_data,
            dataset=dataset,
            preview_settings=render_settings["preview_settings"],
            fun_fact_settings=fun_fact_settings,
        )

    return (
        project_data,
        render_settings["project_file"],
        render_settings["preview_settings"],
    )


def _appearance_presets_panel(*, loaded_project_data, loaded_project_path):
    directory = _appearance_preset_directory()
    catalog = load_appearance_preset_catalog(directory)
    presets_by_name = {
        preset.name.casefold(): preset
        for preset in catalog.presets
    }
    options = tuple(preset.name for preset in catalog.presets)
    selection_key = _widget_key("appearance_preset")
    selection_override = st.session_state.pop(
        APPEARANCE_PRESET_SELECTION_STATE,
        None,
    )

    if selection_override is not None:
        st.session_state.pop(selection_key, None)

    selected_index = (
        options.index(selection_override)
        if selection_override in options
        else None
    )

    with st.expander(
        "Appearance presets",
        icon=":material/style:",
    ):
        st.caption(
            "Reuse Canvas, Bars, and Fun Facts styling without copying project "
            "data, categories, Fun Fact content, animation, or export paths. "
            "Applying a preset changes the current draft; Save project remains "
            "explicit."
        )

        notice = st.session_state.pop(APPEARANCE_PRESET_NOTICE_STATE, None)
        if isinstance(notice, tuple) and len(notice) == 2:
            level, message = notice
            if level == "success":
                st.success(message, icon=":material/check_circle:")
            else:
                st.info(message, icon=":material/info:")

        for error in catalog.errors:
            st.warning(error, icon=":material/warning:")

        selected_name = st.selectbox(
            "Saved appearance preset",
            options=options,
            index=selected_index,
            placeholder="Select a saved preset",
            key=selection_key,
            help=(
                "Choose an existing preset to apply, update, or delete."
            ),
        )
        selected_name = str(selected_name or "").strip()
        selected_preset = presets_by_name.get(selected_name.casefold())
        current_project_data, current_project_file = _appearance_preset_target(
            loaded_project_data,
            loaded_project_path,
        )

        with st.container(
            horizontal=True,
            vertical_alignment="bottom",
            gap="small",
        ):
            apply_clicked = st.button(
                "Apply preset",
                icon=":material/check:",
                type="primary",
                disabled=(
                    selected_preset is None
                    or current_project_data is None
                ),
                key=_widget_key("apply_appearance_preset"),
            )
            update_clicked = st.button(
                "Update preset",
                icon=":material/save:",
                disabled=(
                    selected_preset is None
                    or current_project_data is None
                ),
                key=_widget_key("update_appearance_preset"),
            )
            delete_clicked = st.button(
                "Delete preset",
                icon=":material/delete:",
                disabled=selected_preset is None,
                key=_widget_key("delete_appearance_preset"),
            )

        st.caption(
            "Save the current Canvas, Bars, and Fun Facts appearance as a new preset."
        )
        new_preset_name = st.text_input(
            "New preset name",
            placeholder="For example: Dark documentary",
            key=_widget_key("new_appearance_preset_name"),
        ).strip()
        new_name_conflict = presets_by_name.get(new_preset_name.casefold())
        save_new_clicked = st.button(
            "Save new preset",
            icon=":material/add:",
            disabled=(
                not new_preset_name
                or new_name_conflict is not None
                or current_project_data is None
            ),
            key=_widget_key("save_new_appearance_preset"),
            help=(
                "Choose a different name if the preset already exists; use "
                "Update preset to replace a selected preset."
            ),
        )
        if new_preset_name and new_name_conflict is not None:
            st.caption(
                ":orange-badge[Name already exists] Select it above and use "
                "Update preset."
            )

        if apply_clicked:
            try:
                updated_project = apply_appearance_preset(
                    current_project_data,
                    selected_preset,
                )
            except AppearancePresetError as exc:
                st.error(str(exc), icon=":material/error:")
            else:
                st.session_state[CURRENT_DRAFT_STATE] = {
                    "project_data": updated_project,
                    "project_file": current_project_file,
                }
                _sync_appearance_asset_overrides(selected_preset)
                st.session_state[APPEARANCE_PRESET_SELECTION_STATE] = (
                    selected_preset.name
                )
                st.session_state[APPEARANCE_PRESET_NOTICE_STATE] = (
                    "success",
                    f"Applied appearance preset '{selected_preset.name}'.",
                )
                st.session_state[APPEARANCE_PRESET_DELETE_STATE] = None
                _refresh_form()
                st.rerun()

        if update_clicked:
            try:
                preset = build_appearance_preset(
                    selected_preset.name,
                    current_project_data,
                )
                stored = save_appearance_preset(
                    preset,
                    directory,
                    overwrite=True,
                )
            except AppearancePresetError as exc:
                st.error(str(exc), icon=":material/error:")
            else:
                st.session_state[APPEARANCE_PRESET_SELECTION_STATE] = stored.name
                st.session_state[APPEARANCE_PRESET_NOTICE_STATE] = (
                    "success",
                    f"Updated appearance preset '{stored.name}'.",
                )
                st.session_state[APPEARANCE_PRESET_DELETE_STATE] = None
                _refresh_form()
                st.rerun()

        if save_new_clicked:
            try:
                preset = build_appearance_preset(
                    new_preset_name,
                    current_project_data,
                )
                stored = save_appearance_preset(
                    preset,
                    directory,
                    overwrite=False,
                )
            except AppearancePresetError as exc:
                st.error(str(exc), icon=":material/error:")
            else:
                st.session_state[APPEARANCE_PRESET_SELECTION_STATE] = stored.name
                st.session_state[APPEARANCE_PRESET_NOTICE_STATE] = (
                    "success",
                    f"Saved appearance preset '{stored.name}'.",
                )
                st.session_state[APPEARANCE_PRESET_DELETE_STATE] = None
                _refresh_form()
                st.rerun()

        if delete_clicked:
            st.session_state[APPEARANCE_PRESET_DELETE_STATE] = (
                selected_preset.name
            )
            st.rerun()

        pending_delete = st.session_state.get(APPEARANCE_PRESET_DELETE_STATE)
        if pending_delete and selected_preset is None:
            st.session_state[APPEARANCE_PRESET_DELETE_STATE] = None
            pending_delete = None
        if pending_delete and selected_preset is not None:
            if pending_delete.casefold() != selected_preset.name.casefold():
                st.session_state[APPEARANCE_PRESET_DELETE_STATE] = None
            else:
                st.warning(
                    f"Delete appearance preset '{selected_preset.name}'?",
                    icon=":material/delete_forever:",
                )
                with st.container(horizontal=True, gap="small"):
                    confirm_delete = st.button(
                        "Confirm deletion",
                        icon=":material/delete_forever:",
                        type="primary",
                        key=_widget_key("confirm_delete_appearance_preset"),
                    )
                    cancel_delete = st.button(
                        "Cancel",
                        key=_widget_key("cancel_delete_appearance_preset"),
                    )

                if confirm_delete:
                    try:
                        delete_appearance_preset(selected_preset, directory)
                    except AppearancePresetError as exc:
                        st.error(str(exc), icon=":material/error:")
                    else:
                        st.session_state[APPEARANCE_PRESET_SELECTION_STATE] = ""
                        st.session_state[APPEARANCE_PRESET_NOTICE_STATE] = (
                            "info",
                            f"Deleted appearance preset '{selected_preset.name}'.",
                        )
                        st.session_state[APPEARANCE_PRESET_DELETE_STATE] = None
                        _refresh_form()
                        st.rerun()

                if cancel_delete:
                    st.session_state[APPEARANCE_PRESET_DELETE_STATE] = None
                    st.rerun()


def _appearance_preset_directory():
    configured = str(os.environ.get(APPEARANCE_PRESET_DIR_ENV, "")).strip()
    directory = (
        Path(configured)
        if configured
        else ROOT_DIR / "presets" / "appearance"
    )

    if not directory.is_absolute():
        directory = ROOT_DIR / directory

    return directory


def _appearance_preset_target(loaded_project_data, loaded_project_path):
    current_draft = st.session_state.get(CURRENT_DRAFT_STATE)
    if isinstance(current_draft, dict) and isinstance(
        current_draft.get("project_data"),
        dict,
    ):
        return (
            copy.deepcopy(current_draft["project_data"]),
            current_draft.get("project_file") or loaded_project_path,
        )

    if isinstance(loaded_project_data, dict):
        return copy.deepcopy(loaded_project_data), loaded_project_path

    return None, loaded_project_path


def _sync_appearance_asset_overrides(preset):
    background_path = preset.canvas.get("background_image_path")
    texture_path = preset.bars.get("bar_texture_custom_image")

    if background_path:
        st.session_state[BACKGROUND_IMAGE_PATH_STATE] = background_path
    else:
        st.session_state.pop(BACKGROUND_IMAGE_PATH_STATE, None)

    if texture_path:
        st.session_state[CUSTOM_TEXTURE_PATH_STATE] = texture_path
    else:
        st.session_state.pop(CUSTOM_TEXTURE_PATH_STATE, None)

    st.session_state.pop(CATEGORY_AREA_SPAN_OVERRIDE_STATE, None)


def _resolved_theme(values):
    theme = values.get("theme") or "clean_report"

    try:
        return theme, get_theme(theme)
    except ValueError:
        return "clean_report", get_theme("clean_report")


def _resolved_typography(values):
    typography = values.get("typography_preset") or "editorial"

    try:
        return typography, get_typography_preset(typography)
    except ValueError:
        return "editorial", get_typography_preset("editorial")


def _data_settings_from_values(inspection, values, dataset):
    title = values.get("title") or "Untitled project"
    year_column = _resolved_dataset_column(
        inspection,
        values.get("year_column"),
        inspection.year_candidates,
        "year",
    )
    name_column = _resolved_dataset_column(
        inspection,
        values.get("name_column"),
        inspection.name_candidates,
        "country",
    )
    value_column = _resolved_dataset_column(
        inspection,
        values.get("value_column"),
        inspection.value_candidates,
        "value",
    )
    try:
        available_years = year_values_from_dataframe(dataset, year_column)
    except (OSError, ValueError):
        available_years = ()

    return {
        "title": title,
        "project_name": (
            values.get("name") or project_name_from_title(title)
        ),
        "year_column": year_column,
        "name_column": name_column,
        "value_column": value_column,
        "time_label_column": (
            values.get("time_label_column")
            if values.get("time_label_column") in inspection.columns
            else None
        ),
        "source_label": values.get("source_label") or "",
        "available_years": available_years,
    }


def _resolved_dataset_column(inspection, selected, candidates, fallback):
    if selected in inspection.columns:
        return selected

    return preferred_column(candidates, inspection.columns, fallback)


def _canvas_settings_from_values(
    values,
    *,
    theme_settings,
    typography_settings,
):
    layouts = list_layout_presets()
    layout_preset = values.get("layout_preset")
    if layout_preset not in layouts:
        layout_preset = layouts[0]
    layout = get_layout_preset(layout_preset)
    background_mode = values.get("background_mode", "color")
    if background_mode not in ("color", "image"):
        background_mode = "color"
    background_fit = values.get("background_image_fit", "cover")
    if background_fit not in ("cover", "contain", "stretch"):
        background_fit = "cover"
    right_margin = _int_in_range_or_default(
        values.get("right_margin"),
        layout.right_margin,
        0,
        max(0, layout.width - 1),
    )
    max_left_margin = max(0, layout.width - right_margin - 1)
    left_margin = _int_in_range_or_default(
        values.get("left_margin"),
        layout.left_margin,
        0,
        max_left_margin,
    )

    return {
        "layout_preset": layout_preset,
        "max_visible": _positive_int_or_default(
            values.get("max_visible_bars"),
            8,
        ),
        "background": {
            "mode": background_mode,
            "color": _color_or_default(
                values.get("background_color_override"),
                theme_settings.background_color,
            ),
            "image_path": values.get("background_image_path"),
            "image_fit": background_fit,
            "motion": values.get("background_motion", "off"),
            "motion_speed": float(values.get("background_motion_speed", 1.0)),
            "motion_intensity": float(values.get("background_motion_intensity", 0.35)),
        },
        "value_axis": {
            "enabled": bool(values.get("value_grid_enabled", False)),
            "mode": values.get("value_grid_mode", "dynamic"),
            "show_labels": bool(values.get(
                "value_grid_tick_labels_enabled", True
            )),
            "tick_value_format": values.get(
                "value_grid_tick_value_format", "same"
            ),
            "line_color": _color_or_default(
                values.get("value_grid_line_color"), "#FFFFFF"
            ),
            "line_opacity": _opacity_or_default(
                values.get("value_grid_line_opacity"), 0.18
            ),
            "line_thickness": float(values.get(
                "value_grid_line_thickness", 1.0
            )),
            "text_color": _color_or_default(
                values.get("value_grid_tick_text_color"),
                theme_settings.muted_text_color,
            ),
            "text_opacity": _opacity_or_default(
                values.get("value_grid_tick_text_opacity"), 0.72
            ),
            "font_size": _positive_int_or_default(
                values.get("value_grid_tick_font_size"), 16
            ),
            "font_weight": values.get(
                "value_grid_tick_font_weight", "normal"
            ),
            "font_style": values.get(
                "value_grid_tick_font_style", "normal"
            ),
            "target_tick_count": _int_in_range_or_default(
                values.get("value_grid_target_tick_count"), 5, 2, 12
            ),
        },
        "title_font_family": values.get("title_font_family"),
        "subtitle_font_family": values.get("subtitle_font_family"),
        "label_font_family": values.get("label_font_family"),
        "value_font_family": values.get("value_font_family"),
        "time_label_font_family": values.get("time_label_font_family"),
        "source_font_family": values.get("source_font_family"),
        "rank_label_font_family": values.get("rank_label_font_family"),
        "text_styles": {
            field: values.get(field, getattr(ChartConfig(), field))
            for field in (
                "title_font_weight", "title_font_style",
                "subtitle_font_weight", "subtitle_font_style",
                "time_label_font_weight", "time_label_font_style",
                "source_font_weight", "source_font_style",
                "label_font_weight", "label_font_style",
                "value_font_weight", "value_font_style",
                "rank_label_font_weight", "rank_label_font_style",
            )
        },
        "title_text_color": _color_or_default(
            values.get("title_text_color"),
            theme_settings.text_color,
        ),
        "title_text_opacity": _opacity_or_default(
            values.get("title_text_opacity"), 1.0,
        ),
        "subtitle_text_color": _color_or_default(
            values.get("subtitle_text_color"),
            theme_settings.muted_text_color,
        ),
        "subtitle_text_opacity": _opacity_or_default(
            values.get("subtitle_text_opacity"), 1.0,
        ),
        "label_text_color": _color_or_default(
            values.get("label_text_color"),
            theme_settings.text_color,
        ),
        "label_text_opacity": _opacity_or_default(
            values.get("label_text_opacity"), 1.0,
        ),
        "value_text_color": _color_or_default(
            values.get("value_text_color"),
            theme_settings.muted_text_color,
        ),
        "value_text_opacity": _opacity_or_default(
            values.get("value_text_opacity"), 1.0,
        ),
        "time_label_text_color": _color_or_default(
            values.get("time_label_text_color"),
            theme_settings.muted_text_color,
        ),
        "time_label_opacity": _opacity_or_default(
            values.get("time_label_opacity"),
            0.22,
        ),
        "source_text_color": _color_or_default(
            values.get("source_text_color"),
            theme_settings.muted_text_color,
        ),
        "source_text_opacity": _opacity_or_default(
            values.get("source_text_opacity"), 1.0,
        ),
        "rank_label_text_color": _color_or_default(
            values.get("rank_label_text_color"),
            theme_settings.muted_text_color,
        ),
        "rank_label_text_opacity": _opacity_or_default(
            values.get("rank_label_text_opacity"), 1.0,
        ),
        "bar_gap": max(0, int(values.get("bar_gap", 18))),
        "bar_color_source": values.get("bar_color_source", "manual"),
        "primary_logo_min_size": max(0, int(values.get("primary_logo_min_size", 0))),
        "title_font_size": _positive_int_or_default(
            values.get("title_font_size"),
            typography_settings.title_font_size,
        ),
        "subtitle_font_size": _positive_int_or_default(
            values.get("subtitle_font_size"),
            typography_settings.subtitle_font_size,
        ),
        "label_font_size": _positive_int_or_default(
            values.get("label_font_size"),
            typography_settings.label_font_size,
        ),
        "value_font_size": _positive_int_or_default(
            values.get("value_font_size"),
            typography_settings.value_font_size,
        ),
        "time_label_font_size": _positive_int_or_default(
            values.get("time_label_font_size"),
            typography_settings.time_label_font_size,
        ),
        "source_font_size": _positive_int_or_default(
            values.get("source_font_size"),
            typography_settings.source_font_size,
        ),
        "rank_label_font_size": _positive_int_or_default(
            values.get("rank_label_font_size"),
            18,
        ),
        "bar_vertical_layout_mode": values.get("bar_vertical_layout_mode", "manual"),
        "bar_vertical_top_padding": _int_in_range_or_default(values.get("bar_vertical_top_padding"), 24, 0, layout.height),
        "bar_vertical_bottom_padding": _int_in_range_or_default(values.get("bar_vertical_bottom_padding"), 24, 0, layout.height),
        "title_enabled": bool(values.get("title_enabled", True)),
        "subtitle_enabled": bool(values.get("subtitle_enabled", True)),
        "time_label_enabled": bool(values.get("time_label_enabled", True)),
        "source_label_enabled": bool(values.get("source_label_enabled", True)),
        "rank_labels_enabled": bool(values.get("rank_labels_enabled", True)),
        "category_labels_enabled": bool(
            values.get("category_labels_enabled", True)
        ),
        "value_labels_enabled": bool(
            values.get("value_labels_enabled", True)
        ),
        "title_x": int(
            values["title_x"]
            if values.get("title_x") is not None
            else layout.left_margin
        ),
        "title_y": int(
            values["title_y"]
            if values.get("title_y") is not None
            else layout.title_y
        ),
        "subtitle_x": int(
            values["subtitle_x"]
            if values.get("subtitle_x") is not None
            else layout.left_margin
        ),
        "subtitle_y": int(
            values["subtitle_y"]
            if values.get("subtitle_y") is not None
            else layout.subtitle_y
        ),
        "time_label_x": int(
            values["time_label_x"]
            if values.get("time_label_x") is not None
            else layout.time_label_x
        ),
        "time_label_y": int(
            values["time_label_y"]
            if values.get("time_label_y") is not None
            else layout.time_label_y
        ),
        "source_x": int(
            values["source_x"]
            if values.get("source_x") is not None
            else layout.source_x
        ),
        "source_y": int(
            values["source_y"]
            if values.get("source_y") is not None
            else layout.source_y
        ),
        "label_min_x": _int_in_range_or_default(
            values.get("label_min_x"),
            layout.label_min_x,
            0,
            left_margin,
        ),
        "left_margin": left_margin,
        "rank_label_gap": _int_in_range_or_default(
            values.get("rank_label_gap"),
            layout.rank_label_gap,
            0,
            layout.width,
        ),
    }


def _bars_settings_from_values(values):
    value_formats = list_value_formats()
    value_format = values.get("value_format")
    if value_format not in value_formats:
        value_format = value_formats[0]

    return {
        "value_format": value_format,
        "top_n": _positive_int_or_default(values.get("top_n"), 8),
        "aggregate_other": bool(values.get("aggregate_other", False)),
        "label_text_color": values.get("label_text_color"),
        "label_text_opacity": _opacity_or_default(
            values.get("label_text_opacity"), 1.0,
        ),
        "value_text_color": values.get("value_text_color"),
        "value_text_opacity": _opacity_or_default(
            values.get("value_text_opacity"), 1.0,
        ),
        "rank_label_text_color": values.get("rank_label_text_color"),
        "rank_label_text_opacity": _opacity_or_default(
            values.get("rank_label_text_opacity"), 1.0,
        ),
        "bar_gap": max(0, int(values.get("bar_gap", 18))),
        "bar_color_source": values.get("bar_color_source", "manual"),
        "primary_logo_min_size": max(
            0, int(values.get("primary_logo_min_size", 0))
        ),
        "bar_style": _bar_style_settings(values),
        "category_styles": _clean_category_style_mapping(
            values.get("categories", {})
        ),
    }


def _fun_fact_settings_from_values(values, *, layout_preset):
    layout = get_layout_preset(layout_preset)
    default_width = round(layout.width * DEFAULT_FUN_FACT_PANEL_WIDTH_RATIO)
    default_card_width = round(layout.width * DEFAULT_FLOATING_CARD_WIDTH_RATIO)
    default_card_height = round(layout.height * DEFAULT_FLOATING_CARD_HEIGHT_RATIO)
    return {
        "enabled": bool(values.get("fun_facts_enabled", False)),
        "source": values.get("fun_facts_source"),
        "layout": values.get("fun_facts_layout", "right_panel"),
        "panel_width": _int_in_range_or_default(
            values.get("fun_facts_panel_width"),
            default_width,
            160,
            max(160, layout.width - 160),
        ),
        "panel_margin": _int_in_range_or_default(
            values.get("fun_facts_panel_margin"),
            32,
            0,
            max(0, layout.width // 4),
        ),
        "panel_padding": _int_in_range_or_default(
            values.get("fun_facts_panel_padding"),
            28,
            8,
            max(8, layout.width // 6),
        ),
        "fade_in": float(values.get("fun_facts_fade_in", 0.20)),
        "fade_out": float(values.get("fun_facts_fade_out", 0.20)),
        "editorial_background_mode": values.get("fun_facts_editorial_background_mode", "card"),
        "editorial_background_color": values.get("fun_facts_editorial_background_color"),
        "editorial_background_texture": values.get("fun_facts_editorial_background_texture", "none"),
        "editorial_background_texture_intensity": _opacity_or_default(
            values.get("fun_facts_editorial_background_texture_intensity"), 0.25,
        ),
        "editorial_headline_size": int(values.get("fun_facts_editorial_headline_size", 28)),
        "editorial_headline_font_weight": values.get("fun_facts_editorial_headline_font_weight", "bold"),
        "editorial_headline_font_style": values.get("fun_facts_editorial_headline_font_style", "normal"),
        "editorial_headline_color": values.get("fun_facts_editorial_headline_color"),
        "editorial_headline_opacity": _opacity_or_default(
            values.get("fun_facts_editorial_headline_opacity"), 1.0,
        ),
        "editorial_body_size": int(values.get("fun_facts_editorial_body_size", 18)),
        "editorial_body_font_weight": values.get("fun_facts_editorial_body_font_weight", "normal"),
        "editorial_body_font_style": values.get("fun_facts_editorial_body_font_style", "normal"),
        "editorial_body_color": values.get("fun_facts_editorial_body_color"),
        "editorial_body_opacity": _opacity_or_default(
            values.get("fun_facts_editorial_body_opacity"), 1.0,
        ),
        "editorial_credit_size": int(values.get("fun_facts_editorial_credit_size", 12)),
        "editorial_credit_font_weight": values.get("fun_facts_editorial_credit_font_weight", "normal"),
        "editorial_credit_font_style": values.get("fun_facts_editorial_credit_font_style", "normal"),
        "editorial_credit_color": values.get("fun_facts_editorial_credit_color"),
        "editorial_credit_opacity": _opacity_or_default(
            values.get("fun_facts_editorial_credit_opacity"), 1.0,
        ),
        "editorial_image_area_ratio": float(values.get("fun_facts_editorial_image_area_ratio", 0.42)),
        "editorial_image_fit": values.get("fun_facts_editorial_image_fit", "contain"),
        "editorial_text_image_gap": int(values.get("fun_facts_editorial_text_image_gap", 18)),
        "editorial_top_offset": int(values.get("fun_facts_editorial_top_offset", 0)),
        "editorial_reposition_time_label": bool(values.get("fun_facts_editorial_reposition_time_label", True)),
        "editorial_orientation": values.get("fun_facts_editorial_orientation", "vertical"),
        "editorial_card_x": _int_in_range_or_default(values.get("fun_facts_editorial_card_x"), round(layout.width * 0.50), 0, layout.width),
        "editorial_card_y": _int_in_range_or_default(values.get("fun_facts_editorial_card_y"), round(layout.height * 0.54), 0, layout.height),
        "editorial_card_width": _int_in_range_or_default(values.get("fun_facts_editorial_card_width"), default_card_width, 240, layout.width),
        "editorial_card_height": _int_in_range_or_default(values.get("fun_facts_editorial_card_height"), default_card_height, 140, layout.height),
        "editorial_image_position": values.get("fun_facts_editorial_image_position", "right"),
        "editorial_collision_gap": _int_in_range_or_default(values.get("fun_facts_editorial_collision_gap"), 24, 0, layout.width),
    }


def _fun_facts_section(*, values, dataset, data_settings, layout_preset):
    section_intro(
        "Fun facts",
        "Schedule reusable editorial cards against visible timeline labels.",
        icon="lightbulb",
    )
    canvas_layout = get_layout_preset(layout_preset)
    settings = _fun_fact_settings_from_values(values, layout_preset=layout_preset)
    editorial_editor_key = _widget_key("fun_facts_editorial_layout_editor")
    editorial_event_key = f"{editorial_editor_key}_consumed_event"
    current_rect = {
        "x": settings["editorial_card_x"],
        "y": settings["editorial_card_y"],
        "width": settings["editorial_card_width"],
        "height": settings["editorial_card_height"],
    }
    editorial_state = editorial_layout_component_state(
        key=editorial_editor_key,
        rect=current_rect,
        canvas_width=canvas_layout.width,
        canvas_height=canvas_layout.height,
    )
    rect, consumed_event_id, accepted_editor_event = reconcile_editorial_geometry(
        current_rect=current_rect,
        component_state=editorial_state,
        consumed_event_id=st.session_state.get(editorial_event_key),
        canvas_width=canvas_layout.width,
        canvas_height=canvas_layout.height,
    )
    if consumed_event_id is not None:
        st.session_state[editorial_event_key] = consumed_event_id
    if settings["layout"] == "editorial_floating" and accepted_editor_event:
        settings.update({
            "editorial_card_x": rect["x"],
            "editorial_card_y": rect["y"],
            "editorial_card_width": rect["width"],
            "editorial_card_height": rect["height"],
        })
        for field in ("x", "y", "width", "height"):
            st.session_state.pop(
                _widget_key(f"fun_facts_editorial_card_{field}"),
                None,
            )
    st.markdown("##### Source and scheduling")
    enabled = st.toggle(
        "Enable fun facts",
        value=settings["enabled"],
        key=_widget_key("fun_facts_enabled"),
    )
    source = st.text_input(
        "Source JSON",
        value=settings["source"] or "",
        placeholder="fun_facts/fun_facts.json",
        help="Path relative to the project root.",
        key=_widget_key("fun_facts_source"),
    ).strip()
    st.markdown("##### Card layout and transitions")
    layout_column, width_column = st.columns(2)
    with layout_column:
        layout = st.selectbox(
            "Layout",
            ("right_panel", "editorial_right", "editorial_floating"),
            index=_option_index(("right_panel", "editorial_right", "editorial_floating"), settings["layout"]),
            key=_widget_key("fun_facts_layout"),
        )
    with width_column:
        panel_width = st.number_input(
            "Panel width",
            min_value=160,
            value=int(settings["panel_width"]),
            step=8,
            disabled=layout == "editorial_floating",
            key=_widget_key("fun_facts_panel_width"),
        )
    margin_column, padding_column = st.columns(2)
    with margin_column:
        panel_margin = st.number_input(
            "Panel margin",
            min_value=0,
            value=int(settings["panel_margin"]),
            step=4,
            disabled=layout == "editorial_floating",
            key=_widget_key("fun_facts_panel_margin"),
        )
    with padding_column:
        panel_padding = st.number_input(
            "Panel padding",
            min_value=8,
            value=int(settings["panel_padding"]),
            step=4,
            key=_widget_key("fun_facts_panel_padding"),
        )
    fade_in_column, fade_out_column = st.columns(2)
    with fade_in_column:
        fade_in = st.slider(
            "Fade in",
            min_value=0.0,
            max_value=1.0,
            value=float(settings["fade_in"]),
            step=0.05,
            key=_widget_key("fun_facts_fade_in"),
        )
    with fade_out_column:
        fade_out = st.slider(
            "Fade out",
            min_value=0.0,
            max_value=1.0,
            value=float(settings["fade_out"]),
            step=0.05,
            key=_widget_key("fun_facts_fade_out"),
        )
    if fade_in + fade_out > 1:
        st.error("Fade in plus fade out must be 1.0 or less.")

    editorial = {key: settings[key] for key in settings if key.startswith("editorial_")}
    editorial_editor_slot = None
    if layout in ("editorial_right", "editorial_floating"):
        with st.expander("Editorial layout", expanded=True, icon=":material/article:"):
            if layout == "editorial_floating":
                st.markdown("**Card composition**")
                orientation_column, image_side_column = st.columns(2)
                editorial["editorial_orientation"] = orientation_column.selectbox(
                    "Card orientation",
                    ("vertical", "horizontal"),
                    index=_option_index(("vertical", "horizontal"), settings["editorial_orientation"]),
                    key=_widget_key("fun_facts_editorial_orientation"),
                )
                editorial["editorial_image_position"] = image_side_column.selectbox(
                    "Image position",
                    ("right", "left"),
                    index=_option_index(("right", "left"), settings["editorial_image_position"]),
                    disabled=editorial["editorial_orientation"] != "horizontal",
                    key=_widget_key("fun_facts_editorial_image_position"),
                )
                st.markdown("**Position and size**")
                card_width_column, card_height_column = st.columns(2)
                editorial["editorial_card_width"] = card_width_column.number_input(
                    "Card width",
                    min_value=240,
                    max_value=canvas_layout.width,
                    value=settings["editorial_card_width"],
                    step=8,
                    key=_widget_key("fun_facts_editorial_card_width"),
                )
                editorial["editorial_card_height"] = card_height_column.number_input(
                    "Card height",
                    min_value=140,
                    max_value=canvas_layout.height,
                    value=settings["editorial_card_height"],
                    step=8,
                    key=_widget_key("fun_facts_editorial_card_height"),
                )
                max_card_x = max(
                    0,
                    canvas_layout.width - int(editorial["editorial_card_width"]),
                )
                max_card_y = max(
                    0,
                    canvas_layout.height - int(editorial["editorial_card_height"]),
                )
                card_x_key = _widget_key("fun_facts_editorial_card_x")
                card_y_key = _widget_key("fun_facts_editorial_card_y")
                _drop_widget_value_outside_range(card_x_key, 0, max_card_x)
                _drop_widget_value_outside_range(card_y_key, 0, max_card_y)
                position_x, position_y = st.columns(2)
                editorial["editorial_card_x"] = position_x.number_input(
                    "Card X",
                    min_value=0,
                    max_value=max_card_x,
                    value=_int_in_range_or_default(
                        settings["editorial_card_x"],
                        0,
                        0,
                        max_card_x,
                    ),
                    step=8,
                    key=card_x_key,
                )
                editorial["editorial_card_y"] = position_y.number_input(
                    "Card Y",
                    min_value=0,
                    max_value=max_card_y,
                    value=_int_in_range_or_default(
                        settings["editorial_card_y"],
                        0,
                        0,
                        max_card_y,
                    ),
                    step=8,
                    key=card_y_key,
                )
                editorial["editorial_collision_gap"] = st.number_input(
                    "Bar/card safety gap",
                    min_value=0,
                    max_value=canvas_layout.width,
                    value=settings["editorial_collision_gap"],
                    step=4,
                    help="Only rows that cross the card height reserve this horizontal gap.",
                    key=_widget_key("fun_facts_editorial_collision_gap"),
                )
                st.caption(
                    "Drag or resize the card below; the numeric fields update "
                    "after the gesture ends. All values are final-canvas pixels."
                )
                editorial_editor_slot = st.empty()
            st.markdown("**Card background**")
            background_mode_column, background_color_column = st.columns(2)
            editorial["editorial_background_mode"] = background_mode_column.selectbox(
                "Background mode", ("transparent", "solid", "card"),
                index=_option_index(("transparent", "solid", "card"), settings["editorial_background_mode"]),
                key=_widget_key("fun_facts_editorial_background_mode"),
            )
            editorial["editorial_background_color"] = background_color_column.color_picker(
                "Background color", value=settings["editorial_background_color"] or "#111827",
                key=_widget_key("fun_facts_editorial_background_color"),
                disabled=editorial["editorial_background_mode"] == "transparent",
            )
            texture_column, texture_intensity_column = st.columns(2)
            texture_options = ("none", "grain", "paper", "dots", "diagonal")
            editorial["editorial_background_texture"] = texture_column.selectbox(
                "Background texture", texture_options,
                index=_option_index(texture_options, settings["editorial_background_texture"]),
                key=_widget_key("fun_facts_editorial_background_texture"),
                disabled=editorial["editorial_background_mode"] == "transparent",
                format_func=lambda value: value.replace("_", " ").title(),
            )
            editorial["editorial_background_texture_intensity"] = _opacity_percent_slider(
                "Texture intensity",
                settings["editorial_background_texture_intensity"],
                0.25,
                _widget_key("fun_facts_editorial_background_texture_intensity"),
                disabled=(
                    editorial["editorial_background_mode"] == "transparent"
                    or editorial["editorial_background_texture"] == "none"
                ),
            )

            st.markdown("**Editorial text**")
            theme_settings = _resolved_theme(values)[1]
            headline_column, body_column, credit_column = st.columns(3)
            with headline_column:
                editorial["editorial_headline_color"] = st.color_picker(
                    "Headline color",
                    value=_color_or_default(settings["editorial_headline_color"], theme_settings.text_color),
                    key=_widget_key("fun_facts_editorial_headline_color"),
                )
                editorial["editorial_headline_opacity"] = _opacity_percent_slider(
                    "Headline opacity", settings["editorial_headline_opacity"], 1.0,
                    _widget_key("fun_facts_editorial_headline_opacity"),
                )
                editorial["editorial_headline_size"] = st.number_input(
                    "Headline size", min_value=8, max_value=160,
                    value=settings["editorial_headline_size"],
                    key=_widget_key("fun_facts_editorial_headline_size"),
                )
                editorial["editorial_headline_font_weight"] = (
                    "bold" if st.toggle(
                        "Headline bold",
                        value=settings["editorial_headline_font_weight"] == "bold",
                        key=_widget_key("fun_facts_editorial_headline_bold"),
                    ) else "normal"
                )
                editorial["editorial_headline_font_style"] = (
                    "italic" if st.toggle(
                        "Headline italic",
                        value=settings["editorial_headline_font_style"] == "italic",
                        key=_widget_key("fun_facts_editorial_headline_italic"),
                    ) else "normal"
                )
            with body_column:
                editorial["editorial_body_color"] = st.color_picker(
                    "Body color",
                    value=_color_or_default(settings["editorial_body_color"], theme_settings.muted_text_color),
                    key=_widget_key("fun_facts_editorial_body_color"),
                )
                editorial["editorial_body_opacity"] = _opacity_percent_slider(
                    "Body opacity", settings["editorial_body_opacity"], 1.0,
                    _widget_key("fun_facts_editorial_body_opacity"),
                )
                editorial["editorial_body_size"] = st.number_input(
                    "Body size", min_value=8, max_value=120,
                    value=settings["editorial_body_size"],
                    key=_widget_key("fun_facts_editorial_body_size"),
                )
                editorial["editorial_body_font_weight"] = (
                    "bold" if st.toggle(
                        "Body bold",
                        value=settings["editorial_body_font_weight"] == "bold",
                        key=_widget_key("fun_facts_editorial_body_bold"),
                    ) else "normal"
                )
                editorial["editorial_body_font_style"] = (
                    "italic" if st.toggle(
                        "Body italic",
                        value=settings["editorial_body_font_style"] == "italic",
                        key=_widget_key("fun_facts_editorial_body_italic"),
                    ) else "normal"
                )
            with credit_column:
                editorial["editorial_credit_color"] = st.color_picker(
                    "Credit color",
                    value=_color_or_default(settings["editorial_credit_color"], theme_settings.muted_text_color),
                    key=_widget_key("fun_facts_editorial_credit_color"),
                )
                editorial["editorial_credit_opacity"] = _opacity_percent_slider(
                    "Credit opacity", settings["editorial_credit_opacity"], 1.0,
                    _widget_key("fun_facts_editorial_credit_opacity"),
                )
                editorial["editorial_credit_size"] = st.number_input(
                    "Credit size", min_value=6, max_value=80,
                    value=settings["editorial_credit_size"],
                    key=_widget_key("fun_facts_editorial_credit_size"),
                )
                editorial["editorial_credit_font_weight"] = (
                    "bold" if st.toggle(
                        "Credit bold",
                        value=settings["editorial_credit_font_weight"] == "bold",
                        key=_widget_key("fun_facts_editorial_credit_bold"),
                    ) else "normal"
                )
                editorial["editorial_credit_font_style"] = (
                    "italic" if st.toggle(
                        "Credit italic",
                        value=settings["editorial_credit_font_style"] == "italic",
                        key=_widget_key("fun_facts_editorial_credit_italic"),
                    ) else "normal"
                )
            st.markdown("**Image and attribution layout**")
            editorial["editorial_image_area_ratio"] = st.slider("Image area", 0.0, 0.8, settings["editorial_image_area_ratio"], 0.05, key=_widget_key("fun_facts_editorial_image_area_ratio"))
            editorial["editorial_image_fit"] = st.selectbox("Image fit", ("contain", "cover"), index=_option_index(("contain", "cover"), settings["editorial_image_fit"]), key=_widget_key("fun_facts_editorial_image_fit"))
            editorial["editorial_text_image_gap"] = st.number_input("Text/image gap", min_value=0, max_value=200, value=settings["editorial_text_image_gap"], key=_widget_key("fun_facts_editorial_text_image_gap"))
            editorial["editorial_top_offset"] = st.number_input("Top offset", min_value=0, max_value=500, value=settings["editorial_top_offset"], disabled=layout == "editorial_floating", key=_widget_key("fun_facts_editorial_top_offset"))
            editorial["editorial_reposition_time_label"] = st.toggle("Place date with editorial layout", value=settings["editorial_reposition_time_label"], key=_widget_key("fun_facts_editorial_reposition_time_label"))

    result = {
        "enabled": enabled,
        "source": source or None,
        "layout": layout,
        "panel_width": int(panel_width),
        "panel_margin": int(panel_margin),
        "panel_padding": int(panel_padding),
        "fade_in": float(fade_in),
        "fade_out": float(fade_out),
        **editorial,
    }
    if editorial_editor_slot is not None:
        result["_editorial_layout_editor"] = {
            "slot": editorial_editor_slot,
            "key": editorial_editor_key,
            "rect": {
                "x": int(editorial["editorial_card_x"]),
                "y": int(editorial["editorial_card_y"]),
                "width": int(editorial["editorial_card_width"]),
                "height": int(editorial["editorial_card_height"]),
            },
        }
    if not source:
        st.info("Choose a version-1 fun fact JSON file to validate and preview it.")
        return result

    try:
        collection = load_fun_fact_collection(
            source,
            project_root=_active_project_root(_current_workspace_layout()),
        )
        timeline = Timeline(
            dataset,
            config=DatasetConfig(
                year_column=data_settings["year_column"],
                name_column=data_settings["name_column"],
                value_column=data_settings["value_column"],
                time_label_column=data_settings.get("time_label_column"),
            ),
        )
        scheduler = FunFactScheduler(
            collection,
            timeline,
            fade_in=fade_in,
            fade_out=fade_out,
        )
    except (FunFactFileError, FunFactScheduleError, ValueError, OSError) as exc:
        st.error(str(exc))
        return result

    facts = collection.facts
    first = scheduler.facts[0].fact.start if scheduler.facts else "—"
    last = (
        max(scheduler.facts, key=lambda item: item.end_index).fact.end
        if scheduler.facts
        else "—"
    )
    count_metric, first_metric, last_metric = st.columns(3)
    count_metric.metric("Facts", len(facts))
    first_metric.metric("First date", first)
    last_metric.metric("Last date", last)
    st.success("The fun fact file and timeline schedule are valid.")

    if not facts:
        return result
    period_pairs = timeline.get_period_labels()
    period_labels = tuple(label for _, label in period_pairs)
    preview_state = st.session_state.get(PREVIEW_SETTINGS_STATE, {})
    if not isinstance(preview_state, dict):
        preview_state = {}
    current_year = preview_state.get("year")
    current_label = (
        timeline.get_time_label(current_year)
        if current_year is not None
        else None
    )
    st.markdown("##### Preview controls")
    st.caption(
        "This uses the same selected preview frame shown in Latest preview and Export."
    )
    selected_label = st.selectbox(
        "Fun Fact preview period",
        period_labels,
        index=_option_index(period_labels, current_label),
        key=_widget_key("fun_facts_preview_period"),
    )
    periods_by_label = {label: period for period, label in period_pairs}
    selected_period = periods_by_label[selected_label]
    fact_ids = tuple(fact.id for fact in facts)
    selected_fact = st.selectbox(
        "Active fact",
        fact_ids,
        key=_widget_key("fun_facts_active_fact"),
    )
    with st.container(horizontal=True, horizontal_alignment="left"):
        force_preview = st.button(
            "Preview selected fact",
            icon=":material/preview:",
            key=_widget_key("fun_facts_force_preview"),
        )
        scheduled_preview = st.button(
            "Use timeline scheduling",
            icon=":material/schedule:",
            key=_widget_key("fun_facts_scheduled_preview"),
        )
    updated_preview = {
        "year": selected_period,
        "preview_mode": "year",
        "transition_progress": 0.0,
        "force_fun_fact_id": preview_state.get("force_fun_fact_id"),
    }
    if force_preview:
        updated_preview["force_fun_fact_id"] = selected_fact
    if scheduled_preview:
        updated_preview["force_fun_fact_id"] = None
    st.session_state[PREVIEW_SETTINGS_STATE] = updated_preview
    return result


def _render_settings_from_values(
    values,
    *,
    paths,
    loaded_project_path,
    available_years,
):
    frame_output_mode = values.get("frame_output_mode", "ffmpeg_stream")
    if frame_output_mode not in ("ffmpeg_stream", "png_sequence"):
        frame_output_mode = "ffmpeg_stream"
    motion_mode = values.get("motion_mode", "transition_easing")
    if motion_mode not in ("transition_easing", "continuous"):
        motion_mode = "transition_easing"

    current_draft = st.session_state.get(CURRENT_DRAFT_STATE)
    current_project_file = (
        current_draft.get("project_file")
        if isinstance(current_draft, dict)
        else None
    )
    return {
        "fps": _positive_int_or_default(values.get("fps"), 24),
        "steps": _positive_int_or_default(
            values.get("steps_per_transition"),
            24,
        ),
        "motion_mode": motion_mode,
        "frame_output_mode": frame_output_mode,
        "png_compress_level": _int_in_range_or_default(
            values.get("png_compress_level"),
            default=1,
            minimum=0,
            maximum=9,
        ),
        "output_file": values.get("output_file") or paths["output_file"],
        "frames_dir": values.get("frames_dir") or paths["frames_dir"],
        "project_file": (
            current_project_file
            or loaded_project_path
            or values.get("project_file")
            or paths["project_file"]
        ),
        "preview_settings": _preview_settings_from_state(available_years),
        "export": _export_settings_from_values(values, available_years),
    }


def _export_settings_from_values(values, available_periods):
    defaults = ExportConfig()
    periods = tuple(available_periods)
    start = values.get("short_from_period")
    end = values.get("short_to_period")
    if start not in periods:
        start = periods[0] if periods else None
    if end not in periods:
        end = periods[-1] if periods else None
    if (
        start in periods
        and end in periods
        and periods.index(start) > periods.index(end)
    ):
        end = periods[-1]

    return {
        "mode": (
            values.get("mode")
            if values.get("mode") in ("standard", "short")
            else defaults.mode
        ),
        "short_width": 1080,
        "short_height": 1920,
        "short_from_period": start,
        "short_to_period": end,
        "short_intro_enabled": bool(values.get(
            "short_intro_enabled", defaults.short_intro_enabled
        )),
        "short_intro_text": str(values.get(
            "short_intro_text", defaults.short_intro_text
        )),
        "short_intro_duration": float(values.get(
            "short_intro_duration", defaults.short_intro_duration
        )),
        "short_context_enabled": bool(values.get(
            "short_context_enabled", defaults.short_context_enabled
        )),
        "short_context_title": str(values.get(
            "short_context_title", defaults.short_context_title
        )),
        "short_context_subtitle": str(values.get(
            "short_context_subtitle", defaults.short_context_subtitle
        )),
        "short_outro_enabled": bool(values.get(
            "short_outro_enabled", defaults.short_outro_enabled
        )),
        "short_outro_text": str(values.get(
            "short_outro_text", defaults.short_outro_text
        )),
        "short_outro_duration": float(values.get(
            "short_outro_duration", defaults.short_outro_duration
        )),
        "short_include_fun_facts": bool(values.get(
            "short_include_fun_facts", defaults.short_include_fun_facts
        )),
    }


def _preview_settings_from_state(years):
    if not years:
        return {
            "year": None,
            "preview_mode": "year",
            "transition_progress": 0.0,
            "force_fun_fact_id": None,
        }

    settings = st.session_state.get(PREVIEW_SETTINGS_STATE)
    if not isinstance(settings, dict):
        settings = {}
    preview_mode = settings.get("preview_mode", "year")
    year = settings.get("year")
    force_fun_fact_id = settings.get("force_fun_fact_id")

    if preview_mode == "transition" and len(years) > 1:
        valid_years = years[:-1]
        if year not in valid_years:
            year = valid_years[0]
        return {
            "year": year,
            "preview_mode": "transition",
            "transition_progress": min(
                1.0,
                max(0.0, float(settings.get("transition_progress", 0.5))),
            ),
            "force_fun_fact_id": force_fun_fact_id,
        }

    if year not in years:
        year = years[0]
    return {
        "year": year,
        "preview_mode": "year",
        "transition_progress": 0.0,
        "force_fun_fact_id": force_fun_fact_id,
    }


def _data_content_section(csv_path, inspection, values, dataset):
    section_intro(
        "Data and content",
        "Name the project, map the CSV columns, and define source text.",
        icon="database",
    )
    st.markdown("##### Project identity")
    title_column, name_column_widget = st.columns((2, 1))

    with title_column:
        title = st.text_input(
            "Video title",
            value=values["title"],
            key=_widget_key("title"),
        )

    with name_column_widget:
        project_name = st.text_input(
            "Project name",
            value=values["name"] or project_name_from_title(title),
            key=_widget_key("project_name"),
        )

    st.markdown("##### Column mapping")
    year_field, category_field, value_field = st.columns(3)

    with year_field:
        year_column = st.selectbox(
            "Time column",
            inspection.columns,
            index=_column_index(
                inspection.columns,
                values["year_column"]
                or preferred_column(
                    inspection.year_candidates,
                    inspection.columns,
                    "year",
                ),
            ),
            key=_widget_key("year_column"),
        )

    with category_field:
        name_column = st.selectbox(
            "Category column",
            inspection.columns,
            index=_column_index(
                inspection.columns,
                values["name_column"]
                or preferred_column(
                    inspection.name_candidates,
                    inspection.columns,
                    "country",
                ),
            ),
            key=_widget_key("name_column"),
        )

    with value_field:
        value_column = st.selectbox(
            "Value column",
            inspection.columns,
            index=_column_index(
                inspection.columns,
                values["value_column"]
                or preferred_column(
                    inspection.value_candidates,
                    inspection.columns,
                    "value",
                ),
            ),
            key=_widget_key("value_column"),
        )

    st.markdown("##### Source and timeline")
    source_label = st.text_input(
        "Source text",
        value=values["source_label"],
        key=_widget_key("source_label"),
    )

    try:
        available_years = year_values_from_dataframe(dataset, year_column)
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        available_years = ()

    row_metric, period_metric, column_metric = st.columns(3)
    row_metric.metric("Rows", f"{inspection.row_count:,}")
    period_metric.metric("Time periods", f"{len(available_years):,}")
    column_metric.metric("Columns", f"{len(inspection.columns):,}")

    return {
        "title": title,
        "project_name": project_name,
        "year_column": year_column,
        "name_column": name_column,
        "value_column": value_column,
        "time_label_column": (
            values.get("time_label_column")
            if values.get("time_label_column") in inspection.columns
            else None
        ),
        "source_label": source_label,
        "available_years": available_years,
    }


def _canvas_text_section(
    *,
    values,
    title,
    source_label,
    theme_settings,
    typography_settings,
):
    section_intro(
        "Canvas and text",
        "Configure the canvas, background, typography, and text placement.",
        icon="dashboard_customize",
    )
    st.markdown("##### Canvas and background")
    layout_column, visible_column = st.columns(2)
    layouts = list_layout_presets()

    with layout_column:
        layout_preset = st.selectbox(
            "Canvas layout",
            layouts,
            index=_option_index(layouts, values["layout_preset"]),
            key=_widget_key("layout_preset"),
        )

    layout_changed = layout_preset != values.get("layout_preset")
    if layout_changed:
        st.session_state.pop(_widget_key("label_min_x"), None)
        st.session_state.pop(_widget_key("left_margin"), None)
        st.session_state.pop(_widget_key("rank_label_gap"), None)
        st.session_state.pop(CATEGORY_AREA_SPAN_OVERRIDE_STATE, None)

    with visible_column:
        max_visible = st.number_input(
            "Visible bar slots",
            min_value=1,
            max_value=100,
            value=_positive_int_or_default(values["max_visible_bars"], 8),
            step=1,
            help="Maximum number of rows fitted into the selected canvas.",
            key=_widget_key("max_visible"),
        )

    layout_settings = get_layout_preset(layout_preset)
    background = _background_panel(values, theme_settings.background_color)
    value_axis = _value_axis_panel(values, theme_settings)
    with st.expander("Available content area", expanded=True, icon=":material/height:"):
        st.caption(
            "Visible bar slots and Top N work together: Top N selects data; "
            "this canvas limit determines how many selected rows can be shown."
        )
        vertical_mode = st.selectbox(
            "Vertical layout",
            ("manual", "fill_available"),
            index=_option_index(("manual", "fill_available"), values.get("bar_vertical_layout_mode", "manual")),
            help="Fill available adapts bar height and spacing to visible text and canvas height.",
            key=_widget_key("bar_vertical_layout_mode"),
        )
        vertical_a, vertical_b = st.columns(2)
        with vertical_a:
            vertical_top_padding = st.number_input("Top padding", min_value=0, max_value=layout_settings.height, value=_int_in_range_or_default(values.get("bar_vertical_top_padding"), 24, 0, layout_settings.height), key=_widget_key("bar_vertical_top_padding"))
        with vertical_b:
            vertical_bottom_padding = st.number_input("Bottom padding", min_value=0, max_value=layout_settings.height, value=_int_in_range_or_default(values.get("bar_vertical_bottom_padding"), 24, 0, layout_settings.height), key=_widget_key("bar_vertical_bottom_padding"))
        st.button(
            "Use full vertical space",
            icon=":material/height:",
            on_click=_use_full_vertical_area,
            key=_widget_key("use_full_vertical_area"),
        )
    right_margin = _int_in_range_or_default(
        (
            layout_settings.right_margin
            if layout_changed
            else values.get("right_margin")
        ),
        layout_settings.right_margin,
        0,
        max(0, layout_settings.width - 1),
    )
    max_left_margin = max(0, layout_settings.width - right_margin - 1)

    with st.expander(
        "Category and bar geometry",
        expanded=True,
        icon=":material/format_align_left:",
    ):
        st.caption(
            "Set the label boundary, bar position, and the span that keeps "
            "rankings from moving right with the bars."
        )
        st.caption(
            "Category size is under Text sizes. Position, alignment, and "
            "X/Y offsets are under Bars and categories > Bar appearance > "
            "Category text. Text placed inside a bar is shortened and then "
            "hidden as the available space disappears."
        )
        label_column, bar_start_column, span_column = st.columns(3)

        with bar_start_column:
            left_margin = st.number_input(
                "Bar start",
                min_value=0,
                max_value=max_left_margin,
                value=_int_in_range_or_default(
                    (
                        layout_settings.left_margin
                        if layout_changed
                        else values.get("left_margin")
                    ),
                    layout_settings.left_margin,
                    0,
                    max_left_margin,
                ),
                step=1,
                help=(
                    "Horizontal start of the bars in canvas pixels. Increase "
                    "Category area span too, so the ranking stays on the left."
                ),
                key=_widget_key("left_margin"),
            )

        with label_column:
            label_min_x = st.number_input(
                "Category label start",
                min_value=0,
                max_value=int(left_margin),
                value=_int_in_range_or_default(
                    (
                        layout_settings.label_min_x
                        if layout_changed
                        else values.get("label_min_x")
                    ),
                    layout_settings.label_min_x,
                    0,
                    int(left_margin),
                ),
                step=1,
                help=(
                    "Left boundary of the category-name area in canvas pixels. "
                    "The ranking can move this boundary right when needed."
                ),
                key=_widget_key("label_min_x"),
            )

        with span_column:
            span_widget_key = _widget_key("rank_label_gap")
            span_override = st.session_state.pop(
                CATEGORY_AREA_SPAN_OVERRIDE_STATE,
                None,
            )
            if span_override is not None:
                st.session_state.pop(span_widget_key, None)
            rank_label_gap = st.number_input(
                "Category area span",
                min_value=0,
                max_value=layout_settings.width,
                value=_int_in_range_or_default(
                    (
                        layout_settings.rank_label_gap
                        if layout_changed
                        else (
                            span_override
                            if span_override is not None
                            else values.get("rank_label_gap")
                        )
                    ),
                    layout_settings.rank_label_gap,
                    0,
                    layout_settings.width,
                ),
                step=1,
                help=(
                    "Distance from the bar start back toward the ranking. "
                    "Increase it to use empty space on the left for names."
                ),
                key=span_widget_key,
            )

        rank_min_x = _int_in_range_or_default(
            (
                layout_settings.rank_label_min_x
                if layout_changed
                else values.get("rank_label_min_x")
            ),
            layout_settings.rank_label_min_x,
            0,
            layout_settings.width,
        )
        recommended_span = max(0, int(left_margin) - rank_min_x)
        st.caption(
            f"To keep the ranking at x={rank_min_x} with Bar start "
            f"{int(left_margin)}, use Category area span "
            f"{recommended_span} px or more."
        )
        st.button(
            "Use full left space",
            icon=":material/keyboard_double_arrow_left:",
            disabled=int(rank_label_gap) >= recommended_span,
            on_click=_set_session_value,
            args=(CATEGORY_AREA_SPAN_OVERRIDE_STATE, recommended_span),
            key=_widget_key("use_full_category_area"),
        )

    st.markdown("##### Typography and text")
    with st.expander(
        "Text visibility",
        expanded=True,
        icon=":material/visibility:",
    ):
        st.caption(
            "Choose which text elements are rendered. Hidden elements keep "
            "their typography and placement settings for later reuse."
        )
        header_column, bars_column, footer_column = st.columns(3)

        with header_column:
            st.markdown("**Header**")
            title_enabled = st.toggle(
                "Show title",
                value=bool(values.get("title_enabled", True)),
                key=_widget_key("title_enabled"),
            )
            subtitle_enabled = st.toggle(
                "Show subtitle",
                value=bool(values.get("subtitle_enabled", True)),
                key=_widget_key("subtitle_enabled"),
            )

        with bars_column:
            st.markdown("**Bars**")
            rank_labels_enabled = st.toggle(
                "Show rankings",
                value=bool(values.get("rank_labels_enabled", True)),
                key=_widget_key("rank_labels_enabled"),
            )
            category_labels_enabled = st.toggle(
                "Show categories",
                value=bool(values.get("category_labels_enabled", True)),
                key=_widget_key("category_labels_enabled"),
            )
            value_labels_enabled = st.toggle(
                "Show values",
                value=bool(values.get("value_labels_enabled", True)),
                key=_widget_key("value_labels_enabled"),
            )

        with footer_column:
            st.markdown("**Context**")
            time_label_enabled = st.toggle(
                "Show date",
                value=bool(values.get("time_label_enabled", True)),
                key=_widget_key("time_label_enabled"),
            )
            source_label_enabled = st.toggle(
                "Show source",
                value=bool(values.get("source_label_enabled", True)),
                key=_widget_key("source_label_enabled"),
            )

    with st.expander("Fonts", icon=":material/font_download:"):
        st.caption("Project default inherits the base font; each element can override it.")
        font_column_a, font_column_b, font_column_c = st.columns(3)

        with font_column_a:
            title_font_family = font_family_picker(
                "Title font",
                values["title_font_family"],
                _widget_key("title_font_family"),
            )
            subtitle_font_family = font_family_picker(
                "Subtitle font",
                values["subtitle_font_family"],
                _widget_key("subtitle_font_family"),
            )
            time_label_font_family = font_family_picker(
                "Date font",
                values["time_label_font_family"],
                _widget_key("time_label_font_family"),
            )

        with font_column_b:
            label_font_family = font_family_picker(
                "Category font",
                values["label_font_family"],
                _widget_key("label_font_family"),
            )
            value_font_family = font_family_picker(
                "Value font",
                values["value_font_family"],
                _widget_key("value_font_family"),
            )

        with font_column_c:
            rank_label_font_family = font_family_picker(
                "Ranking font",
                values["rank_label_font_family"],
                _widget_key("rank_label_font_family"),
            )
            source_font_family = font_family_picker(
                "Source font",
                values["source_font_family"],
                _widget_key("source_font_family"),
            )

    text_styles = {}
    with st.expander("Bold and italic", icon=":material/format_bold:"):
        st.caption("Bold and italic are independent and use installed font variants when available.")
        style_columns = st.columns(4)
        style_specs = (
            ("Title", "title", 0),
            ("Subtitle", "subtitle", 0),
            ("Date", "time_label", 1),
            ("Source", "source", 1),
            ("Category", "label", 2),
            ("Value", "value", 2),
            ("Ranking", "rank_label", 3),
        )
        for label, prefix, column_index in style_specs:
            with style_columns[column_index]:
                st.markdown(f"**{label}**")
                bold = st.toggle(
                    f"{label} bold",
                    value=values.get(f"{prefix}_font_weight", "normal") == "bold",
                    key=_widget_key(f"{prefix}_font_bold"),
                )
                italic = st.toggle(
                    f"{label} italic",
                    value=values.get(f"{prefix}_font_style", "normal") == "italic",
                    key=_widget_key(f"{prefix}_font_italic"),
                )
                text_styles[f"{prefix}_font_weight"] = "bold" if bold else "normal"
                text_styles[f"{prefix}_font_style"] = "italic" if italic else "normal"

    with st.expander("Text sizes", icon=":material/format_size:"):
        st.caption("Sizes use points and update the placement editor.")
        size_column_a, size_column_b, size_column_c, size_column_d = st.columns(4)

        with size_column_a:
            title_font_size = _font_size_input(
                "Title size",
                values["title_font_size"],
                typography_settings.title_font_size,
                _widget_key("title_font_size"),
            )
            subtitle_font_size = _font_size_input(
                "Subtitle size",
                values["subtitle_font_size"],
                typography_settings.subtitle_font_size,
                _widget_key("subtitle_font_size"),
            )

        with size_column_b:
            label_font_size = _font_size_input(
                "Category size",
                values["label_font_size"],
                typography_settings.label_font_size,
                _widget_key("label_font_size"),
            )
            value_font_size = _font_size_input(
                "Value size",
                values["value_font_size"],
                typography_settings.value_font_size,
                _widget_key("value_font_size"),
            )

        with size_column_c:
            time_label_font_size = _font_size_input(
                "Date size",
                values["time_label_font_size"],
                typography_settings.time_label_font_size,
                _widget_key("time_label_font_size"),
            )
            source_font_size = _font_size_input(
                "Source size",
                values["source_font_size"],
                typography_settings.source_font_size,
                _widget_key("source_font_size"),
            )

        with size_column_d:
            rank_label_font_size = _font_size_input(
                "Ranking size",
                values["rank_label_font_size"],
                18,
                _widget_key("rank_label_font_size"),
            )

    label_text_color = values["label_text_color"]
    value_text_color = values["value_text_color"]
    rank_label_text_color = values["rank_label_text_color"]
    label_text_opacity = _opacity_or_default(values.get("label_text_opacity"), 1.0)
    value_text_opacity = _opacity_or_default(values.get("value_text_opacity"), 1.0)
    rank_label_text_opacity = _opacity_or_default(values.get("rank_label_text_opacity"), 1.0)

    with st.expander("Text colors and opacity", icon=":material/palette:"):
        st.caption("Color and base opacity for canvas text. Bar text is configured in Bars.")
        title_column, subtitle_column, date_column, source_column = st.columns(4)

        with title_column:
            title_text_color = st.color_picker(
                "Title color",
                value=_color_or_default(values["title_text_color"], theme_settings.text_color),
                key=_widget_key("title_text_color"),
            )
            title_text_opacity = _opacity_percent_slider(
                "Title opacity", values.get("title_text_opacity"), 1.0,
                _widget_key("title_text_opacity"),
            )

        with subtitle_column:
            subtitle_text_color = st.color_picker(
                "Subtitle color",
                value=_color_or_default(values["subtitle_text_color"], theme_settings.muted_text_color),
                key=_widget_key("subtitle_text_color"),
            )
            subtitle_text_opacity = _opacity_percent_slider(
                "Subtitle opacity", values.get("subtitle_text_opacity"), 1.0,
                _widget_key("subtitle_text_opacity"),
            )

        with date_column:
            time_label_text_color = st.color_picker(
                "Date color",
                value=_color_or_default(values["time_label_text_color"], theme_settings.muted_text_color),
                key=_widget_key("time_label_text_color"),
            )
            time_label_opacity = _opacity_percent_slider(
                "Date opacity", values.get("time_label_opacity"), 0.22,
                _widget_key("time_label_opacity"),
            )

        with source_column:
            source_text_color = st.color_picker(
                "Source color",
                value=_color_or_default(values["source_text_color"], theme_settings.muted_text_color),
                key=_widget_key("source_text_color"),
            )
            source_text_opacity = _opacity_percent_slider(
                "Source opacity", values.get("source_text_opacity"), 1.0,
                _widget_key("source_text_opacity"),
            )

    editor_positions = {
        "title": {
            "x": values["title_x"] if values["title_x"] is not None else layout_settings.left_margin,
            "y": values["title_y"] if values["title_y"] is not None else layout_settings.title_y,
        },
        "subtitle": {
            "x": values["subtitle_x"] if values["subtitle_x"] is not None else layout_settings.left_margin,
            "y": values["subtitle_y"] if values["subtitle_y"] is not None else layout_settings.subtitle_y,
        },
        "date": {
            "x": values["time_label_x"] if values["time_label_x"] is not None else layout_settings.time_label_x,
            "y": values["time_label_y"] if values["time_label_y"] is not None else layout_settings.time_label_y,
        },
        "source": {
            "x": values["source_x"] if values["source_x"] is not None else layout_settings.source_x,
            "y": values["source_y"] if values["source_y"] is not None else layout_settings.source_y,
        },
    }
    editor_key = _widget_key("text_layout_editor")
    position_values = text_layout_editor_positions(
        key=editor_key,
        positions=editor_positions,
    )
    editor_elements = {
        "title": {
            "label": "Title",
            "text": title or "Title",
            "font_family": title_font_family,
            "font_size": int(title_font_size),
            "font_weight": text_styles["title_font_weight"],
            "font_style": text_styles["title_font_style"],
            "color": title_text_color,
            "opacity": title_text_opacity if title_enabled else 0.0,
        },
        "subtitle": {
            "label": "Subtitle",
            "text": "Period A -> Period B",
            "font_family": subtitle_font_family,
            "font_size": int(subtitle_font_size),
            "font_weight": text_styles["subtitle_font_weight"],
            "font_style": text_styles["subtitle_font_style"],
            "color": subtitle_text_color,
            "opacity": subtitle_text_opacity if subtitle_enabled else 0.0,
        },
        "date": {
            "label": "Date",
            "text": "2024",
            "font_family": time_label_font_family,
            "font_size": int(time_label_font_size),
            "font_weight": text_styles["time_label_font_weight"],
            "font_style": text_styles["time_label_font_style"],
            "color": time_label_text_color,
            "opacity": time_label_opacity if time_label_enabled else 0.0,
        },
        "source": {
            "label": "Source",
            "text": source_label or "Source",
            "font_family": source_font_family,
            "font_size": int(source_font_size),
            "font_weight": text_styles["source_font_weight"],
            "font_style": text_styles["source_font_style"],
            "color": source_text_color,
            "opacity": source_text_opacity if source_label_enabled else 0.0,
        },
    }
    preset_positions = {
        "title": {"x": layout_settings.left_margin, "y": layout_settings.title_y},
        "subtitle": {"x": layout_settings.left_margin, "y": layout_settings.subtitle_y},
        "date": {"x": layout_settings.time_label_x, "y": layout_settings.time_label_y},
        "source": {"x": layout_settings.source_x, "y": layout_settings.source_y},
    }
    with st.expander("Text placement", icon=":material/open_with:"):
        st.caption(
            "Geometry is computed in Python from the selected preview frame. "
            "Coordinates remain final-canvas pixels."
        )
        editor_slot = st.empty()

    return {
        "layout_preset": layout_preset,
        "max_visible": int(max_visible),
        "bar_vertical_layout_mode": vertical_mode,
        "bar_vertical_top_padding": int(vertical_top_padding),
        "bar_vertical_bottom_padding": int(vertical_bottom_padding),
        "label_min_x": int(label_min_x),
        "left_margin": int(left_margin),
        "rank_label_gap": int(rank_label_gap),
        "background": background,
        "value_axis": value_axis,
        "title_font_family": title_font_family,
        "subtitle_font_family": subtitle_font_family,
        "label_font_family": label_font_family,
        "value_font_family": value_font_family,
        "time_label_font_family": time_label_font_family,
        "source_font_family": source_font_family,
        "rank_label_font_family": rank_label_font_family,
        "text_styles": text_styles,
        "title_text_color": title_text_color,
        "title_text_opacity": title_text_opacity,
        "subtitle_text_color": subtitle_text_color,
        "subtitle_text_opacity": subtitle_text_opacity,
        "label_text_color": label_text_color,
        "label_text_opacity": label_text_opacity,
        "value_text_color": value_text_color,
        "value_text_opacity": value_text_opacity,
        "time_label_text_color": time_label_text_color,
        "time_label_opacity": time_label_opacity,
        "source_text_color": source_text_color,
        "source_text_opacity": source_text_opacity,
        "rank_label_text_color": rank_label_text_color,
        "rank_label_text_opacity": rank_label_text_opacity,
        "title_font_size": int(title_font_size),
        "subtitle_font_size": int(subtitle_font_size),
        "label_font_size": int(label_font_size),
        "value_font_size": int(value_font_size),
        "time_label_font_size": int(time_label_font_size),
        "source_font_size": int(source_font_size),
        "rank_label_font_size": int(rank_label_font_size),
        "title_enabled": bool(title_enabled),
        "subtitle_enabled": bool(subtitle_enabled),
        "time_label_enabled": bool(time_label_enabled),
        "source_label_enabled": bool(source_label_enabled),
        "rank_labels_enabled": bool(rank_labels_enabled),
        "category_labels_enabled": bool(category_labels_enabled),
        "value_labels_enabled": bool(value_labels_enabled),
        "title_x": int(position_values["title"]["x"]),
        "title_y": int(position_values["title"]["y"]),
        "subtitle_x": int(position_values["subtitle"]["x"]),
        "subtitle_y": int(position_values["subtitle"]["y"]),
        "time_label_x": int(position_values["date"]["x"]),
        "time_label_y": int(position_values["date"]["y"]),
        "source_x": int(position_values["source"]["x"]),
        "source_y": int(position_values["source"]["y"]),
        "_text_layout_editor": {
            "slot": editor_slot,
            "key": editor_key,
            "positions": position_values,
            "preset_positions": preset_positions,
            "elements": editor_elements,
            "theme": {
                "background_color": background["color"],
                "font_family": theme_settings.font_family,
            },
            "dpi": int(values["dpi"]),
        },
    }


def _mount_text_layout_editor(
    *,
    project_data,
    dataset,
    preview_settings,
    canvas_settings,
):
    editor = canvas_settings.get("_text_layout_editor")
    if not isinstance(editor, dict) or editor.get("slot") is None:
        return

    elements = copy.deepcopy(editor["elements"])
    geometry = {}
    preview = None
    error = None
    try:
        preview = build_studio_layout_preview(
            project_data,
            dataset,
            preview_settings,
        )
        geometry = build_scene_geometry(
            preview.chart_config,
            preview.fun_fact_config,
            preview.scene,
        )
        elements["title"]["text"] = preview.scene.title or "Title"
        elements["subtitle"]["text"] = preview.scene.subtitle or "Subtitle"
        elements["date"]["text"] = preview.scene.time_label or "Date"
        elements["source"]["text"] = preview.scene.source_label or "Source"
        effective_date = geometry.get("effective_positions", {}).get("date")
        raw_date = {
            "x": int(preview.raw_chart_config.time_label_x),
            "y": int(preview.raw_chart_config.time_label_y),
        }
        elements["date"]["managed"] = bool(
            effective_date
            and effective_date != raw_date
        )
    except (OSError, ValueError, ProjectFileError) as exc:
        error = str(exc)

    with editor["slot"].container():
        if error:
            st.warning(
                f"The selected frame geometry is unavailable: {error}",
                icon=":material/warning:",
            )
        text_layout_editor(
            canvas_width=(
                preview.chart_config.width
                if preview is not None
                else get_layout_preset(canvas_settings["layout_preset"]).width
            ),
            canvas_height=(
                preview.chart_config.height
                if preview is not None
                else get_layout_preset(canvas_settings["layout_preset"]).height
            ),
            dpi=(
                preview.chart_config.dpi
                if preview is not None
                else editor["dpi"]
            ),
            positions=editor["positions"],
            preset_positions=editor["preset_positions"],
            elements=elements,
            theme=editor["theme"],
            geometry=geometry,
            key=editor["key"],
        )


def _mount_editorial_layout_editor(
    *,
    project_data,
    dataset,
    preview_settings,
    fun_fact_settings,
):
    editor = fun_fact_settings.get("_editorial_layout_editor")
    if not isinstance(editor, dict) or editor.get("slot") is None:
        return
    preview = None
    geometry = {}
    error = None
    try:
        preview = build_studio_layout_preview(
            project_data,
            dataset,
            preview_settings,
        )
        geometry = build_scene_geometry(
            preview.chart_config,
            preview.fun_fact_config,
            preview.scene,
        )
    except (OSError, ValueError, ProjectFileError) as exc:
        error = str(exc)

    layout = get_layout_preset(project_data["chart"]["layout_preset"])
    canvas_width = preview.chart_config.width if preview else layout.width
    canvas_height = preview.chart_config.height if preview else layout.height
    background_color = (
        preview.chart_config.background_color
        if preview is not None
        else project_data["chart"].get("background_color_override", "#111827")
    )
    with editor["slot"].container():
        if error:
            st.warning(
                f"The selected frame geometry is unavailable: {error}",
                icon=":material/warning:",
            )
        editorial_layout_editor(
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            rect=editor["rect"],
            overlay=geometry,
            theme={
                "background_color": background_color,
                "card_background_mode": project_data.get("fun_facts", {}).get(
                    "editorial_background_mode", "card"
                ),
                "card_background_color": project_data.get("fun_facts", {}).get(
                    "editorial_background_color"
                ) or "#111827",
                "card_background_texture": project_data.get("fun_facts", {}).get(
                    "editorial_background_texture", "none"
                ),
                "card_background_texture_intensity": project_data.get("fun_facts", {}).get(
                    "editorial_background_texture_intensity", 0.25
                ),
            },
            key=editor["key"],
        )


def _bars_categories_section(
    *,
    csv_path,
    name_column,
    values,
    theme_settings,
    background_color,
    dataset,
):
    section_intro(
        "Bars and categories",
        "Control ranking, number formatting, materials, icons, and categories.",
        icon="bar_chart",
    )
    selection_panel = st.container(border=True)
    selection_panel.markdown("**Selection and visible rows**")
    selection_panel.caption(
        "Top N chooses categories from the data. Canvas > Available content "
        "area controls the separate visible-row limit."
    )
    format_column, ranking_column, aggregate_column = selection_panel.columns(3)
    value_formats = list_value_formats()

    with format_column:
        value_format = st.selectbox(
            "Value format",
            value_formats,
            index=_option_index(value_formats, values["value_format"]),
            key=_widget_key("value_format"),
        )

    with ranking_column:
        top_n = st.number_input(
            "Top N categories",
            min_value=1,
            max_value=100,
            value=_positive_int_or_default(values["top_n"], 8),
            step=1,
            help="Categories selected from the data before layout.",
            key=_widget_key("top_n"),
        )

    with aggregate_column:
        aggregate_other = st.toggle(
            "Group remaining as Other",
            value=bool(values["aggregate_other"]),
            key=_widget_key("aggregate_other"),
        )

    geometry_panel = st.container(border=True)
    geometry_panel.markdown("**Geometry, color source, and primary logo**")
    geometry_column, color_source_column, logo_min_column = geometry_panel.columns(3)
    with geometry_column:
        bar_gap = st.number_input(
            "Bar spacing",
            min_value=0,
            max_value=500,
            value=min(500, max(0, int(values.get("bar_gap", 18)))),
            step=1,
            help="Final-canvas pixels between adjacent rows. LayoutEngine applies it to all row content.",
            key=_widget_key("bar_gap"),
        )
    with color_source_column:
        bar_color_source = st.segmented_control(
            "Bar color source",
            options=("manual", "primary_logo"),
            default=(
                values.get("bar_color_source", "manual")
                if values.get("bar_color_source", "manual") in ("manual", "primary_logo")
                else "manual"
            ),
            format_func=lambda value: {
                "manual": "Manual",
                "primary_logo": "Primary logo",
            }[value],
            key=_widget_key("bar_color_source"),
        ) or "manual"
        st.caption("Manual category colors remain stored when logo color is active.")
    with logo_min_column:
        primary_logo_min_size = st.number_input(
            "Minimum primary logo size",
            min_value=0,
            max_value=500,
            value=min(500, max(0, int(values.get("primary_logo_min_size", 0)))),
            step=1,
            help=(
                "Pixel floor for the primary logo after applying Logo Size. "
                "The bar height always remains the hard maximum."
            ),
            key=_widget_key("primary_logo_min_size"),
        )

    text_panel = st.container(border=True)
    text_panel.markdown("**Bar text colors and opacity**")
    text_panel.caption(
        "Base opacity is multiplied by each bar's animation opacity."
    )
    category_column, value_column, rank_column = text_panel.columns(3)
    with category_column:
        label_text_color = st.color_picker(
            "Category color",
            value=_color_or_default(values.get("label_text_color"), theme_settings.text_color),
            key=_widget_key("label_text_color"),
        )
        label_text_opacity = _opacity_percent_slider(
            "Category opacity", values.get("label_text_opacity"), 1.0,
            _widget_key("label_text_opacity"),
        )
    with value_column:
        value_text_color = st.color_picker(
            "Value color",
            value=_color_or_default(values.get("value_text_color"), theme_settings.muted_text_color),
            key=_widget_key("value_text_color"),
        )
        value_text_opacity = _opacity_percent_slider(
            "Value opacity", values.get("value_text_opacity"), 1.0,
            _widget_key("value_text_opacity"),
        )
    with rank_column:
        rank_label_text_color = st.color_picker(
            "Ranking color",
            value=_color_or_default(values.get("rank_label_text_color"), theme_settings.muted_text_color),
            key=_widget_key("rank_label_text_color"),
        )
        rank_label_text_opacity = _opacity_percent_slider(
            "Ranking opacity", values.get("rank_label_text_opacity"), 1.0,
            _widget_key("rank_label_text_opacity"),
        )

    with st.expander("Bar appearance", icon=":material/texture:"):
        st.caption(
            "Bar material, category labels, values, ranking, logos, borders, and effects."
        )
        bar_style = bar_style_editor(
            settings=_bar_style_settings(values),
            bar_colors=theme_settings.bar_palette,
            background_color=background_color,
            key=_widget_key("bar_style_editor"),
        )
        bar_style = _custom_texture_upload(bar_style)

    category_styles = _category_styles_panel(
        csv_path=csv_path,
        name_column=name_column,
        existing_styles=values["categories"],
        dataset=dataset,
    )

    return {
        "value_format": value_format,
        "top_n": int(top_n),
        "aggregate_other": aggregate_other,
        "label_text_color": label_text_color,
        "label_text_opacity": label_text_opacity,
        "value_text_color": value_text_color,
        "value_text_opacity": value_text_opacity,
        "rank_label_text_color": rank_label_text_color,
        "rank_label_text_opacity": rank_label_text_opacity,
        "bar_gap": int(bar_gap),
        "bar_color_source": bar_color_source,
        "primary_logo_min_size": int(primary_logo_min_size),
        "bar_style": bar_style,
        "category_styles": category_styles,
    }


def _animation_output_section(
    *,
    csv_path,
    year_column,
    available_years,
    values,
    paths,
    loaded_project_path,
):
    section_intro(
        "Animation and export",
        "Set motion timing, review playback duration, and choose output files.",
        icon="movie_filter",
    )
    st.markdown("##### Export format")
    export_settings = _export_settings_from_values(values, available_years)
    export_mode = st.selectbox(
        "Format",
        options=("standard", "short"),
        index=1 if export_settings["mode"] == "short" else 0,
        format_func=lambda mode: {
            "standard": "Standard 16:9",
            "short": "Short 9:16",
        }[mode],
        key=_widget_key("export_mode"),
    )
    export_settings["mode"] = export_mode

    if export_mode == "short":
        export_settings = _short_export_controls(
            export_settings,
            available_years=available_years,
        )

    st.markdown("##### Motion and duration")
    fps_column, steps_column, motion_column = st.columns(3)

    with fps_column:
        fps = st.number_input(
            "FPS",
            min_value=1,
            max_value=120,
            value=_positive_int_or_default(values["fps"], 24),
            step=1,
            key=_widget_key("fps"),
        )

    with steps_column:
        steps = st.number_input(
            "Steps per transition",
            min_value=1,
            max_value=1200,
            value=_positive_int_or_default(values["steps_per_transition"], 24),
            step=1,
            key=_widget_key("steps"),
        )

    with motion_column:
        motion_mode = st.selectbox(
            "Motion mode",
            options=("transition_easing", "continuous"),
            index=0 if values["motion_mode"] == "transition_easing" else 1,
            format_func=lambda mode: {
                "transition_easing": "Per-period easing",
                "continuous": "Continuous",
            }[mode],
            key=_widget_key("motion_mode"),
        )

    with st.container(border=True):
        selected_periods = resolve_export_periods(
            available_years,
            ExportConfig(**export_settings),
        )
        estimate = _show_video_duration_estimate(
            period_count=len(selected_periods),
            fps=int(fps),
            steps_per_transition=int(steps),
            motion_mode=motion_mode,
            short_mode=export_mode == "short",
        )
        if export_mode == "short":
            st.caption(
                f"Short runtime: {estimate.duration_seconds:.1f} seconds. "
                "Choose a range near 25-35 seconds when practical."
            )

    with st.expander("Encoding", icon=":material/tune:"):
        output_mode_column, compression_column = st.columns(2)

        with output_mode_column:
            frame_output_mode = st.selectbox(
                "Frame output mode",
                options=("ffmpeg_stream", "png_sequence"),
                index=1 if values["frame_output_mode"] == "png_sequence" else 0,
                format_func=lambda mode: {
                    "png_sequence": "PNG sequence",
                    "ffmpeg_stream": "Direct FFmpeg stream (recommended)",
                }[mode],
                key=_widget_key("frame_output_mode"),
            )

        with compression_column:
            png_compress_level = st.number_input(
                "PNG compression",
                min_value=0,
                max_value=9,
                value=_int_in_range_or_default(
                    values["png_compress_level"],
                    default=1,
                    minimum=0,
                    maximum=9,
                ),
                step=1,
                disabled=frame_output_mode == "ffmpeg_stream",
                help="Only used when frames are saved as a PNG sequence.",
                key=_widget_key("png_compress_level"),
            )

    with st.expander("Output files", icon=":material/folder:"):
        output_column, project_column = st.columns(2)

        with output_column:
            output_file = st.text_input(
                "Output MP4",
                value=values["output_file"] or paths["output_file"],
                key=_widget_key("output_file"),
            )
            if export_mode == "short":
                effective_output = resolve_export_output_path(
                    output_file,
                    ExportConfig(**export_settings),
                )
                st.caption(f"Short render output: `{effective_output}`")

        with project_column:
            project_file = st.text_input(
                "Project JSON",
                value=(
                    loaded_project_path
                    or values["project_file"]
                    or paths["project_file"]
                ),
                key=_widget_key("project_file"),
            )

        frames_dir = st.text_input(
            "Frames directory",
            value=values["frames_dir"] or paths["frames_dir"],
            disabled=frame_output_mode == "ffmpeg_stream",
            help="Only used when frames are saved as a PNG sequence.",
            key=_widget_key("frames_dir"),
        )

    preview_settings = _preview_controls(
        csv_path,
        year_column,
        years=available_years,
    )
    st.session_state[PREVIEW_SETTINGS_STATE] = dict(preview_settings)

    return {
        "fps": int(fps),
        "steps": int(steps),
        "motion_mode": motion_mode,
        "frame_output_mode": frame_output_mode,
        "png_compress_level": int(png_compress_level),
        "output_file": output_file,
        "frames_dir": frames_dir,
        "project_file": project_file,
        "preview_settings": preview_settings,
        "export": export_settings,
    }


def _short_export_controls(
    settings,
    *,
    available_years,
):
    st.caption("Resolution: 1080 x 1920 · native vertical canvas")
    periods = tuple(available_years)
    if len(periods) < 2:
        st.warning("Short export requires at least two timeline periods.")
        return settings

    st.markdown("##### Timeline range")
    from_options = periods[:-1]
    configured_start = settings["short_from_period"]
    if configured_start not in from_options:
        configured_start = from_options[0]
    range_columns = st.columns(2)
    with range_columns[0]:
        start = st.selectbox(
            "From",
            options=from_options,
            index=from_options.index(configured_start),
            key=_widget_key("short_from_period"),
        )
    to_options = periods[periods.index(start) + 1 :]
    configured_end = settings["short_to_period"]
    if configured_end not in to_options:
        configured_end = to_options[-1]
    with range_columns[1]:
        end = st.selectbox(
            "To",
            options=to_options,
            index=to_options.index(configured_end),
            key=_widget_key(f"short_to_period_{start}"),
        )
    settings["short_from_period"] = start
    settings["short_to_period"] = end

    with st.expander(
        "Short text overlays",
        expanded=True,
        icon=":material/subtitles:",
    ):
        settings["short_intro_enabled"] = st.toggle(
            "Enable short intro hook",
            value=settings["short_intro_enabled"],
            key=_widget_key("short_intro_enabled"),
        )
        intro_columns = st.columns((2, 1))
        with intro_columns[0]:
            settings["short_intro_text"] = st.text_input(
                "Intro text",
                value=settings["short_intro_text"],
                disabled=not settings["short_intro_enabled"],
                key=_widget_key("short_intro_text"),
            )
        with intro_columns[1]:
            settings["short_intro_duration"] = float(st.number_input(
                "Intro duration (seconds)",
                min_value=0.0,
                max_value=60.0,
                value=settings["short_intro_duration"],
                step=0.5,
                disabled=not settings["short_intro_enabled"],
                key=_widget_key("short_intro_duration"),
            ))

        settings["short_context_enabled"] = st.toggle(
            "Enable short context text",
            value=settings["short_context_enabled"],
            key=_widget_key("short_context_enabled"),
        )
        settings["short_context_title"] = st.text_input(
            "Context title",
            value=settings["short_context_title"],
            disabled=not settings["short_context_enabled"],
            key=_widget_key("short_context_title"),
        )
        settings["short_context_subtitle"] = st.text_input(
            "Context subtitle",
            value=settings["short_context_subtitle"],
            disabled=not settings["short_context_enabled"],
            key=_widget_key("short_context_subtitle"),
        )

        settings["short_outro_enabled"] = st.toggle(
            "Enable short outro CTA",
            value=settings["short_outro_enabled"],
            key=_widget_key("short_outro_enabled"),
        )
        outro_columns = st.columns((2, 1))
        with outro_columns[0]:
            settings["short_outro_text"] = st.text_input(
                "Outro text",
                value=settings["short_outro_text"],
                disabled=not settings["short_outro_enabled"],
                key=_widget_key("short_outro_text"),
            )
        with outro_columns[1]:
            settings["short_outro_duration"] = float(st.number_input(
                "Outro duration (seconds)",
                min_value=0.0,
                max_value=60.0,
                value=settings["short_outro_duration"],
                step=0.5,
                disabled=not settings["short_outro_enabled"],
                key=_widget_key("short_outro_duration"),
            ))

        settings["short_include_fun_facts"] = st.toggle(
            "Include Fun Facts in Short",
            value=settings["short_include_fun_facts"],
            key=_widget_key("short_include_fun_facts"),
            help="Off by default to keep the vertical composition uncluttered.",
        )

    return settings


def _project_values_for_csv(values, csv_path, loaded_project_data):
    if loaded_project_data:
        return values

    csv_defaults = project_defaults_from_csv_path(csv_path)
    next_values = dict(values)
    next_values.update(csv_defaults)
    next_values["csv_path"] = csv_path

    return next_values


def _refresh_new_project_form_on_csv_change(csv_path, loaded_project_data):
    if loaded_project_data:
        st.session_state.pop(NEW_PROJECT_CSV_PATH_STATE, None)
        return

    previous_csv_path = st.session_state.get(NEW_PROJECT_CSV_PATH_STATE)
    if previous_csv_path is None:
        st.session_state[NEW_PROJECT_CSV_PATH_STATE] = csv_path
        st.session_state[NEW_PROJECT_CSV_PATH_OVERRIDE_STATE] = csv_path
        return

    if previous_csv_path == csv_path:
        return

    if _has_unsaved_draft():
        pending_action = st.session_state.get(PENDING_PROJECT_ACTION_STATE)
        if (
            isinstance(pending_action, dict)
            and pending_action.get("action") == "change_csv"
            and pending_action.get("csv_path") == csv_path
        ):
            return

        st.session_state[PENDING_PROJECT_ACTION_STATE] = {
            "action": "change_csv",
            "csv_path": csv_path,
            "previous_csv": previous_csv_path,
            "draft": copy.deepcopy(
                st.session_state.get(CURRENT_DRAFT_STATE)
            ),
        }
        st.rerun()

    _apply_new_project_csv_change(csv_path)


def _apply_new_project_csv_change(csv_path):
    st.session_state[NEW_PROJECT_CSV_PATH_STATE] = csv_path
    st.session_state[NEW_PROJECT_CSV_PATH_OVERRIDE_STATE] = csv_path
    st.session_state.pop(APPLIED_LOGO_MATCHES_STATE, None)
    st.session_state.pop(APPLIED_SECONDARY_LOGO_MATCHES_STATE, None)
    st.session_state[SAVED_DRAFT_FINGERPRINT_STATE] = None
    _reset_project_editor_state()
    _refresh_form()
    st.rerun()


def _clean_category_style_mapping(styles):
    return {
        raw_name: dict(style)
        for raw_name, style in styles.items()
        if isinstance(style, dict)
    }


def _category_style_context(csv_path, name_column):
    loaded_project_path = st.session_state.get("loaded_project_path", "")
    return "|".join(
        str(value)
        for value in (loaded_project_path, csv_path, name_column)
    )


def _category_draft_styles(context, existing_styles):
    category_draft = st.session_state.get(CATEGORY_STYLE_DRAFT_STATE)

    if not isinstance(category_draft, dict) or category_draft.get(
        "context"
    ) != context:
        styles = _clean_category_style_mapping(existing_styles)
        _store_category_draft_styles(context, styles)
        return styles

    return _clean_category_style_mapping(category_draft.get("styles", {}))


def _store_category_draft_styles(context, styles):
    st.session_state[CATEGORY_STYLE_DRAFT_STATE] = {
        "context": context,
        "styles": _clean_category_style_mapping(styles),
    }


def _category_styles_panel(csv_path, name_column, existing_styles, dataset):
    try:
        all_categories = category_values_from_dataframe(
            dataset,
            name_column,
            limit=None,
        )
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        return _clean_category_style_mapping(existing_styles)

    context = _category_style_context(csv_path, name_column)
    styles = _category_draft_styles(context, existing_styles)

    if not all_categories:
        return styles

    category_indices = {
        raw_name: index for index, raw_name in enumerate(all_categories)
    }

    with st.expander("Categories", icon=":material/category:"):
        st.caption(
            "Search or filter the dataset, edit one small page, then apply "
            "the page before navigating away."
        )
        upload_column, logo_folder_column, logo_action_column = st.columns([2, 2, 1])
        logo_folder_widget_key = _widget_key("category_logo_folder")

        with upload_column:
            uploaded_logo_files = st.file_uploader(
                "Logo folder",
                type=[extension.lstrip(".") for extension in LOGO_FILE_EXTENSIONS],
                accept_multiple_files="directory",
                key=_widget_key("category_logo_folder_upload"),
            )

            if uploaded_logo_files:
                logo_folder = _save_uploaded_logo_folder(uploaded_logo_files)
                previous_logo_folder = st.session_state.get(LOGO_FOLDER_OVERRIDE_STATE)
                st.session_state[LOGO_FOLDER_OVERRIDE_STATE] = logo_folder

                if previous_logo_folder != logo_folder:
                    st.session_state.pop(APPLIED_LOGO_MATCHES_STATE, None)
                    st.session_state[logo_folder_widget_key] = logo_folder
                    st.rerun()

        with logo_folder_column:
            logo_folder_input_kwargs = {"key": logo_folder_widget_key}

            if logo_folder_widget_key not in st.session_state:
                logo_folder_input_kwargs["value"] = st.session_state.get(
                    LOGO_FOLDER_OVERRIDE_STATE,
                    DEFAULT_LOGO_FOLDER,
                )

            logo_folder = st.text_input(
                "Logo folder path",
                **logo_folder_input_kwargs,
            )

        logo_files = _logo_files(logo_folder)
        matched_logos = match_category_logos(all_categories, logo_files)
        match_context = _logo_match_context(csv_path, name_column, logo_folder)
        styles = apply_category_logo_matches(
            styles,
            _applied_logo_matches(match_context),
        )

        with logo_action_column:
            apply_matched_logos = st.button(
                "Apply matched logos",
                width="stretch",
                disabled=not matched_logos,
                key=_widget_key("apply_matched_logos"),
            )

        if matched_logos:
            st.caption(f"{len(matched_logos)} logo matches")

        if apply_matched_logos:
            st.session_state[APPLIED_LOGO_MATCHES_STATE] = {
                "context": match_context,
                "matches": matched_logos,
            }
            styles = apply_category_logo_matches(styles, matched_logos)

        st.markdown("**Second logo source**")
        secondary_upload_column, secondary_folder_column, secondary_action_column = (
            st.columns([2, 2, 1])
        )
        secondary_folder_widget_key = _widget_key("category_secondary_logo_folder")

        with secondary_upload_column:
            uploaded_secondary_logo_files = st.file_uploader(
                "Second logo folder",
                type=[extension.lstrip(".") for extension in LOGO_FILE_EXTENSIONS],
                accept_multiple_files="directory",
                key=_widget_key("category_secondary_logo_folder_upload"),
            )

            if uploaded_secondary_logo_files:
                secondary_logo_folder = _save_uploaded_logo_folder(
                    uploaded_secondary_logo_files,
                    slot="secondary",
                )
                previous_secondary_folder = st.session_state.get(
                    SECONDARY_LOGO_FOLDER_OVERRIDE_STATE
                )
                st.session_state[SECONDARY_LOGO_FOLDER_OVERRIDE_STATE] = (
                    secondary_logo_folder
                )

                if previous_secondary_folder != secondary_logo_folder:
                    st.session_state.pop(
                        APPLIED_SECONDARY_LOGO_MATCHES_STATE,
                        None,
                    )
                    st.session_state[secondary_folder_widget_key] = (
                        secondary_logo_folder
                    )
                    st.rerun()

        with secondary_folder_column:
            secondary_folder_input_kwargs = {
                "key": secondary_folder_widget_key,
            }
            if secondary_folder_widget_key not in st.session_state:
                secondary_folder_input_kwargs["value"] = st.session_state.get(
                    SECONDARY_LOGO_FOLDER_OVERRIDE_STATE,
                    DEFAULT_SECONDARY_LOGO_FOLDER,
                )
            secondary_logo_folder = st.text_input(
                "Second logo folder path",
                **secondary_folder_input_kwargs,
            )

        secondary_logo_files = _logo_files(secondary_logo_folder)
        matched_secondary_logos = match_category_logos(
            all_categories,
            secondary_logo_files,
        )
        secondary_match_context = _logo_match_context(
            csv_path,
            name_column,
            secondary_logo_folder,
        )
        styles = apply_category_logo_matches(
            styles,
            _applied_logo_matches(
                secondary_match_context,
                state_key=APPLIED_SECONDARY_LOGO_MATCHES_STATE,
            ),
            logo_field="secondary_logo",
        )

        with secondary_action_column:
            apply_matched_secondary_logos = st.button(
                "Apply matched second logos",
                width="stretch",
                disabled=not matched_secondary_logos,
                key=_widget_key("apply_matched_secondary_logos"),
            )

        if matched_secondary_logos:
            st.caption(f"{len(matched_secondary_logos)} second logo matches")

        if apply_matched_secondary_logos:
            st.session_state[APPLIED_SECONDARY_LOGO_MATCHES_STATE] = {
                "context": secondary_match_context,
                "matches": matched_secondary_logos,
            }
            styles = apply_category_logo_matches(
                styles,
                matched_secondary_logos,
                logo_field="secondary_logo",
            )

        search_column, filter_column, size_column = st.columns([2, 2, 1])
        with search_column:
            category_query = st.text_input(
                "Search categories",
                placeholder="Name or custom label",
                key=_widget_key("category_search"),
            )
        with filter_column:
            category_filter = st.selectbox(
                "Category filter",
                CATEGORY_FILTERS,
                key=_widget_key("category_filter"),
            )
        with size_column:
            page_size = st.selectbox(
                "Rows per page",
                CATEGORY_PAGE_SIZES,
                key=_widget_key("category_page_size"),
            )

        filtered_categories = filter_categories(
            all_categories,
            styles,
            query=category_query,
            category_filter=category_filter,
        )
        provisional_page = paginate_categories(
            filtered_categories,
            page=1,
            page_size=page_size,
        )
        page_options = tuple(range(1, provisional_page.page_count + 1))
        page_widget_key = _widget_key("category_page")
        selected_page = st.session_state.get(page_widget_key, 1)

        if selected_page not in page_options:
            st.session_state[page_widget_key] = page_options[-1]

        page_number = st.selectbox(
            "Page",
            page_options,
            key=page_widget_key,
        )
        category_page = paginate_categories(
            filtered_categories,
            page=page_number,
            page_size=page_size,
        )
        visible_categories = category_page.items

        if apply_matched_logos:
            _set_matched_logo_widget_values(
                visible_categories,
                matched_logos,
                category_indices=category_indices,
            )

        if apply_matched_secondary_logos:
            _set_matched_logo_widget_values(
                visible_categories,
                matched_secondary_logos,
                logo_field="secondary_logo",
                category_indices=category_indices,
            )

        if category_page.total:
            st.caption(
                f"Showing {category_page.start}-{category_page.end} of "
                f"{category_page.total} matching categories "
                f"({len(all_categories)} total)."
            )
        else:
            st.info("No categories match the current search and filter.")

        submitted_rows = []
        if visible_categories:
            with st.form(
                _widget_key("category_page_editor"),
                clear_on_submit=False,
                border=False,
            ):
                for raw_name in visible_categories:
                    index = category_indices[raw_name]
                    key = _safe_widget_key(raw_name, index)
                    logo_widget_key = _widget_key(f"category_logo_{key}")
                    secondary_logo_widget_key = _widget_key(
                        f"category_secondary_logo_{key}"
                    )
                    current_style = styles.get(raw_name, {})
                    current_label = current_style.get("label", raw_name)
                    current_color = current_style.get("color")
                    current_logo = (
                        current_style.get("logo")
                        or st.session_state.get(logo_widget_key, "")
                    )
                    current_secondary_logo = (
                        current_style.get("secondary_logo")
                        or st.session_state.get(secondary_logo_widget_key, "")
                    )
                    default_color = current_color or DEFAULT_CATEGORY_COLORS[
                        index % len(DEFAULT_CATEGORY_COLORS)
                    ]

                    columns = st.columns([3, 1, 1, 2, 1])
                    with columns[0]:
                        label = st.text_input(
                            raw_name,
                            value=current_label,
                            key=_widget_key(f"category_label_{key}"),
                        )
                    with columns[1]:
                        use_color = st.checkbox(
                            "Custom color",
                            value=bool(current_color),
                            key=_widget_key(f"category_use_color_{key}"),
                        )
                    with columns[2]:
                        color = st.color_picker(
                            raw_name,
                            value=default_color,
                            key=_widget_key(f"category_color_{key}"),
                            label_visibility="collapsed",
                            disabled=not use_color,
                        )
                    with columns[3]:
                        logo_options = _logo_options(current_logo, logo_files)
                        logo_input_kwargs = {
                            "format_func": (
                                lambda path: "No logo" if not path else path
                            ),
                            "key": logo_widget_key,
                        }
                        if logo_widget_key not in st.session_state:
                            logo_input_kwargs["index"] = _option_index(
                                logo_options,
                                current_logo,
                            )
                        logo_path = st.selectbox(
                            "Logo",
                            logo_options,
                            **logo_input_kwargs,
                        )
                    with columns[4]:
                        uploaded_logo = st.file_uploader(
                            "Upload",
                            type=[
                                extension.lstrip(".")
                                for extension in LOGO_FILE_EXTENSIONS
                            ],
                            key=_widget_key(f"category_upload_logo_{key}"),
                        )
                        if uploaded_logo is not None:
                            logo_path = _save_uploaded_logo(raw_name, uploaded_logo)

                    secondary_logo_columns = st.columns([3, 1])
                    with secondary_logo_columns[0]:
                        secondary_logo_options = _logo_options(
                            current_secondary_logo,
                            secondary_logo_files,
                        )
                        secondary_logo_input_kwargs = {
                            "format_func": (
                                lambda path: (
                                    "No second logo" if not path else path
                                )
                            ),
                            "key": secondary_logo_widget_key,
                        }
                        if secondary_logo_widget_key not in st.session_state:
                            secondary_logo_input_kwargs["index"] = _option_index(
                                secondary_logo_options,
                                current_secondary_logo,
                            )
                        secondary_logo_path = st.selectbox(
                            "Second logo",
                            secondary_logo_options,
                            **secondary_logo_input_kwargs,
                        )
                    with secondary_logo_columns[1]:
                        uploaded_secondary_logo = st.file_uploader(
                            "Second upload",
                            type=[
                                extension.lstrip(".")
                                for extension in LOGO_FILE_EXTENSIONS
                            ],
                            key=_widget_key(
                                f"category_upload_secondary_logo_{key}"
                            ),
                        )
                        if uploaded_secondary_logo is not None:
                            secondary_logo_path = _save_uploaded_logo(
                                raw_name,
                                uploaded_secondary_logo,
                                slot="secondary",
                            )

                    submitted_rows.append({
                        "raw_name": raw_name,
                        "label": label,
                        "use_color": use_color,
                        "color": color,
                        "logo": logo_path,
                        "secondary_logo": secondary_logo_path,
                    })

                apply_category_edits = st.form_submit_button(
                    "Apply category changes",
                    icon=":material/check:",
                    type="primary",
                    width="stretch",
                )

            if apply_category_edits:
                for row in submitted_rows:
                    raw_name = row.pop("raw_name")
                    styles = update_category_style(
                        styles,
                        raw_name,
                        **row,
                    )
                st.success(
                    f"Applied changes for {len(submitted_rows)} categories."
                )

        _store_category_draft_styles(context, styles)

    return styles


def _save_draft(draft, *, show_success=True):
    layout = _current_workspace_layout()
    project_root = _active_project_root(
        layout,
        project_name=draft.project_data.get("name"),
    )
    project_kind = st.session_state.get(ACTIVE_PROJECT_KIND_STATE, "scratch")
    project_data = copy.deepcopy(draft.project_data)
    project_file = draft.project_file

    if (
        project_kind in {"legacy", "example"}
        or project_root == layout.app_root
        or project_root.is_relative_to(layout.app_root)
    ):
        source_root = project_root
        project_root = _writable_project_root(
            layout,
            hint=project_data.get("name") or "legacy_project",
            force_new=True,
        )
        project_data = _rebase_legacy_project_data(
            project_data,
            source_root=source_root,
        )
        project_file = "project.json"

    initialize_workspace(layout.workspace_root, app_root=layout.app_root)
    project_root.mkdir(parents=True, exist_ok=True)
    try:
        target_path = resolve_portable_project_path(
            project_file,
            project_root=project_root,
            required=True,
            field_name="project file",
            allow_absolute=False,
        )
        target_path = assert_user_write_path(
            target_path,
            app_root=layout.app_root,
            workspace_root=layout.workspace_root,
            operation="Project save",
        )
    except (ProjectPathError, WorkspacePathError, AppRootWriteError) as exc:
        st.error(str(exc))
        return None

    path = save_project_data(
        project_data,
        target_path,
        app_root=layout.app_root,
        workspace_root=layout.workspace_root,
    )
    saved_draft = ProjectDraft.create(project_data, project_file, draft.preview_settings)
    st.session_state[SAVED_DRAFT_FINGERPRINT_STATE] = saved_draft.fingerprint
    st.session_state[CURRENT_DRAFT_FINGERPRINT_STATE] = saved_draft.fingerprint
    st.session_state[CURRENT_DRAFT_STATE] = {
        "project_data": copy.deepcopy(saved_draft.project_data),
        "project_file": saved_draft.project_file,
    }
    st.session_state[SAVED_DRAFT_PENDING_STATE] = False
    st.session_state["loaded_project_data"] = copy.deepcopy(project_data)
    st.session_state["loaded_project_path"] = project_file
    st.session_state[ACTIVE_PROJECT_ROOT_STATE] = str(project_root)
    st.session_state[ACTIVE_PROJECT_KIND_STATE] = (
        "production"
        if project_root.is_relative_to(layout.productions_root)
        else "scratch"
    )
    try:
        location = project_location_from_path(path, layout)
    except (OSError, WorkspacePathError):
        st.session_state[LOADED_PROJECT_IDENTIFIER_STATE] = None
    else:
        st.session_state[LOADED_PROJECT_IDENTIFIER_STATE] = _project_option_value(
            location,
            layout,
        )
    _refresh_form()

    if show_success:
        try:
            display_path = path.resolve().relative_to(layout.workspace_root)
        except ValueError:
            display_path = path

        st.toast(
            f"Saved {display_path}",
            icon=":material/cloud_done:",
        )

    return path


def _logo_match_context(csv_path, name_column, logo_folder):
    return "|".join(str(value) for value in (csv_path, name_column, logo_folder))


def _applied_logo_matches(
    match_context,
    *,
    state_key=APPLIED_LOGO_MATCHES_STATE,
):
    applied_logo_matches = st.session_state.get(state_key, {})

    if not isinstance(applied_logo_matches, dict):
        return {}

    if applied_logo_matches.get("context") != match_context:
        return {}

    matches = applied_logo_matches.get("matches", {})

    return matches if isinstance(matches, dict) else {}


def _set_matched_logo_widget_values(
    visible_categories,
    matched_logos,
    *,
    logo_field="logo",
    category_indices=None,
):
    widget_prefix = (
        "category_secondary_logo_"
        if logo_field == "secondary_logo"
        else "category_logo_"
    )
    category_indices = category_indices or {}

    for fallback_index, raw_name in enumerate(visible_categories):
        logo_path = matched_logos.get(raw_name)

        if not logo_path:
            continue

        category_key = _safe_widget_key(
            raw_name,
            category_indices.get(raw_name, fallback_index),
        )
        widget_key = _widget_key(f"{widget_prefix}{category_key}")
        st.session_state[widget_key] = logo_path


def _clear_logo_session_overrides():
    st.session_state.pop(LOGO_FOLDER_OVERRIDE_STATE, None)
    st.session_state.pop(APPLIED_LOGO_MATCHES_STATE, None)
    st.session_state.pop(SECONDARY_LOGO_FOLDER_OVERRIDE_STATE, None)
    st.session_state.pop(APPLIED_SECONDARY_LOGO_MATCHES_STATE, None)
    st.session_state.pop(CUSTOM_TEXTURE_PATH_STATE, None)
    st.session_state.pop(BACKGROUND_IMAGE_PATH_STATE, None)


def _value_axis_panel(values, theme_settings):
    with st.expander("Value axis", icon=":material/grid_on:"):
        enabled = st.toggle(
            "Show value grid",
            value=bool(values.get("value_grid_enabled", False)),
            key=_widget_key("value_grid_enabled"),
        )
        mode = values.get("value_grid_mode", "dynamic")
        if mode not in ("static", "dynamic"):
            mode = "dynamic"
        mode = st.segmented_control(
            "Grid mode",
            options=("static", "dynamic"),
            default=mode,
            format_func=lambda value: {
                "static": "Static",
                "dynamic": "Dynamic",
            }[value],
            disabled=not enabled,
            key=_widget_key("value_grid_mode"),
        ) or mode
        show_labels = st.toggle(
            "Show tick labels",
            value=bool(values.get("value_grid_tick_labels_enabled", True)),
            disabled=not enabled,
            key=_widget_key("value_grid_tick_labels_enabled"),
        )
        tick_value_format = values.get(
            "value_grid_tick_value_format", "same"
        )
        if tick_value_format not in ("same", "full", "compact"):
            tick_value_format = "same"
        tick_value_format = st.segmented_control(
            "Tick value format",
            options=("same", "full", "compact"),
            default=tick_value_format,
            format_func=lambda value: {
                "same": "Same as bar values",
                "full": "Full",
                "compact": "Compact",
            }[value],
            disabled=not (enabled and show_labels),
            key=_widget_key("value_grid_tick_value_format"),
        ) or tick_value_format

        line_columns = st.columns(3)
        line_color = line_columns[0].color_picker(
            "Grid line color",
            value=_color_or_default(
                values.get("value_grid_line_color"), "#FFFFFF"
            ),
            disabled=not enabled,
            key=_widget_key("value_grid_line_color"),
        )
        line_opacity = line_columns[1].slider(
            "Grid line opacity",
            0.0,
            1.0,
            _opacity_or_default(values.get("value_grid_line_opacity"), 0.18),
            0.05,
            disabled=not enabled,
            key=_widget_key("value_grid_line_opacity"),
        )
        line_thickness = line_columns[2].slider(
            "Grid line thickness",
            0.5,
            4.0,
            min(4.0, max(0.5, float(values.get(
                "value_grid_line_thickness", 1.0
            )))),
            0.25,
            disabled=not enabled,
            key=_widget_key("value_grid_line_thickness"),
        )

        label_enabled = enabled and show_labels
        text_columns = st.columns(3)
        text_color = text_columns[0].color_picker(
            "Tick text color",
            value=_color_or_default(
                values.get("value_grid_tick_text_color"),
                theme_settings.muted_text_color,
            ),
            disabled=not label_enabled,
            key=_widget_key("value_grid_tick_text_color"),
        )
        text_opacity = text_columns[1].slider(
            "Tick text opacity",
            0.0,
            1.0,
            _opacity_or_default(
                values.get("value_grid_tick_text_opacity"), 0.72
            ),
            0.05,
            disabled=not label_enabled,
            key=_widget_key("value_grid_tick_text_opacity"),
        )
        font_size = text_columns[2].number_input(
            "Tick font size",
            min_value=8,
            max_value=72,
            value=_int_in_range_or_default(
                values.get("value_grid_tick_font_size"), 16, 8, 72
            ),
            step=1,
            disabled=not label_enabled,
            key=_widget_key("value_grid_tick_font_size"),
        )
        style_columns = st.columns(3)
        bold = style_columns[0].toggle(
            "Bold",
            value=values.get("value_grid_tick_font_weight", "normal")
            == "bold",
            disabled=not label_enabled,
            key=_widget_key("value_grid_tick_bold"),
        )
        italic = style_columns[1].toggle(
            "Italic",
            value=values.get("value_grid_tick_font_style", "normal")
            == "italic",
            disabled=not label_enabled,
            key=_widget_key("value_grid_tick_italic"),
        )
        target_tick_count = style_columns[2].number_input(
            "Target tick count",
            min_value=2,
            max_value=12,
            value=_int_in_range_or_default(
                values.get("value_grid_target_tick_count"), 5, 2, 12
            ),
            step=1,
            disabled=not enabled,
            key=_widget_key("value_grid_target_tick_count"),
        )

    return {
        "enabled": bool(enabled),
        "mode": mode,
        "show_labels": bool(show_labels),
        "tick_value_format": tick_value_format,
        "line_color": line_color,
        "line_opacity": float(line_opacity),
        "line_thickness": float(line_thickness),
        "text_color": text_color,
        "text_opacity": float(text_opacity),
        "font_size": int(font_size),
        "font_weight": "bold" if bold else "normal",
        "font_style": "italic" if italic else "normal",
        "target_tick_count": int(target_tick_count),
    }


def _background_panel(values, theme_background_color):
    mode_options = ("color", "image")
    current_mode = values.get("background_mode", "color")

    if current_mode not in mode_options:
        current_mode = "color"

    current_color = (
        values.get("background_color_override")
        or theme_background_color
    )

    if not (
        isinstance(current_color, str)
        and len(current_color) == 7
        and current_color.startswith("#")
        and all(
            character in "0123456789abcdefABCDEF"
            for character in current_color[1:]
        )
    ):
        current_color = theme_background_color
    current_image_path = (
        st.session_state.get(BACKGROUND_IMAGE_PATH_STATE)
        or values.get("background_image_path")
        or ""
    )

    with st.expander("Background", icon=":material/wallpaper:"):
        mode = st.segmented_control(
            "Background type",
            options=mode_options,
            default=current_mode,
            format_func=lambda value: {
                "color": "Color",
                "image": "Image",
            }[value],
            key=_widget_key("background_mode"),
        ) or current_mode
        color = st.color_picker(
            "Background color",
            value=current_color,
            help="Used directly in Color mode and behind image margins or transparency.",
            key=_widget_key("background_color"),
        )
        image_fit = st.selectbox(
            "Image fit",
            options=("cover", "contain", "stretch"),
            index=_option_index(
                ("cover", "contain", "stretch"),
                values.get("background_image_fit", "cover"),
            ),
            format_func=lambda value: {
                "cover": "Cover",
                "contain": "Contain",
                "stretch": "Stretch",
            }[value],
            disabled=mode != "image",
            key=_widget_key("background_image_fit"),
        )

        if mode == "image":
            image_path_widget_key = _widget_key("background_image_path")
            uploaded_background = st.file_uploader(
                "Upload background image",
                type=["png", "jpg", "jpeg", "webp"],
                key=_widget_key("background_image_upload"),
            )

            if uploaded_background is not None:
                source_name = Path(uploaded_background.name).name
                suffix = Path(source_name).suffix.lower()
                safe_stem = (
                    _safe_filename_key(Path(source_name).stem)
                    or "background"
                )
                layout = _current_workspace_layout()
                project_root = _writable_project_root(
                    layout,
                    hint=safe_stem,
                )
                background_dir = assert_user_write_path(
                    project_root / "assets" / "backgrounds",
                    app_root=layout.app_root,
                    workspace_root=layout.workspace_root,
                    operation="Background upload",
                )
                background_dir.mkdir(parents=True, exist_ok=True)
                background_path = background_dir / f"{safe_stem}{suffix}"
                background_path.write_bytes(uploaded_background.getbuffer())
                current_image_path = _project_relative_path(
                    background_path,
                    project_root=project_root,
                )
                st.session_state[BACKGROUND_IMAGE_PATH_STATE] = current_image_path
                st.session_state[image_path_widget_key] = current_image_path

            image_path_input_kwargs = {"key": image_path_widget_key}

            if image_path_widget_key not in st.session_state:
                image_path_input_kwargs["value"] = current_image_path

            current_image_path = st.text_input(
                "Background image path",
                **image_path_input_kwargs,
            ).strip()

            if current_image_path:
                st.caption(f"Background image: {current_image_path}")
                preview_path = Path(current_image_path)

                if not preview_path.is_absolute():
                    preview_path = _active_project_root(
                        _current_workspace_layout()
                    ) / preview_path

                if preview_path.is_file():
                    st.image(str(preview_path), width=320)
                else:
                    st.warning("The selected background image could not be found.")
            else:
                st.info("Upload an image or enter its path.")
        elif current_image_path:
            st.caption("The selected image is preserved for switching back to Image mode.")

        st.markdown("**Background motion**")
        motion = st.segmented_control(
            "Motion",
            options=("off", "forward_motion"),
            default=(
                values.get("background_motion", "off")
                if values.get("background_motion", "off") in ("off", "forward_motion")
                else "off"
            ),
            format_func=lambda value: {
                "off": "Off",
                "forward_motion": "Forward motion",
            }[value],
            key=_widget_key("background_motion"),
        ) or "off"
        motion_columns = st.columns(2)
        motion_speed = motion_columns[0].slider(
            "Motion speed", 0.0, 4.0,
            min(4.0, max(0.0, float(values.get("background_motion_speed", 1.0)))), 0.1,
            disabled=motion == "off",
            key=_widget_key("background_motion_speed"),
        )
        motion_intensity = motion_columns[1].slider(
            "Motion intensity", 0.0, 1.0,
            min(1.0, max(0.0, float(values.get("background_motion_intensity", 0.35)))), 0.05,
            disabled=motion == "off",
            key=_widget_key("background_motion_intensity"),
        )

    return {
        "mode": mode,
        "color": color,
        "image_path": current_image_path or None,
        "image_fit": image_fit,
        "motion": motion,
        "motion_speed": float(motion_speed),
        "motion_intensity": float(motion_intensity),
    }


def _show_video_duration_estimate(
    *,
    period_count,
    fps,
    steps_per_transition,
    motion_mode,
    short_mode=False,
):
    estimate = estimate_video_duration(
        period_count=period_count,
        steps_per_transition=steps_per_transition,
        fps=fps,
        continuous_motion=motion_mode == "continuous",
    )
    if short_mode:
        st.metric("Estimated duration", f"{estimate.duration_seconds:.1f} s")
    else:
        st.metric(
            "Estimated video duration",
            format_video_duration(estimate.duration_seconds),
        )

    if estimate.transition_count == 0:
        st.caption("At least two time periods are required to create a video.")
        return estimate

    st.caption(
        f"{estimate.period_count:,} periods · "
        f"{estimate.transition_count:,} transitions · "
        f"{estimate.frame_count:,} frames at {estimate.fps:,} FPS. "
        "This is video runtime, not rendering time."
    )
    return estimate


def _bar_style_settings(values):
    settings = {field: values[field] for field in BAR_STYLE_FIELDS}
    custom_texture_path = st.session_state.get(CUSTOM_TEXTURE_PATH_STATE)

    if custom_texture_path:
        settings["bar_texture_custom_image"] = custom_texture_path

    return settings


def _custom_texture_upload(bar_style):
    texture_active = (
        bar_style["bar_texture_enabled"]
        or bar_style["bar_fill_type"] == "texture"
    )
    if (
        not texture_active
        or bar_style["bar_texture_preset"] != "custom_image"
    ):
        st.session_state.pop(CUSTOM_TEXTURE_PATH_STATE, None)
        return bar_style

    uploaded_texture = st.file_uploader(
        "Upload custom bar texture",
        type=["png", "jpg", "jpeg", "webp"],
        key=_widget_key("custom_bar_texture_upload"),
    )

    if uploaded_texture is not None:
        source_name = Path(uploaded_texture.name).name
        suffix = Path(source_name).suffix.lower()
        safe_stem = _safe_filename_key(Path(source_name).stem) or "bar_texture"
        layout = _current_workspace_layout()
        project_root = _writable_project_root(layout, hint=safe_stem)
        texture_dir = assert_user_write_path(
            project_root / "assets" / "textures",
            app_root=layout.app_root,
            workspace_root=layout.workspace_root,
            operation="Texture upload",
        )
        texture_dir.mkdir(parents=True, exist_ok=True)
        texture_path = texture_dir / f"{safe_stem}{suffix}"
        texture_path.write_bytes(uploaded_texture.getbuffer())
        relative_path = _project_relative_path(
            texture_path,
            project_root=project_root,
        )
        st.session_state[CUSTOM_TEXTURE_PATH_STATE] = relative_path
        bar_style["bar_texture_custom_image"] = relative_path
        st.caption(f"Custom texture: {relative_path}")
    elif st.session_state.get(CUSTOM_TEXTURE_PATH_STATE):
        bar_style["bar_texture_custom_image"] = st.session_state[
            CUSTOM_TEXTURE_PATH_STATE
        ]

    return bar_style


def _preview_controls(csv_path, year_column, years=None):
    if years is None:
        try:
            years = year_values(csv_path, year_column)
        except (OSError, ValueError) as exc:
            st.error(str(exc))
            years = ()

    if not years:
        return {
            "year": None,
            "preview_mode": "year",
            "transition_progress": 0.0,
            "force_fun_fact_id": None,
        }

    with st.expander("Preview frame", icon=":material/preview:"):
        mode = st.segmented_control(
            "Mode",
            ("Year", "Transition"),
            default="Year",
            key=_widget_key("preview_mode"),
            disabled=len(years) < 2,
        )

        if mode == "Transition" and len(years) > 1:
            year_options = years[:-1]
            year = st.selectbox(
                "Start year",
                year_options,
                key=_widget_key("preview_start_year"),
            )
            progress = st.slider(
                "Transition progress",
                min_value=0.0,
                max_value=1.0,
                value=0.5,
                step=0.05,
                key=_widget_key("preview_transition_progress"),
            )

            return {
                "year": year,
                "preview_mode": "transition",
                "transition_progress": progress,
                "force_fun_fact_id": None,
            }

        year = st.selectbox(
            "Year",
            years,
            key=_widget_key("preview_year"),
        )

    return {
        "year": year,
        "preview_mode": "year",
        "transition_progress": 0.0,
        "force_fun_fact_id": None,
    }


def _render_preview(project_file, preview_settings, *, project_data=None):
    layout = _current_workspace_layout()
    project_root = _active_project_root(
        layout,
        project_name=(
            project_data.get("name")
            if isinstance(project_data, dict)
            else None
        ),
    )
    project_kind = st.session_state.get(ACTIVE_PROJECT_KIND_STATE, "scratch")
    if project_kind in {"legacy", "example"}:
        preview_root = (
            layout.scratch_root
            / "legacy_previews"
            / safe_slug(Path(str(project_file)).stem)
            / "output"
            / "previews"
        )
    else:
        preview_root = project_root / "output" / "previews"
    try:
        preview_root = assert_user_write_path(
            preview_root,
            app_root=layout.app_root,
            workspace_root=layout.workspace_root,
            operation="Preview render",
        )
        preview_root.mkdir(parents=True, exist_ok=True)
        preview_path = render_project_preview(
            project_root / project_file,
            output_dir=preview_root,
            year=preview_settings["year"],
            preview_mode=preview_settings["preview_mode"],
            transition_progress=preview_settings["transition_progress"],
            force_fun_fact_id=preview_settings.get("force_fun_fact_id"),
            root_dir=project_root,
            project_data=project_data,
            app_root=layout.app_root,
        )
    except (
        AppRootWriteError,
        ProjectFileError,
        ValueError,
        WorkspacePathError,
        OSError,
    ) as exc:
        st.error(str(exc))
        return None

    return preview_path


def _column_index(columns, selected):
    try:
        return tuple(columns).index(selected)
    except ValueError:
        return 0


def _option_index(options, selected):
    try:
        return tuple(options).index(selected)
    except ValueError:
        return 0


def _project_files(layout=None):
    layout = layout or _current_workspace_layout()
    return tuple(
        _project_option_value(location, layout)
        for location in discover_project_locations(layout)
    )


def _project_option_value(location, layout):
    if location.kind in {"production", "scratch"}:
        return location.absolute_path.relative_to(layout.workspace_root).as_posix()
    return location.absolute_path.relative_to(layout.app_root).as_posix()


def _project_option_label(value, layout):
    if not value:
        return "New project"
    try:
        return find_project_location(value, layout).label
    except WorkspacePathError:
        return str(value)


def _project_display_labels(locations, layout):
    """Return deterministic, name-first labels without changing option values."""
    locations = tuple(locations)
    stem_counts = {}
    for location in locations:
        key = location.absolute_path.stem.casefold()
        stem_counts[key] = stem_counts.get(key, 0) + 1

    labels = {}
    label_counts = {}
    for location in locations:
        value = _project_option_value(location, layout)
        name = location.absolute_path.stem
        kind = location.kind.title()
        if stem_counts[name.casefold()] > 1:
            context = _project_label_context(location, layout)
            label = f"{name} — {kind} / {context}"
        else:
            label = f"{name} — {kind}"
        labels[value] = label
        key = label.casefold()
        label_counts[key] = label_counts.get(key, 0) + 1

    for value, label in tuple(labels.items()):
        if label_counts[label.casefold()] > 1:
            labels[value] = f"{label} · {value}"
    return labels


def _project_label_context(location, layout):
    if location.kind in {"production", "scratch"}:
        return location.project_root.name
    try:
        relative = location.absolute_path.relative_to(layout.app_root)
    except ValueError:
        relative = Path(location.relative_path)
    parent = relative.parent.as_posix()
    return parent if parent not in {"", "."} else location.kind


def _active_project_root(
    layout,
    *,
    csv_path=None,
    project_name=None,
):
    current = st.session_state.get(ACTIVE_PROJECT_ROOT_STATE)
    if current:
        return Path(current).resolve(strict=False)

    if csv_path:
        candidate = Path(str(csv_path))
        legacy_source = (
            candidate.resolve(strict=False)
            if candidate.is_absolute()
            else (layout.app_root / candidate).resolve(strict=False)
        )
        if legacy_source.is_file() and legacy_source.is_relative_to(layout.app_root):
            st.session_state[ACTIVE_PROJECT_ROOT_STATE] = str(layout.app_root)
            st.session_state[ACTIVE_PROJECT_KIND_STATE] = "legacy"
            return layout.app_root

    hint = project_name or (Path(str(csv_path)).stem if csv_path else "project")
    slug = safe_slug(hint)
    root = layout.scratch_root / slug
    st.session_state[ACTIVE_PROJECT_ROOT_STATE] = str(root)
    st.session_state[ACTIVE_PROJECT_KIND_STATE] = "scratch"
    st.session_state[NEW_PROJECT_ROOT_STATE] = str(root)
    return root


def _writable_project_root(layout, *, hint, force_new=False):
    current = st.session_state.get(ACTIVE_PROJECT_ROOT_STATE)
    kind = st.session_state.get(ACTIVE_PROJECT_KIND_STATE)
    if current and kind in {"production", "scratch"} and not force_new:
        root = Path(current).resolve(strict=False)
        assert_user_write_path(
            root,
            app_root=layout.app_root,
            workspace_root=layout.workspace_root,
            operation="Project content",
        )
        initialize_workspace(layout.workspace_root, app_root=layout.app_root)
        root.mkdir(parents=True, exist_ok=True)
        return root

    initialize_workspace(layout.workspace_root, app_root=layout.app_root)
    preserve_legacy_root = bool(
        current
        and kind in {"legacy", "example"}
        and not force_new
    )
    base = safe_slug(hint)
    candidate = layout.scratch_root / base
    suffix = 2
    while (candidate / "project.json").exists() and not preserve_legacy_root:
        candidate = layout.scratch_root / f"{base}_{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=True)
    if not preserve_legacy_root:
        st.session_state[ACTIVE_PROJECT_ROOT_STATE] = str(candidate)
        st.session_state[ACTIVE_PROJECT_KIND_STATE] = "scratch"
        st.session_state[NEW_PROJECT_ROOT_STATE] = str(candidate)
    return candidate


def _rebase_legacy_project_data(project_data, *, source_root):
    rebased = copy.deepcopy(project_data)
    data_source = rebased.get("data_source")
    if isinstance(data_source, dict):
        for field in ("csv_path", "sqlite_database_path"):
            _make_legacy_reference_absolute(data_source, field, source_root)

    chart = rebased.setdefault("chart", {})
    for field in (
        "background_image_path",
        "bar_texture_custom_image",
        "logos_dir",
    ):
        _make_legacy_reference_absolute(chart, field, source_root)
    defaults = default_project_paths(
        safe_slug(rebased.get("name") or "legacy_project")
    )
    chart["output_file"] = defaults["output_file"]
    chart["frames_dir"] = defaults["frames_dir"]

    dataset = rebased.get("dataset")
    if isinstance(dataset, dict):
        for field in ("category_logos", "category_secondary_logos"):
            mapping = dataset.get(field)
            if isinstance(mapping, dict):
                for key, value in tuple(mapping.items()):
                    mapping[key] = _absolute_legacy_reference(value, source_root)

    fun_facts = rebased.get("fun_facts")
    if isinstance(fun_facts, dict):
        _make_legacy_reference_absolute(fun_facts, "source", source_root)
    return rebased


def _make_legacy_reference_absolute(container, field, source_root):
    value = container.get(field)
    if value:
        container[field] = _absolute_legacy_reference(value, source_root)


def _absolute_legacy_reference(value, source_root):
    path = Path(str(value))
    if path.is_absolute():
        return str(path.resolve())
    return str((Path(source_root) / path).resolve())


def _reset_workspace_project_state():
    for key in (
        "loaded_project_data",
        "loaded_project_path",
        LOADED_PROJECT_IDENTIFIER_STATE,
        ACTIVE_PROJECT_ROOT_STATE,
        NEW_PROJECT_ROOT_STATE,
    ):
        st.session_state.pop(key, None)
    st.session_state[ACTIVE_PROJECT_KIND_STATE] = "scratch"
    _reset_project_editor_state()


def _open_workspace_folder(path):
    path = Path(path).resolve(strict=True)
    if os.name == "nt":
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            raise OSError("Windows folder opening is unavailable.")
        startfile(str(path))
        return
    command = ["open", str(path)] if sys.platform == "darwin" else ["xdg-open", str(path)]
    subprocess.Popen(command, start_new_session=True)


def _logo_files(logos_dir=DEFAULT_LOGO_FOLDER):
    logos_dir = _resolve_project_path(logos_dir)

    if not logos_dir.exists():
        return ()

    return tuple(
        _project_relative_path(path)
        for path in sorted(logos_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in LOGO_FILE_EXTENSIONS
    )


def _logo_options(current_logo, logo_files):
    options = ["", *logo_files]

    if current_logo and current_logo not in options:
        options.insert(1, current_logo)

    return tuple(options)


def _save_uploaded_logo(raw_name, uploaded_logo, *, slot="primary"):
    layout = _current_workspace_layout()
    project_root = _writable_project_root(layout, hint=raw_name)
    folder = "logos_secondary" if slot == "secondary" else "logos"
    logos_dir = assert_user_write_path(
        project_root / "assets" / folder,
        app_root=layout.app_root,
        workspace_root=layout.workspace_root,
        operation="Logo upload",
    )
    logos_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(uploaded_logo.name).suffix.lower()

    if suffix not in LOGO_FILE_EXTENSIONS:
        suffix = ".png"

    suffix_label = "_secondary" if slot == "secondary" else ""
    logo_path = logos_dir / (
        f"{_safe_filename_key(raw_name)}{suffix_label}{suffix}"
    )
    logo_path.write_bytes(uploaded_logo.getbuffer())

    return _project_relative_path(logo_path, project_root=project_root)


def _save_uploaded_logo_folder(uploaded_logo_files, *, slot="primary"):
    folder_name = _uploaded_folder_name(uploaded_logo_files)
    folder_key = _safe_filename_key(folder_name)
    default_folder = (
        DEFAULT_SECONDARY_LOGO_FOLDER
        if slot == "secondary"
        else DEFAULT_LOGO_FOLDER
    )
    layout = _current_workspace_layout()
    project_root = _writable_project_root(layout, hint=folder_key)
    target_dir = assert_user_write_path(
        project_root / default_folder,
        app_root=layout.app_root,
        workspace_root=layout.workspace_root,
        operation="Logo folder upload",
    )

    if folder_key != default_folder:
        target_dir = target_dir / folder_key

    target_dir.mkdir(parents=True, exist_ok=True)

    for uploaded_logo_file in uploaded_logo_files:
        suffix = Path(uploaded_logo_file.name).suffix.lower()

        if suffix not in LOGO_FILE_EXTENSIONS:
            continue

        logo_path = target_dir / _safe_logo_filename(uploaded_logo_file.name)
        logo_path.write_bytes(uploaded_logo_file.getbuffer())

    return _project_relative_path(target_dir, project_root=project_root)


def _uploaded_folder_name(uploaded_logo_files):
    for uploaded_logo_file in uploaded_logo_files:
        parts = PurePosixPath(str(uploaded_logo_file.name).replace("\\", "/")).parts

        if len(parts) > 1:
            return parts[0]

    return "uploaded_logos"


def _safe_logo_filename(uploaded_name):
    filename = PurePosixPath(str(uploaded_name).replace("\\", "/")).name
    suffix = Path(filename).suffix.lower()

    if suffix not in LOGO_FILE_EXTENSIONS:
        suffix = ".png"

    return f"{_safe_filename_key(Path(filename).stem)}{suffix}"


def _resolve_project_path(path):
    path = Path(str(path).strip() or DEFAULT_LOGO_FOLDER)

    if not path.is_absolute():
        path = _active_project_root(_current_workspace_layout()) / path

    return path


def _project_relative_path(path, *, project_root=None):
    active_root = _active_project_root(_current_workspace_layout())
    root = Path(project_root or active_root).resolve()
    resolved_path = Path(path).resolve()
    if project_root is not None and root != active_root:
        return str(resolved_path).replace("\\", "/")
    try:
        return str(resolved_path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _widget_key(name):
    return f"{name}_{st.session_state.get('form_version', 0)}"


def _set_session_value(key, value):
    st.session_state[key] = value


def _use_full_vertical_area():
    st.session_state[_widget_key("bar_vertical_layout_mode")] = "fill_available"
    st.session_state[_widget_key("bar_vertical_top_padding")] = 0
    st.session_state[_widget_key("bar_vertical_bottom_padding")] = 0


def _safe_filename_key(value):
    safe_value = "".join(
        character if character.isalnum() else "_"
        for character in str(value).lower()
    ).strip("_")
    return safe_value or "category"


def _safe_widget_key(value, index):
    return f"{index}_{_safe_filename_key(value)}"


def _refresh_form():
    st.session_state["form_version"] = st.session_state.get("form_version", 0) + 1


def _positive_int_or_default(value, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default

    return value if value >= 1 else default


def _font_size_input(label, value, default, key):
    return st.number_input(
        label,
        min_value=1,
        max_value=500,
        value=_int_in_range_or_default(value, default, 1, 500),
        step=1,
        key=key,
    )


def _color_or_default(value, default):
    value = str(value or "").strip()

    if (
        len(value) == 7
        and value.startswith("#")
        and all(character in "0123456789abcdefABCDEF" for character in value[1:])
    ):
        return value.upper()

    return default


def _opacity_or_default(value, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return float(default)

    return min(1.0, max(0.0, value))


def _opacity_percent_slider(label, value, default, key, *, disabled=False):
    percent = st.slider(
        label,
        min_value=0,
        max_value=100,
        value=round(_opacity_or_default(value, default) * 100),
        format="%d%%",
        key=key,
        disabled=disabled,
        help="Base text opacity. Animation and fade opacity are multiplied afterward.",
    )
    return percent / 100.0


def _drop_widget_value_outside_range(key, minimum, maximum):
    if key not in st.session_state:
        return
    try:
        value = float(st.session_state[key])
    except (TypeError, ValueError):
        st.session_state.pop(key, None)
        return
    if value < minimum or value > maximum:
        st.session_state.pop(key, None)


def _int_in_range_or_default(value, default, minimum, maximum):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default

    return min(maximum, max(minimum, value))


if __name__ == "__main__":
    main()
