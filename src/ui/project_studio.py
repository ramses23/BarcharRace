import copy
import sys
from pathlib import Path, PurePosixPath

import pandas as pd
import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config.layout_config import get_layout_preset, list_layout_presets
from config.project_file_loader import ProjectFileError
from config.theme_config import get_theme
from config.typography_config import get_typography_preset
from config.value_format_config import list_value_formats
from studio.preview import render_project_preview
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
from ui.font_picker import font_family_picker
from ui.render_workflow import (
    BACKGROUND_RENDER_STATE,
    LAST_PREFLIGHT_STATE,
    LAST_RENDER_STATUS_STATE,
    render_workflow_panel,
    start_render_with_preflight,
)
from ui.text_layout_editor import text_layout_editor
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
DEFAULT_LOGO_FOLDER = "logos"
DEFAULT_SECONDARY_LOGO_FOLDER = "logos_secondary"
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
CATEGORY_STYLE_DRAFT_STATE = "category_style_draft"
CURRENT_DRAFT_FINGERPRINT_STATE = "current_project_draft_fingerprint"
CURRENT_DRAFT_STATE = "current_project_draft"
PENDING_PROJECT_ACTION_STATE = "pending_project_action"
PROJECT_BUNDLE_EXPORT_STATE = "project_bundle_export"
LAST_BUNDLE_IMPORT_STATE = "last_project_bundle_import"


st.set_page_config(
    page_title="BarChartStudio",
    page_icon="B",
    layout="wide",
)


def main():
    _initialize_studio_state()
    st.title("BarChartStudio")
    st.caption("Build, style, preview, and export animated bar chart races.")

    with st.sidebar:
        _project_source_panel()

        loaded_project_data = st.session_state.get("loaded_project_data")
        loaded_project_path = st.session_state.get("loaded_project_path")
        values = project_form_values(loaded_project_data)

        csv_path = _csv_source_panel(values, loaded_project_data)

    if not csv_path:
        return

    _refresh_new_project_form_on_csv_change(csv_path, loaded_project_data)
    values = _project_values_for_csv(values, csv_path, loaded_project_data)

    try:
        dataset = load_csv_dataset(csv_path)
        inspection = inspect_dataframe(dataset, path=csv_path)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.error(str(exc))
        return

    with st.expander("Dataset preview"):
        st.caption(f"{inspection.row_count:,} rows · {len(inspection.columns):,} columns")
        preview_df = dataset.head(12)
        st.dataframe(preview_df, width="stretch", hide_index=True)

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
    _project_actions(draft)
    render_workflow_panel()
    _show_persistent_preview(draft)

    with st.expander("Generated project JSON"):
        st.json(project_data, expanded=True)


def _initialize_studio_state():
    st.session_state.setdefault("form_version", 0)
    st.session_state.setdefault(SAVED_DRAFT_FINGERPRINT_STATE, None)
    st.session_state.setdefault(SAVED_DRAFT_PENDING_STATE, False)
    st.session_state.setdefault(LAST_PREVIEW_STATE, None)
    st.session_state.setdefault(CURRENT_DRAFT_FINGERPRINT_STATE, None)
    st.session_state.setdefault(CURRENT_DRAFT_STATE, None)
    st.session_state.setdefault(PENDING_PROJECT_ACTION_STATE, None)
    st.session_state.setdefault(BACKGROUND_RENDER_STATE, None)
    st.session_state.setdefault(LAST_RENDER_STATUS_STATE, None)
    st.session_state.setdefault(LAST_PREFLIGHT_STATE, None)
    st.session_state.setdefault(PROJECT_BUNDLE_EXPORT_STATE, None)
    st.session_state.setdefault(LAST_BUNDLE_IMPORT_STATE, None)


def _initialize_saved_draft(draft):
    pending = st.session_state.get(SAVED_DRAFT_PENDING_STATE, False)

    if pending:
        st.session_state[SAVED_DRAFT_FINGERPRINT_STATE] = draft.fingerprint
        st.session_state[SAVED_DRAFT_PENDING_STATE] = False


