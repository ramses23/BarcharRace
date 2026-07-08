import sys
from pathlib import Path, PurePosixPath
from subprocess import CalledProcessError

import pandas as pd
import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config.layout_config import list_layout_presets
from config.project_file_loader import ProjectFileError
from config.theme_config import list_themes
from config.typography_config import list_typography_presets
from config.value_format_config import list_value_formats
from pipeline.render_job import RenderJob
from studio.preview import render_project_preview
from studio.project_builder import (
    build_project_data,
    category_values,
    default_project_paths,
    inspect_csv,
    load_project_data,
    match_category_logos,
    preferred_column,
    project_defaults_from_csv_path,
    project_form_values,
    project_name_from_title,
    save_project_data,
    year_values,
)
from config.project_file_loader import load_project_file


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
CATEGORY_DISPLAY_LIMIT = 80
LOGO_FOLDER_OVERRIDE_STATE = "category_logo_folder_override"
NEW_PROJECT_CSV_PATH_STATE = "new_project_csv_path"
NEW_PROJECT_CSV_PATH_OVERRIDE_STATE = "new_project_csv_path_override"


st.set_page_config(
    page_title="BarChartStudio",
    page_icon="B",
    layout="wide",
)


def main():
    st.title("BarChartStudio")

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
        inspection = inspect_csv(csv_path)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.error(str(exc))
        return

    st.caption(f"{inspection.row_count:,} rows")

    preview_df = pd.read_csv(csv_path, nrows=12)
    st.dataframe(preview_df, use_container_width=True, hide_index=True)

    project_data, project_file, preview_settings = _project_form(
        csv_path,
        inspection,
        values,
        loaded_project_data,
        loaded_project_path,
    )

    preview_column, render_column = st.columns(2)

    with preview_column:
        if st.button("Render preview", use_container_width=True):
            _save_project(project_data, project_file)
            _render_preview(project_file, preview_settings)

    with render_column:
        if st.button("Render video", type="primary", use_container_width=True):
            _save_project(project_data, project_file)
            _render_video(project_file)

    st.json(project_data, expanded=False)


def _project_source_panel():
    st.subheader("Project")
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

    with load_column:
        if st.button("Load project", use_container_width=True, disabled=not selected_project):
            try:
                project_data = load_project_data(ROOT_DIR / selected_project)
            except (OSError, ValueError) as exc:
                st.error(str(exc))
                return

            st.session_state["loaded_project_data"] = project_data
            st.session_state["loaded_project_path"] = selected_project
            st.session_state.pop(NEW_PROJECT_CSV_PATH_STATE, None)
            st.session_state.pop(NEW_PROJECT_CSV_PATH_OVERRIDE_STATE, None)
            st.session_state.pop(LOGO_FOLDER_OVERRIDE_STATE, None)
            _refresh_form()
            st.rerun()

    with new_column:
        if st.button("New project", use_container_width=True):
            st.session_state.pop("loaded_project_data", None)
            st.session_state.pop("loaded_project_path", None)
            st.session_state.pop(NEW_PROJECT_CSV_PATH_STATE, None)
            st.session_state.pop(NEW_PROJECT_CSV_PATH_OVERRIDE_STATE, None)
            st.session_state.pop(LOGO_FOLDER_OVERRIDE_STATE, None)
            _refresh_form()
            st.rerun()

    if st.session_state.get("loaded_project_path"):
        st.caption(f"Editing {st.session_state['loaded_project_path']}")


def _csv_source_panel(values, loaded_project_data):
    st.subheader("Dataset")
    uploaded_file = st.file_uploader("CSV file", type=["csv"])
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


