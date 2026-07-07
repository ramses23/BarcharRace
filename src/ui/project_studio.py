import sys
from pathlib import Path
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
    preferred_column,
    project_form_values,
    project_name_from_title,
    save_project_data,
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

    csv_path = _csv_source_panel(values)

    if not csv_path:
        return

    try:
        inspection = inspect_csv(csv_path)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.error(str(exc))
        return

    st.caption(f"{inspection.row_count:,} rows")

    preview_df = pd.read_csv(csv_path, nrows=12)
    st.dataframe(preview_df, use_container_width=True, hide_index=True)

    project_data, project_file = _project_form(
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
            _render_preview(project_file)

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
            _refresh_form()
            st.rerun()

    with new_column:
        if st.button("New project", use_container_width=True):
            st.session_state.pop("loaded_project_data", None)
            st.session_state.pop("loaded_project_path", None)
            _refresh_form()
            st.rerun()

    if st.session_state.get("loaded_project_path"):
        st.caption(f"Editing {st.session_state['loaded_project_path']}")


def _csv_source_panel(values):
    st.subheader("Dataset")
    uploaded_file = st.file_uploader("CSV file", type=["csv"])
    default_csv = values["csv_path"]

    if uploaded_file is not None:
        datasets_dir = ROOT_DIR / "data" / "datasets"
        datasets_dir.mkdir(parents=True, exist_ok=True)
        csv_path = datasets_dir / uploaded_file.name
        csv_path.write_bytes(uploaded_file.getbuffer())
        return str(csv_path.relative_to(ROOT_DIR))

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

    return project_data, project_file


def _category_styles_panel(csv_path, name_column, existing_styles):
    styles = {
        raw_name: dict(style)
        for raw_name, style in existing_styles.items()
        if isinstance(style, dict)
    }

    try:
        categories = category_values(csv_path, name_column)
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        return styles

    if not categories:
        return styles

    with st.expander("Categories"):
        for index, raw_name in enumerate(categories):
            current_style = styles.get(raw_name, {})
            current_label = current_style.get("label", raw_name)
            current_color = current_style.get("color")
            default_color = (
                current_color
                or DEFAULT_CATEGORY_COLORS[index % len(DEFAULT_CATEGORY_COLORS)]
            )

            label_column, toggle_column, color_column = st.columns([3, 1, 1])
            key = _safe_widget_key(raw_name, index)

            with label_column:
                label = st.text_input(
                    raw_name,
                    value=current_label,
                    key=_widget_key(f"category_label_{key}"),
                )

            with toggle_column:
                use_color = st.checkbox(
                    "Custom color",
                    value=bool(current_color),
                    key=_widget_key(f"category_use_color_{key}"),
                )

            with color_column:
                color = st.color_picker(
                    raw_name,
                    value=default_color,
                    key=_widget_key(f"category_color_{key}"),
                    label_visibility="collapsed",
                    disabled=not use_color,
                )

            next_style = {}
            label = label.strip()

            if label and label != raw_name:
                next_style["label"] = label

            if use_color:
                next_style["color"] = color

            if next_style:
                styles[raw_name] = next_style
            else:
                styles.pop(raw_name, None)

    return styles


def _save_project(project_data, project_file):
    path = save_project_data(project_data, ROOT_DIR / project_file)
    st.success(f"Saved {path.relative_to(ROOT_DIR)}")


def _render_preview(project_file):
    try:
        preview_path = render_project_preview(ROOT_DIR / project_file)
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


def _widget_key(name):
    return f"{name}_{st.session_state.get('form_version', 0)}"


def _safe_widget_key(value, index):
    safe_value = "".join(
        character if character.isalnum() else "_"
        for character in str(value).lower()
    ).strip("_")
    return f"{index}_{safe_value or 'category'}"


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