def _project_actions(draft):
    background_render = st.session_state.get(BACKGROUND_RENDER_STATE)
    render_active = bool(
        background_render is not None and background_render.is_running()
    )
    save_column, preview_column, render_column = st.columns(3)
    save_project = save_column.button(
        "Save project",
        icon=":material/save:",
        width="stretch",
    )
    render_preview = preview_column.button(
        "Render preview",
        icon=":material/visibility:",
        width="stretch",
    )
    render_video = render_column.button(
        "Render video",
        icon=":material/movie:",
        type="primary",
        width="stretch",
        disabled=render_active,
    )

    if save_project:
        _save_draft(draft)

    if render_preview:
        _save_draft(draft, show_success=False)
        preview_path = _render_preview(
            draft.project_file,
            draft.preview_settings,
        )

        if preview_path is not None:
            st.session_state[LAST_PREVIEW_STATE] = {
                "path": str(preview_path),
                "fingerprint": draft.fingerprint,
            }

    if render_video:
        _save_draft(draft, show_success=False)
        start_render_with_preflight(draft.project_file, root_dir=ROOT_DIR)

    saved_fingerprint = st.session_state.get(SAVED_DRAFT_FINGERPRINT_STATE)
    if draft.is_dirty(saved_fingerprint):
        st.caption(":orange-badge[Unsaved changes] Save before closing the app.")
    else:
        st.caption(f":green-badge[Saved] {draft.project_file}")

    _portable_bundle_export_panel(draft, render_active=render_active)


