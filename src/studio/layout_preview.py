from dataclasses import dataclass

from config.project_file_loader import load_project_data
from core.bar_selector import BarSelector
from core.layout_engine import LayoutEngine
from core.timeline import Timeline
from core.value_axis import scale_bar_sprites
from models.scene import Scene
from studio.fun_fact_layout import apply_fun_fact_layout
from studio.preview import (
    _preview_mode,
    _preview_value_axis_state,
    _selected_transition_years,
    _selected_year,
    _sprites_for_year,
    _transition_frame_index,
    _transition_sprites,
)


@dataclass(frozen=True)
class StudioLayoutPreview:
    chart_config: object
    raw_chart_config: object
    fun_fact_config: object
    scene: Scene


def build_studio_layout_preview(project_data, dataframe, preview_settings=None):
    """Build the selected Studio frame without rendering or resolving assets."""
    preview_settings = preview_settings if isinstance(preview_settings, dict) else {}
    preset = load_project_data(project_data, default_name="studio-layout-preview")
    timeline = Timeline(dataframe, config=preset.dataset_config)
    years = timeline.get_years()
    if not years:
        raise ValueError("Layout preview requires at least one time period.")

    raw_chart_config = preset.chart_config
    chart_config = apply_fun_fact_layout(
        raw_chart_config,
        preset.fun_fact_config,
    )
    selector = BarSelector(config=chart_config.selection)
    layout = LayoutEngine(
        config=chart_config,
        fun_fact_config=preset.fun_fact_config,
    )
    mode = _preview_mode(preview_settings.get("preview_mode", "year"), years)
    year = preview_settings.get("year")
    if mode == "transition":
        year_a, year_b = _selected_transition_years(year, years)
        progress = min(1.0, max(0.0, float(preview_settings.get("transition_progress", 0.5))))
        sprites = _transition_sprites(
            timeline=timeline,
            selector=selector,
            layout=layout,
            animation_config=chart_config.animation,
            steps=chart_config.steps_per_transition,
            year_a=year_a,
            year_b=year_b,
            progress=progress,
        )
        subtitle = f"{timeline.get_time_label(year_a)} -> {timeline.get_time_label(year_b)}"
        time_label = timeline.get_time_label(year_a + ((year_b - year_a) * progress))
        frame_index = _transition_frame_index(
            chart_config,
            years.index(year_a),
            progress,
        )
    else:
        selected_year = _selected_year(year, years)
        sprites = _sprites_for_year(timeline, selector, layout, selected_year)
        subtitle = timeline.get_time_label(selected_year)
        time_label = subtitle
        frame_index = years.index(selected_year) * chart_config.steps_per_transition

    value_axis = _preview_value_axis_state(
        timeline=timeline,
        selector=selector,
        layout=layout,
        chart_config=chart_config,
        years=years,
        target_frame_index=frame_index,
    )
    if value_axis is not None:
        sprites = scale_bar_sprites(sprites, value_axis.scale)

    return StudioLayoutPreview(
        chart_config=chart_config,
        raw_chart_config=raw_chart_config,
        fun_fact_config=preset.fun_fact_config,
        scene=Scene(
            title=chart_config.title,
            subtitle=subtitle,
            time_label=time_label,
            source_label=preset.data_source_config.source_label,
            bars=sprites,
            frame_index=frame_index,
            value_axis=value_axis,
        ),
    )
