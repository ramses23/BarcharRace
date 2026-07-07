import sys
from pathlib import Path

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
    default_project_paths,
    inspect_csv,
    preferred_column,
    project_name_from_title,
    save_project_data,
)
from config.project_file_loader import load_project_file


st.set_page_config(
    page_title="BarChartStudio",
    page_icon="B",
    layout="wide",
)


def main():
    st.title("BarChartStudio")

    csv_path = _csv_source_panel()

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

    project_data, project_file = _project_form(csv_path, inspection)

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


def _csv_source_panel():
    st.subheader("Dataset")
    uploaded_file = st.file_uploader("CSV file", type=["csv"])
    default_csv = "data/datasets/global_electricity_sources.csv"

    if uploaded_file is not None:
        datasets_dir = ROOT_DIR / "data" / "datasets"
        datasets_dir.mkdir(parents=True, exist_ok=True)
        csv_path = datasets_dir / uploaded_file.name
        csv_path.write_bytes(uploaded_file.getbuffer())
        return str(csv_path.relative_to(ROOT_DIR))

    return st.text_input("CSV path", value=default_csv)


def _project_form(csv_path, inspection):
    title = st.text_input("Title", value="Electricity by Source")
    project_name = st.text_input(
        "Project name",
        value=project_name_from_title(title),
    )
    paths = default_project_paths(project_name)

    dataset_column, visual_column, render_column = st.columns(3)

    with dataset_column:
        year_column = st.selectbox(
            "Year column",
            inspection.columns,
            index=_column_index(
                inspection.columns,
                preferred_column(inspection.year_candidates, inspection.columns, "year"),
            ),
        )
        name_column = st.selectbox(
            "Name column",
            inspection.columns,
            index=_column_index(
                inspection.columns,
                preferred_column(inspection.name_candidates, inspection.columns, "country"),
            ),
        )
        value_column = st.selectbox(
            "Value column",
            inspection.columns,
            index=_column_index(
                inspection.columns,
                preferred_column(inspection.value_candidates, inspection.columns, "value"),
            ),
        )
        source_label = st.text_input(
            "Source label",
            value="Source: User-provided dataset",
        )

    with visual_column:
        layouts = list_layout_presets()
        themes = list_themes()
        typographies = list_typography_presets()
        value_formats = list_value_formats()

        layout_preset = st.selectbox(
            "Layout",
            layouts,
            index=_option_index(layouts, "youtube_1080p"),
        )
        theme = st.selectbox(
            "Theme",
            themes,
            index=_option_index(themes, "clean_report"),
        )
        typography_preset = st.selectbox(
            "Typography",
            typographies,
            index=_option_index(typographies, "editorial"),
        )
        value_format = st.selectbox(
            "Value format",
            value_formats,
            index=_option_index(value_formats, "decimal"),
        )

    with render_column:
        fps = st.number_input("FPS", min_value=1, max_value=120, value=24, step=1)
        steps = st.number_input(
            "Steps per transition",
            min_value=1,
            max_value=240,
            value=24,
            step=1,
        )
        top_n = st.number_input("Top N", min_value=1, max_value=100, value=8, step=1)
        max_visible = st.number_input(
            "Visible bars",
            min_value=1,
            max_value=100,
            value=8,
            step=1,
        )

    output_column, project_column = st.columns(2)

    with output_column:
        output_file = st.text_input("Output MP4", value=paths["output_file"])
        frames_dir = st.text_input("Frames directory", value=paths["frames_dir"])

    with project_column:
        project_file = st.text_input("Project JSON", value=paths["project_file"])

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
    )

    return project_data, project_file


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
    try:
        preset = load_project_file(ROOT_DIR / project_file)
        result = RenderJob(
            config=preset.chart_config,
            data_source_config=preset.data_source_config,
            dataset_config=preset.dataset_config,
        ).run()
    except (ProjectFileError, ValueError, OSError) as exc:
        st.error(str(exc))
        return

    st.success(f"Rendered {result.output_file}")


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


if __name__ == "__main__":
    main()