def _portable_bundle_export_panel(draft, *, render_active):
    with st.expander("Portable project bundle"):
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
            _save_draft(draft, show_success=False)
            try:
                with st.spinner("Collecting project files..."):
                    exported = build_project_bundle(
                        draft.project_data,
                        root_dir=ROOT_DIR,
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
        return

    preview_path = Path(str(preview.get("path", "")))

    if not preview_path.is_file():
        st.session_state[LAST_PREVIEW_STATE] = None
        return

    with st.container(border=True):
        st.subheader("Latest preview")

        if preview.get("fingerprint") != draft.fingerprint:
            st.warning(
                "This preview is out of date. Render it again to include "
                "the current unsaved changes.",
                icon=":material/update:",
            )

        st.image(str(preview_path), width="stretch")


def _project_source_panel():
    st.subheader("Project")
    _pending_project_action_panel()
    project_files = _project_files()
    project_options = ("", *project_files)
    current_project = st.session_state.get("loaded_project_path", "")
    selected_project = st.selectbox(
        "Open project",
        project_options,
        index=_option_index(project_options, current_project),
        format_func=lambda path: "New project" if not path else path,
    )
    load_column, new_column = st.columns(2)
    background_render = st.session_state.get(BACKGROUND_RENDER_STATE)
    render_active = bool(
        background_render is not None and background_render.is_running()
    )

    with load_column:
        if st.button(
            "Load project",
            width="stretch",
            disabled=not selected_project or render_active,
        ):
            _request_project_action("load", project=selected_project)

    with new_column:
        if st.button(
            "New project",
            width="stretch",
            disabled=render_active,
        ):
            _request_project_action("new")

    if render_active:
        st.caption("Project switching is disabled while a render is active.")

    if st.session_state.get("loaded_project_path"):
        st.caption(f"Editing {st.session_state['loaded_project_path']}")

    _portable_bundle_import_panel(render_active=render_active)


def _portable_bundle_import_panel(*, render_active):
    with st.expander("Import portable ZIP"):
        imported = st.session_state.get(LAST_BUNDLE_IMPORT_STATE)
        if isinstance(imported, dict):
            st.success(
                f"Imported {imported.get('project', 'project bundle')}",
                icon=":material/inventory_2:",
            )
            st.caption(
                f"{imported.get('files', 0):,} verified files · "
                f"{format_file_size(imported.get('uncompressed_size', 0))} unpacked"
            )

        uploaded = st.file_uploader(
            "Project bundle",
            type=["zip"],
            help="Select a .barchart.zip file exported by BarChartStudio.",
            key=_widget_key("project_bundle_upload"),
        )
        if st.button(
            "Import and open",
            icon=":material/unarchive:",
            width="stretch",
            disabled=uploaded is None or render_active,
            key="import_project_bundle",
        ):
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

    st.warning("You have unsaved changes. Save them before continuing, or discard them.")
    discard_column, keep_column = st.columns(2)
    if discard_column.button(
        "Discard & continue",
        type="primary",
        width="stretch",
        key="discard_pending_project_action",
    ):
        st.session_state[PENDING_PROJECT_ACTION_STATE] = None
        _execute_project_action(pending_action)

    if keep_column.button(
        "Keep editing",
        width="stretch",
        key="cancel_pending_project_action",
    ):
        current_draft = pending_action.get("draft")
        if isinstance(current_draft, dict) and isinstance(
            current_draft.get("project_data"),
            dict,
        ):
            st.session_state["loaded_project_data"] = copy.deepcopy(
                current_draft["project_data"]
            )
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
    try:
        imported = import_project_bundle(bundle, root_dir=ROOT_DIR)
    except (OSError, ValueError, ProjectBundleError) as exc:
        st.error(f"Could not import {filename}: {exc}")
        return

    project_path = _project_relative_path(Path(imported.project_path))
    st.session_state[LAST_BUNDLE_IMPORT_STATE] = {
        "project": project_path,
        "files": imported.file_count,
        "uncompressed_size": imported.uncompressed_size,
    }
    _load_selected_project(project_path, preserve_bundle_import=True)


def _load_selected_project(selected_project, *, preserve_bundle_import=False):
    try:
        project_data = load_project_data(ROOT_DIR / selected_project)
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        return

    st.session_state["loaded_project_data"] = project_data
    st.session_state["loaded_project_path"] = selected_project
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
    st.session_state[LAST_PREFLIGHT_STATE] = None
    st.session_state[LAST_RENDER_STATUS_STATE] = None
    st.session_state[PROJECT_BUNDLE_EXPORT_STATE] = None
    st.session_state.pop(CATEGORY_STYLE_DRAFT_STATE, None)
    _clear_logo_session_overrides()


def _has_unsaved_draft():
    current_fingerprint = st.session_state.get(CURRENT_DRAFT_FINGERPRINT_STATE)
    saved_fingerprint = st.session_state.get(SAVED_DRAFT_FINGERPRINT_STATE)
    return bool(
        current_fingerprint
        and current_fingerprint != saved_fingerprint
    )


def _csv_source_panel(values, loaded_project_data):
    st.subheader("Dataset")
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
        datasets_dir = ROOT_DIR / "data" / "datasets"
        datasets_dir.mkdir(parents=True, exist_ok=True)
        csv_path = datasets_dir / uploaded_file.name
        csv_path.write_bytes(uploaded_file.getbuffer())
        csv_path = str(csv_path.relative_to(ROOT_DIR))

        if not loaded_project_data:
            st.session_state[NEW_PROJECT_CSV_PATH_OVERRIDE_STATE] = csv_path

        return csv_path

    return st.text_input("CSV path", value=default_csv, key=_widget_key("csv_path"))


def _project_form(
    csv_path,
    inspection,
    values,
    loaded_project_data,
    loaded_project_path,
    dataset,
):
    theme, theme_settings = _resolved_theme(values)
    typography_preset, typography_settings = _resolved_typography(values)
    data_tab, canvas_tab, bars_tab, animation_tab = st.tabs((
        "1. Data & content",
        "2. Canvas & text",
        "3. Bars & categories",
        "4. Animation & output",
    ))

    with data_tab:
        data_settings = _data_content_section(
            csv_path,
            inspection,
            values,
            dataset,
        )

    paths = default_project_paths(data_settings["project_name"])

    with canvas_tab:
        canvas_settings = _canvas_text_section(
            values=values,
            title=data_settings["title"],
            source_label=data_settings["source_label"],
            theme_settings=theme_settings,
            typography_settings=typography_settings,
        )

    with bars_tab:
        bars_settings = _bars_categories_section(
            csv_path=csv_path,
            name_column=data_settings["name_column"],
            values=values,
            theme_settings=theme_settings,
            background_color=canvas_settings["background"]["color"],
            dataset=dataset,
        )

    with animation_tab:
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
        typography_preset=typography_preset,
        value_format=bars_settings["value_format"],
        fps=render_settings["fps"],
        steps_per_transition=render_settings["steps"],
        top_n=bars_settings["top_n"],
        max_visible_bars=canvas_settings["max_visible"],
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
        subtitle_text_color=canvas_settings["subtitle_text_color"],
        label_text_color=canvas_settings["label_text_color"],
        value_text_color=canvas_settings["value_text_color"],
        time_label_text_color=canvas_settings["time_label_text_color"],
        source_text_color=canvas_settings["source_text_color"],
        rank_label_text_color=canvas_settings["rank_label_text_color"],
        title_font_size=canvas_settings["title_font_size"],
        subtitle_font_size=canvas_settings["subtitle_font_size"],
        label_font_size=canvas_settings["label_font_size"],
        value_font_size=canvas_settings["value_font_size"],
        time_label_font_size=canvas_settings["time_label_font_size"],
        source_font_size=canvas_settings["source_font_size"],
        rank_label_font_size=canvas_settings["rank_label_font_size"],
        title_x=canvas_settings["title_x"],
        title_y=canvas_settings["title_y"],
        subtitle_x=canvas_settings["subtitle_x"],
        subtitle_y=canvas_settings["subtitle_y"],
        time_label_x=canvas_settings["time_label_x"],
        time_label_y=canvas_settings["time_label_y"],
        source_x=canvas_settings["source_x"],
        source_y=canvas_settings["source_y"],
        aggregate_other=bars_settings["aggregate_other"],
        category_styles=bars_settings["category_styles"],
        base_project_data=loaded_project_data,
    )

    return (
        project_data,
        render_settings["project_file"],
        render_settings["preview_settings"],
    )


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