def _project_form(csv_path, inspection, values, loaded_project_data, loaded_project_path):
    title = st.text_input("Title", value=values["title"], key=_widget_key("title"))
    project_name = st.text_input(
        "Project name",
        value=values["name"] or project_name_from_title(title),
        key=_widget_key("project_name"),
    )
    paths = default_project_paths(project_name)

    dataset_column, visual_column, render_column = st.columns(3)

    with dataset_column:
        year_column = st.selectbox(
            "Year column",
            inspection.columns,
            index=_column_index(
                inspection.columns,
                values["year_column"]
                or preferred_column(inspection.year_candidates, inspection.columns, "year"),
            ),
            key=_widget_key("year_column"),
        )
        name_column = st.selectbox(
            "Name column",
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
        value_column = st.selectbox(
            "Value column",
            inspection.columns,
            index=_column_index(
                inspection.columns,
                values["value_column"]
                or preferred_column(inspection.value_candidates, inspection.columns, "value"),
            ),
            key=_widget_key("value_column"),
        )
        source_label = st.text_input(
            "Source label",
            value=values["source_label"],
            key=_widget_key("source_label"),
        )

    with visual_column:
        layouts = list_layout_presets()
        themes = list_themes()
        typographies = list_typography_presets()
        value_formats = list_value_formats()

        layout_preset = st.selectbox(
            "Layout",
            layouts,
            index=_option_index(layouts, values["layout_preset"]),
            key=_widget_key("layout_preset"),
        )
        theme = st.selectbox(
            "Theme",
            themes,
            index=_option_index(themes, values["theme"]),
            key=_widget_key("theme"),
        )
        typography_preset = st.selectbox(
            "Typography",
            typographies,
            index=_option_index(typographies, values["typography_preset"]),
            key=_widget_key("typography_preset"),
        )
        value_format = st.selectbox(
            "Value format",
            value_formats,
            index=_option_index(value_formats, values["value_format"]),
            key=_widget_key("value_format"),
        )

    with render_column:
        fps = st.number_input(
            "FPS",
            min_value=1,
            max_value=120,
            value=_positive_int_or_default(values["fps"], 24),
            step=1,
            key=_widget_key("fps"),
        )
        steps = st.number_input(
            "Steps per transition",
            min_value=1,
            max_value=240,
            value=_positive_int_or_default(values["steps_per_transition"], 24),
            step=1,
            key=_widget_key("steps"),
        )
        top_n = st.number_input(
            "Top N",
            min_value=1,
            max_value=100,
            value=_positive_int_or_default(values["top_n"], 8),
            step=1,
            key=_widget_key("top_n"),
        )
        max_visible = st.number_input(
            "Visible bars",
            min_value=1,
            max_value=100,
            value=_positive_int_or_default(values["max_visible_bars"], 8),
            step=1,
            key=_widget_key("max_visible"),
        )
        aggregate_other = st.checkbox(
            "Aggregate hidden bars",
            value=bool(values["aggregate_other"]),
            key=_widget_key("aggregate_other"),
        )

    category_styles = _category_styles_panel(
        csv_path=csv_path,
        name_column=name_column,
        existing_styles=values["categories"],
    )

    output_column, project_column = st.columns(2)

    with output_column:
        output_file = st.text_input(
            "Output MP4",
            value=values["output_file"] or paths["output_file"],
            key=_widget_key("output_file"),
        )
        frames_dir = st.text_input(
            "Frames directory",
            value=values["frames_dir"] or paths["frames_dir"],
            key=_widget_key("frames_dir"),
        )

    with project_column:
        project_file = st.text_input(
            "Project JSON",
            value=loaded_project_path or values["project_file"] or paths["project_file"],
            key=_widget_key("project_file"),
        )

    preview_settings = _preview_controls(csv_path, year_column)

    project_data = build_project_data(
        name=project_name,
        csv_path=csv_path,
        year_column=year_column,
        name_column=name_column,
        value_column=value_column,
        title=title,
        source_label=source_label,
        output_file=output_file,
        frames_dir=frames_dir,
        layout_preset=layout_preset,
        theme=theme,
        typography_preset=typography_preset,
        value_format=value_format,
        fps=int(fps),
        steps_per_transition=int(steps),
        top_n=int(top_n),
        max_visible_bars=int(max_visible),
        aggregate_other=aggregate_other,
        category_styles=category_styles,
        base_project_data=loaded_project_data,
    )

    return project_data, project_file, preview_settings


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
    st.session_state[NEW_PROJECT_CSV_PATH_STATE] = csv_path
    st.session_state[NEW_PROJECT_CSV_PATH_OVERRIDE_STATE] = csv_path

    if previous_csv_path is not None and previous_csv_path != csv_path:
        _refresh_form()
        st.rerun()


def _category_styles_panel(csv_path, name_column, existing_styles):
    styles = {
        raw_name: dict(style)
        for raw_name, style in existing_styles.items()
        if isinstance(style, dict)
    }

    try:
        all_categories = category_values(csv_path, name_column, limit=None)
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        return styles

    if not all_categories:
        return styles

    visible_categories = all_categories[:CATEGORY_DISPLAY_LIMIT]

    with st.expander("Categories"):
        upload_column, logo_folder_column, logo_action_column = st.columns([2, 2, 1])

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
                    _refresh_form()
                    st.rerun()

        with logo_folder_column:
            logo_folder = st.text_input(
                "Logo folder path",
                value=st.session_state.get(
                    LOGO_FOLDER_OVERRIDE_STATE,
                    DEFAULT_LOGO_FOLDER,
                ),
                key=_widget_key("category_logo_folder"),
            )

        logo_files = _logo_files(logo_folder)
        matched_logos = match_category_logos(all_categories, logo_files)

        with logo_action_column:
            apply_matched_logos = st.button(
                "Apply matched logos",
                use_container_width=True,
                disabled=not matched_logos,
                key=_widget_key("apply_matched_logos"),
            )

        if matched_logos:
            st.caption(f"{len(matched_logos)} logo matches")

        if len(all_categories) > len(visible_categories):
            st.caption(
                f"Showing {len(visible_categories)} of {len(all_categories)} categories"
            )

        if apply_matched_logos:
            for raw_name, logo_path in matched_logos.items():
                styles.setdefault(raw_name, {})["logo"] = logo_path

        for index, raw_name in enumerate(visible_categories):
            current_style = styles.get(raw_name, {})
            current_label = current_style.get("label", raw_name)
            current_color = current_style.get("color")
            current_logo = current_style.get("logo") or matched_logos.get(raw_name, "")
            default_color = (
                current_color
                or DEFAULT_CATEGORY_COLORS[index % len(DEFAULT_CATEGORY_COLORS)]
            )

            columns = st.columns([3, 1, 1, 2, 1])
            key = _safe_widget_key(raw_name, index)

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
                logo_path = st.selectbox(
                    "Logo",
                    logo_options,
                    index=_option_index(logo_options, current_logo),
                    format_func=lambda path: "No logo" if not path else path,
                    key=_widget_key(f"category_logo_{key}"),
                )

            with columns[4]:
                uploaded_logo = st.file_uploader(
                    "Upload",
                    type=[extension.lstrip(".") for extension in LOGO_FILE_EXTENSIONS],
                    key=_widget_key(f"category_upload_logo_{key}"),
                )

                if uploaded_logo is not None:
                    logo_path = _save_uploaded_logo(raw_name, uploaded_logo)

            next_style = {}
            label = label.strip()

            if label and label != raw_name:
                next_style["label"] = label

            if use_color:
                next_style["color"] = color

            if logo_path:
                next_style["logo"] = logo_path

            if next_style:
                styles[raw_name] = next_style
            else:
                styles.pop(raw_name, None)

    return styles


def _save_project(project_data, project_file):
    path = save_project_data(project_data, ROOT_DIR / project_file)
    st.success(f"Saved {path.relative_to(ROOT_DIR)}")


def _preview_controls(csv_path, year_column):
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
        return

    st.image(preview_path, use_container_width=True)


def _render_video(project_file):
    progress_bar = st.progress(0.0)
    status_message = st.empty()

    try:
        preset = load_project_file(ROOT_DIR / project_file)
        progress_callback = _streamlit_progress_callback(
            progress_bar,
            status_message,
        )
        result = RenderJob(
            config=preset.chart_config,
            data_source_config=preset.data_source_config,
            dataset_config=preset.dataset_config,
            progress_callback=progress_callback,
        ).run()
    except (ProjectFileError, ValueError, OSError, CalledProcessError) as exc:
        progress_bar.empty()
        st.error(str(exc))
        return

    progress_bar.progress(1.0)
    status_message.success(f"Rendered {result.output_file}")


def _streamlit_progress_callback(progress_bar, status_message):
    def update(progress):
        message = progress.message

        if progress.total:
            message = f"{message}: {progress.current}/{progress.total}"

        progress_bar.progress(progress.progress)
        status_message.caption(message)

    return update


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


def _save_uploaded_logo(raw_name, uploaded_logo):
    logos_dir = ROOT_DIR / "logos"
    logos_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(uploaded_logo.name).suffix.lower()

    if suffix not in LOGO_FILE_EXTENSIONS:
        suffix = ".png"

    logo_path = logos_dir / f"{_safe_filename_key(raw_name)}{suffix}"
    logo_path.write_bytes(uploaded_logo.getbuffer())

    return _project_relative_path(logo_path)


def _save_uploaded_logo_folder(uploaded_logo_files):
    folder_name = _uploaded_folder_name(uploaded_logo_files)
    folder_key = _safe_filename_key(folder_name)
    target_dir = ROOT_DIR / DEFAULT_LOGO_FOLDER

    if folder_key != DEFAULT_LOGO_FOLDER:
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


if __name__ == "__main__":
    main()
