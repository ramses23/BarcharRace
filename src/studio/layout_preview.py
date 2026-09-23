from dataclasses import dataclass

from config.project_file_loader import load_project_data
from core.bar_selector import BarSelector
from core.bar_value_scale import scale_bar_sprites
from core.layout_engine import LayoutEngine
from core.timeline import Timeline
from core.motion_engine import MotionEngine
from core.transition_timing import sample_timed_sprites
from models.scene import Scene
from studio.fun_fact_layout import apply_fun_fact_layout
from studio.preview import (
    _preview_mode,
    _preview_timing_plan,
    _preview_value_scales,
    _display_calendar_resolver,
    _selected_transition_years,
    _selected_year,
    _sprites_for_year,
    _transition_frame_index,
    _transition_sprites,
)
from studio.short_export import (
    apply_export_profile,
    resolve_export_periods,
    short_fun_fact_config,
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
    timeline = Timeline(dataframe, config=preset.dataset_config,
                        include_missing_categories=preset.chart_config.bar_visibility_mode == "all")
    years = resolve_export_periods(
        timeline.get_years(),
        preset.export_config,
    )
    if not years:
        raise ValueError("Layout preview requires at least one time period.")

    raw_chart_config = preset.chart_config
    effective_fun_fact_config = short_fun_fact_config(
        preset.fun_fact_config,
        preset.export_config,
    )
    chart_config = apply_fun_fact_layout(
        apply_export_profile(raw_chart_config, preset.export_config),
        effective_fun_fact_config,
    )
    selector = BarSelector(config=chart_config.selection)
    layout = LayoutEngine(
        config=chart_config,
        fun_fact_config=effective_fun_fact_config,
    )
    timing_plan = _preview_timing_plan(timeline, years, chart_config, selector, layout)
    calendar_resolver = _display_calendar_resolver(timeline, years, chart_config, timing_plan)
    mode = _preview_mode(preview_settings.get("preview_mode", "year"), years)
    from core.opening_intro import opening_intro_frames, opening_intro_bars
    intro_frames = opening_intro_frames(chart_config)
    year = preview_settings.get("year")
    if mode == "intro":
        year = years[0]
    if mode == "transition":
        year_a, year_b = _selected_transition_years(year, years)
        progress = min(1.0, max(0.0, float(preview_settings.get("transition_progress", 0.5))))
        transition_index = years.index(year_a)
        if chart_config.animation.transition_duration_mode == "activity_weighted":
            global_frame = timing_plan.frame_at_progress(transition_index, progress)
            transition_index, _, progress = timing_plan.locate(global_frame)
            year_a, year_b = years[transition_index:transition_index + 2]
        sprites = _transition_sprites(
            timeline=timeline,
            selector=selector,
            layout=layout,
            animation_config=chart_config.animation,
            steps=timing_plan.steps_per_transition[transition_index],
            periods=years if chart_config.animation.transition_duration_mode == "activity_weighted" else None,
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
            timing_plan,
        )
    else:
        selected_year = _selected_year(year, years)
        sprites = _sprites_for_year(timeline, selector, layout, selected_year)
        subtitle = timeline.get_time_label(selected_year)
        time_label = subtitle
        frame_index = timing_plan.prefix_offsets[years.index(selected_year)]
        if chart_config.animation.transition_duration_mode == "activity_weighted":
            frame_index = min(timing_plan.frame_count - 1, frame_index)
            if timing_plan.steps_per_transition:
                sprites = sample_timed_sprites(MotionEngine(chart_config.animation),
                    tuple(_sprites_for_year(timeline, selector, layout, p) for p in years), timing_plan, frame_index)

    bar_value_scale, value_axis = _preview_value_scales(
        timeline=timeline,
        selector=selector,
        layout=layout,
        chart_config=chart_config,
        years=years,
        target_frame_index=frame_index,
        target_sprites=sprites,
    )
    sprites = scale_bar_sprites(sprites, bar_value_scale, chart_config)
    output_frame_index = frame_index + intro_frames
    if mode == "intro" and intro_frames:
        progress = min(1.0, max(0.0, float(preview_settings.get("transition_progress", 0))))
        output_frame_index = round(progress * intro_frames)
        sprites = opening_intro_bars(sprites, output_frame_index / intro_frames)

    return StudioLayoutPreview(
        chart_config=chart_config,
        raw_chart_config=raw_chart_config,
        fun_fact_config=effective_fun_fact_config,
        scene=Scene(
            title=chart_config.title,
            subtitle=subtitle,
            time_label=time_label,
            display_calendar=(
                calendar_resolver.state_at(frame_index)
                if calendar_resolver is not None
                else None
            ),
            source_label=preset.data_source_config.source_label,
            bars=sprites,
            frame_index=output_frame_index,
            value_axis=value_axis,
            bar_value_scale=bar_value_scale,
        ),
    )