def _data_content_section(csv_path, inspection, values, dataset):
    st.caption("Name the project, map the CSV columns, and define source text.")
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
    st.caption("Configure the canvas, background, fonts, sizes, and text placement.")
    layout_column, visible_column = st.columns(2)
    layouts = list_layout_presets()

    with layout_column:
        layout_preset = st.selectbox(
            "Canvas layout",
            layouts,
            index=_option_index(layouts, values["layout_preset"]),
            key=_widget_key("layout_preset"),
        )

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

    with st.expander("Fonts", expanded=True):
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

    with st.expander("Text sizes"):
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

    with st.expander("Text colors"):
        st.caption("Each text element can override the colors inherited from the project.")
        color_column_a, color_column_b, color_column_c, color_column_d = st.columns(4)

        with color_column_a:
            title_text_color = st.color_picker(
                "Title color",
                value=_color_or_default(
                    values["title_text_color"],
                    theme_settings.text_color,
                ),
                key=_widget_key("title_text_color"),
            )
            subtitle_text_color = st.color_picker(
                "Subtitle color",
                value=_color_or_default(
                    values["subtitle_text_color"],
                    theme_settings.muted_text_color,
                ),
                key=_widget_key("subtitle_text_color"),
            )

        with color_column_b:
            label_text_color = st.color_picker(
                "Category color",
                value=_color_or_default(
                    values["label_text_color"],
                    theme_settings.text_color,
                ),
                key=_widget_key("label_text_color"),
            )
            value_text_color = st.color_picker(
                "Value color",
                value=_color_or_default(
                    values["value_text_color"],
                    theme_settings.muted_text_color,
                ),
                key=_widget_key("value_text_color"),
            )

        with color_column_c:
            time_label_text_color = st.color_picker(
                "Date color",
                value=_color_or_default(
                    values["time_label_text_color"],
                    theme_settings.muted_text_color,
                ),
                key=_widget_key("time_label_text_color"),
            )
            source_text_color = st.color_picker(
                "Source color",
                value=_color_or_default(
                    values["source_text_color"],
                    theme_settings.muted_text_color,
                ),
                key=_widget_key("source_text_color"),
            )

        with color_column_d:
            rank_label_text_color = st.color_picker(
                "Ranking color",
                value=_color_or_default(
                    values["rank_label_text_color"],
                    theme_settings.muted_text_color,
                ),
                key=_widget_key("rank_label_text_color"),
            )

    with st.expander("Text placement"):
        position_values = text_layout_editor(
            canvas_width=layout_settings.width,
            canvas_height=layout_settings.height,
            dpi=values["dpi"],
            positions={
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
            },
            preset_positions={
                "title": {"x": layout_settings.left_margin, "y": layout_settings.title_y},
                "subtitle": {"x": layout_settings.left_margin, "y": layout_settings.subtitle_y},
                "date": {"x": layout_settings.time_label_x, "y": layout_settings.time_label_y},
                "source": {"x": layout_settings.source_x, "y": layout_settings.source_y},
            },
            elements={
                "title": {
                    "label": "Title",
                    "text": title or "Title",
                    "font_family": title_font_family,
                    "font_size": int(title_font_size),
                    "font_weight": typography_settings.title_font_weight,
                    "color": title_text_color,
                },
                "subtitle": {
                    "label": "Subtitle",
                    "text": "Period A -> Period B",
                    "font_family": subtitle_font_family,
                    "font_size": int(subtitle_font_size),
                    "font_weight": typography_settings.subtitle_font_weight,
                    "color": subtitle_text_color,
                },
                "date": {
                    "label": "Date",
                    "text": "2024",
                    "font_family": time_label_font_family,
                    "font_size": int(time_label_font_size),
                    "font_weight": typography_settings.time_label_font_weight,
                    "color": time_label_text_color,
                    "opacity": 0.22,
                },
                "source": {
                    "label": "Source",
                    "text": source_label or "Source",
                    "font_family": source_font_family,
                    "font_size": int(source_font_size),
                    "font_weight": typography_settings.source_font_weight,
                    "color": source_text_color,
                },
            },
            theme={
                "background_color": background["color"],
                "font_family": theme_settings.font_family,
                "bar_color": theme_settings.bar_palette[0],
            },
            layout={
                "left_margin": layout_settings.left_margin,
                "right_margin": layout_settings.right_margin,
                "top_margin": layout_settings.top_margin,
                "bottom_margin": layout_settings.bottom_margin,
                "bar_height": layout_settings.bar_height,
                "bar_count": int(max_visible),
            },
            key=_widget_key("text_layout_editor"),
        )

    return {
        "layout_preset": layout_preset,
        "max_visible": int(max_visible),
        "background": background,
        "title_font_family": title_font_family,
        "subtitle_font_family": subtitle_font_family,
        "label_font_family": label_font_family,
        "value_font_family": value_font_family,
        "time_label_font_family": time_label_font_family,
        "source_font_family": source_font_family,
        "rank_label_font_family": rank_label_font_family,
        "title_text_color": title_text_color,
        "subtitle_text_color": subtitle_text_color,
        "label_text_color": label_text_color,
        "value_text_color": value_text_color,
        "time_label_text_color": time_label_text_color,
        "source_text_color": source_text_color,
        "rank_label_text_color": rank_label_text_color,
        "title_font_size": int(title_font_size),
        "subtitle_font_size": int(subtitle_font_size),
        "label_font_size": int(label_font_size),
        "value_font_size": int(value_font_size),
        "time_label_font_size": int(time_label_font_size),
        "source_font_size": int(source_font_size),
        "rank_label_font_size": int(rank_label_font_size),
        "title_x": int(position_values["title"]["x"]),
        "title_y": int(position_values["title"]["y"]),
        "subtitle_x": int(position_values["subtitle"]["x"]),
        "subtitle_y": int(position_values["subtitle"]["y"]),
        "time_label_x": int(position_values["date"]["x"]),
        "time_label_y": int(position_values["date"]["y"]),
        "source_x": int(position_values["source"]["x"]),
        "source_y": int(position_values["source"]["y"]),
    }


def _bars_categories_section(
    *,
    csv_path,
    name_column,
    values,
    theme_settings,
    background_color,
    dataset,
):
    st.caption("Control ranking, number formatting, bar materials, icons, and categories.")
    format_column, ranking_column, aggregate_column = st.columns(3)
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
        aggregate_other = st.checkbox(
            "Group remaining as Other",
            value=bool(values["aggregate_other"]),
            key=_widget_key("aggregate_other"),
        )

    with st.expander("Bar appearance", expanded=True):
        st.caption(
            "Shape, material, icon placement, label alignment, borders, and effects."
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
    st.caption("Set motion timing, review playback duration, and choose output files.")
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
            max_value=240,
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
        _show_video_duration_estimate(
            period_count=len(available_years),
            fps=int(fps),
            steps_per_transition=int(steps),
            motion_mode=motion_mode,
        )

    with st.expander("Export settings"):
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

    with st.expander("Output files", expanded=True):
        output_column, project_column = st.columns(2)

        with output_column:
            output_file = st.text_input(
                "Output MP4",
                value=values["output_file"] or paths["output_file"],
                key=_widget_key("output_file"),
            )

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
    }


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

    with st.expander("Categories"):
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
    path = save_project_data(
        draft.project_data,
        ROOT_DIR / draft.project_file,
    )
    st.session_state[SAVED_DRAFT_FINGERPRINT_STATE] = draft.fingerprint
    st.session_state[SAVED_DRAFT_PENDING_STATE] = False
    st.session_state["loaded_project_data"] = copy.deepcopy(draft.project_data)
    st.session_state["loaded_project_path"] = draft.project_file

    if show_success:
        try:
            display_path = path.resolve().relative_to(ROOT_DIR.resolve())
        except ValueError:
            display_path = path

        st.success(f"Saved {display_path}")

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

    with st.expander("Background"):
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
                background_dir = ROOT_DIR / "backgrounds"
                background_dir.mkdir(parents=True, exist_ok=True)
                background_path = background_dir / f"{safe_stem}{suffix}"
                background_path.write_bytes(uploaded_background.getbuffer())
                current_image_path = _project_relative_path(background_path)
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
                    preview_path = ROOT_DIR / preview_path

                if preview_path.is_file():
                    st.image(str(preview_path), width=320)
                else:
                    st.warning("The selected background image could not be found.")
            else:
                st.info("Upload an image or enter its path.")
        elif current_image_path:
            st.caption("The selected image is preserved for switching back to Image mode.")

    return {
        "mode": mode,
        "color": color,
        "image_path": current_image_path or None,
        "image_fit": image_fit,
    }


def _show_video_duration_estimate(
    *,
    period_count,
    fps,
    steps_per_transition,
    motion_mode,
):
    estimate = estimate_video_duration(
        period_count=period_count,
        steps_per_transition=steps_per_transition,
        fps=fps,
        continuous_motion=motion_mode == "continuous",
    )
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
    if (
        bar_style["bar_appearance_mode"] != "advanced"
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
        texture_dir = ROOT_DIR / "textures"
        texture_dir.mkdir(parents=True, exist_ok=True)
        texture_path = texture_dir / f"{safe_stem}{suffix}"
        texture_path.write_bytes(uploaded_texture.getbuffer())
        relative_path = _project_relative_path(texture_path)
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
        }

    with st.expander("Preview", expanded=True):
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
    }


def _render_preview(project_file, preview_settings):
    try:
        preview_path = render_project_preview(
            ROOT_DIR / project_file,
            year=preview_settings["year"],
            preview_mode=preview_settings["preview_mode"],
            transition_progress=preview_settings["transition_progress"],
        )
    except (ProjectFileError, ValueError, OSError) as exc:
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


def _project_files():
    projects_dir = ROOT_DIR / "projects"

    if not projects_dir.exists():
        return ()

    return tuple(
        str(path.relative_to(ROOT_DIR))
        for path in sorted(projects_dir.glob("*.json"))
    )


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
    logos_dir = ROOT_DIR / "logos"
    logos_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(uploaded_logo.name).suffix.lower()

    if suffix not in LOGO_FILE_EXTENSIONS:
        suffix = ".png"

    suffix_label = "_secondary" if slot == "secondary" else ""
    logo_path = logos_dir / (
        f"{_safe_filename_key(raw_name)}{suffix_label}{suffix}"
    )
    logo_path.write_bytes(uploaded_logo.getbuffer())

    return _project_relative_path(logo_path)


def _save_uploaded_logo_folder(uploaded_logo_files, *, slot="primary"):
    folder_name = _uploaded_folder_name(uploaded_logo_files)
    folder_key = _safe_filename_key(folder_name)
    default_folder = (
        DEFAULT_SECONDARY_LOGO_FOLDER
        if slot == "secondary"
        else DEFAULT_LOGO_FOLDER
    )
    target_dir = ROOT_DIR / default_folder

    if folder_key != default_folder:
        target_dir = target_dir / folder_key

    target_dir.mkdir(parents=True, exist_ok=True)

    for uploaded_logo_file in uploaded_logo_files:
        suffix = Path(uploaded_logo_file.name).suffix.lower()

        if suffix not in LOGO_FILE_EXTENSIONS:
            continue

        logo_path = target_dir / _safe_logo_filename(uploaded_logo_file.name)
        logo_path.write_bytes(uploaded_logo_file.getbuffer())

    return _project_relative_path(target_dir)


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
        path = ROOT_DIR / path

    return path


def _project_relative_path(path):
    try:
        return str(path.relative_to(ROOT_DIR)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _widget_key(name):
    return f"{name}_{st.session_state.get('form_version', 0)}"


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


def _int_in_range_or_default(value, default, minimum, maximum):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default

    return min(maximum, max(minimum, value))


if __name__ == "__main__":
    main()
