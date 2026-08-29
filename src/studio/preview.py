from dataclasses import replace

from config.project_file_loader import load_project_data, load_project_file
from core.background_motion import (
    SpeedLineMotionTracker,
    normalized_motion_response,
)
from core.bar_selector import BarSelector
from core.layout_engine import LayoutEngine
from core.motion_engine import MotionEngine
from core.timeline import Timeline
from importers.data_source_loader import DataSourceLoader
from models.scene import Scene
from renderer.bar_renderer import BarRenderer
from studio.package_paths import DEFAULT_PROJECT_ROOT, resolve_project_path
from studio.fun_fact_layout import apply_fun_fact_layout
from studio.fun_fact_loader import load_fun_fact_scheduler
from studio.project_runtime import resolve_project_preset_paths
from studio.short_export import (
    apply_export_profile,
    estimate_export_duration,
    resolve_export_periods,
    short_fun_fact_config,
    short_overlay_for_frame,
)
from studio.workspace_paths import assert_user_write_path
from validators.dataset_validator import DatasetValidator


def render_project_preview(
    project_path,
    output_dir=None,
    year=None,
    preview_mode="year",
    transition_progress=0.0,
    *,
    root_dir=None,
    project_data=None,
    force_fun_fact_id=None,
    app_root=None,
):
    root_path = _project_root(root_dir)
    if project_data is None:
        project_path = resolve_project_path(
            project_path,
            project_root=root_path,
            required=True,
            field_name="project file",
        )
        preset = load_project_file(project_path)
    else:
        preset = load_project_data(
            project_data,
            default_name=project_path,
        )
    source_label = preset.data_source_config.source_label
    preset = resolve_project_preset_paths(
        preset,
        project_root=root_path,
        output_root=root_path,
    )
    data_source_config = preset.data_source_config
    dataset_config = preset.dataset_config
    chart_config = preset.chart_config

    dataframe = DataSourceLoader(data_source_config).load()
    dataframe = DatasetValidator(config=dataset_config).validate(dataframe)
    timeline = Timeline(dataframe, config=dataset_config)
    years = resolve_export_periods(
        timeline.get_years(),
        preset.export_config,
    )

    if not years:
        raise ValueError("Preview requires at least one time period.")

    fun_fact_config = short_fun_fact_config(
        preset.fun_fact_config,
        preset.export_config,
    )
    fun_fact_scheduler = load_fun_fact_scheduler(
        fun_fact_config,
        timeline,
        project_root=root_path,
    )
    chart_config = apply_export_profile(chart_config, preset.export_config)
    chart_config = apply_fun_fact_layout(chart_config, fun_fact_config)
    selector = BarSelector(config=chart_config.selection)
    layout = LayoutEngine(
        config=chart_config,
        fun_fact_config=preset.fun_fact_config,
    )
    preview_mode = _preview_mode(preview_mode, years)

    if preview_mode == "transition":
        year_a, year_b = _selected_transition_years(year, years)
        sprites = _transition_sprites(
            timeline=timeline,
            selector=selector,
            layout=layout,
            animation_config=chart_config.animation,
            year_a=year_a,
            year_b=year_b,
            progress=transition_progress,
        )
        progress = _clamped_progress(transition_progress)
        display_year = year_a + (year_b - year_a) * progress
        subtitle = (
            f"{timeline.get_time_label(year_a)} -> "
            f"{timeline.get_time_label(year_b)}"
        )
        time_label = timeline.get_time_label(display_year)
        active_fact = (
            fun_fact_scheduler.active_at(
                year_a,
                year_b,
                progress=progress,
            )
            if fun_fact_scheduler is not None
            else None
        )
        frame_index = (
            years.index(year_a) * chart_config.steps_per_transition
            + round(progress * chart_config.steps_per_transition)
        )
    else:
        selected_year = _selected_year(year, years)
        sprites = _sprites_for_year(timeline, selector, layout, selected_year)
        subtitle = timeline.get_time_label(selected_year)
        time_label = timeline.get_time_label(selected_year)
        active_fact = (
            fun_fact_scheduler.active_for_period(selected_year)
            if fun_fact_scheduler is not None
            else None
        )
        frame_index = years.index(selected_year) * chart_config.steps_per_transition

    if force_fun_fact_id is not None:
        if fun_fact_scheduler is None:
            if not (
                preset.export_config.is_short
                and not preset.export_config.short_include_fun_facts
            ):
                raise ValueError("Cannot force a preview when fun facts are disabled.")
        else:
            active_fact = fun_fact_scheduler.force(force_fun_fact_id)

    scene = Scene(
        title=chart_config.title,
        subtitle=subtitle,
        time_label=time_label,
        source_label=source_label,
        bars=sprites,
        fun_fact=active_fact,
        frame_index=frame_index,
    )
    speed_line_motion = _preview_speed_line_motion(
        timeline=timeline,
        selector=selector,
        layout=layout,
        chart_config=chart_config,
        years=years,
        target_frame_index=frame_index,
    )
    if speed_line_motion is not None:
        scene.background_motion_response = (
            speed_line_motion.smoothed_response
        )
        scene.background_motion_line_positions = (
            speed_line_motion.line_positions
        )
    duration = estimate_export_duration(
        timeline.get_years(),
        chart_config,
        preset.export_config,
    )
    scene.short_overlay = short_overlay_for_frame(
        preset.export_config,
        frame_index=min(frame_index, max(0, duration.frame_count - 1)),
        total_frames=duration.frame_count,
        fps=chart_config.fps,
    )

    output_path = resolve_project_path(
        output_dir or "output/previews",
        project_root=root_path,
        required=True,
        field_name="preview output directory",
    )
    if app_root is not None:
        output_path = assert_user_write_path(
            output_path,
            app_root=app_root,
            operation="Preview render",
        )
    renderer = BarRenderer(
        output_dir=str(output_path),
        config=chart_config,
        fun_fact_config=fun_fact_config,
    )

    try:
        return renderer.render(scene, filename="preview.png")
    finally:
        renderer.close()


def _project_root(root_dir):
    return resolve_project_path(
        root_dir if root_dir is not None else DEFAULT_PROJECT_ROOT,
        project_root=DEFAULT_PROJECT_ROOT,
        required=True,
        field_name="project root",
    )


def _resolved_dataset_config(config, root_path):
    """Backward-compatible helper for callers that resolve preview logo maps."""
    return replace(
        config,
        category_logos={
            category: str(
                resolve_project_path(
                    value,
                    project_root=root_path,
                    required=True,
                    field_name=f"dataset.category_logos[{category!r}]",
                )
            )
            for category, value in config.category_logos.items()
        },
        category_secondary_logos={
            category: str(
                resolve_project_path(
                    value,
                    project_root=root_path,
                    required=True,
                    field_name=(
                        "dataset.category_secondary_logos"
                        f"[{category!r}]"
                    ),
                )
            )
            for category, value in config.category_secondary_logos.items()
        },
    )


def _resolved_chart_config(config, root_path):
    """Backward-compatible helper for preview asset path resolution."""
    background_path = resolve_project_path(
        config.background_image_path,
        project_root=root_path,
        required=config.background_mode == "image",
        field_name="chart.background_image_path",
    )
    texture_path = resolve_project_path(
        config.bar_texture_custom_image,
        project_root=root_path,
        required=(
            config.bar_texture_enabled
            and config.bar_texture_preset == "custom_image"
        ),
        field_name="chart.bar_texture_custom_image",
    )
    logos_dir = resolve_project_path(
        config.logos_dir,
        project_root=root_path,
        required=True,
        field_name="chart.logos_dir",
    )
    return replace(
        config,
        background_image_path=(
            str(background_path) if background_path is not None else None
        ),
        bar_texture_custom_image=(
            str(texture_path) if texture_path is not None else None
        ),
        logos_dir=str(logos_dir),
    )


def _selected_year(year, years):
    if year is None:
        return years[0]

    year = int(year)

    if year in years:
        return year

    return min(years, key=lambda candidate: abs(candidate - year))


def _selected_transition_years(year, years):
    if len(years) < 2:
        selected_year = _selected_year(year, years)
        return selected_year, selected_year

    start_years = years[:-1]
    selected_year = _selected_year(year, start_years)
    start_index = years.index(selected_year)

    return years[start_index], years[start_index + 1]


def _preview_mode(preview_mode, years):
    if preview_mode == "transition" and len(years) > 1:
        return "transition"

    return "year"


def _transition_sprites(
    timeline,
    selector,
    layout,
    animation_config,
    year_a,
    year_b,
    progress,
):
    start_sprites = _sprites_for_year(timeline, selector, layout, year_a)
    end_sprites = _sprites_for_year(timeline, selector, layout, year_b)
    motion = MotionEngine(animation_config=animation_config)

    if animation_config.continuous_motion:
        years = timeline.get_years()
        start_index = years.index(year_a)
        previous_year = years[start_index - 1] if start_index > 0 else year_a
        next_year = (
            years[start_index + 2]
            if start_index + 2 < len(years)
            else year_b
        )
        frames = motion.interpolate_sprites_continuous(
            _sprites_for_year(timeline, selector, layout, previous_year),
            start_sprites,
            end_sprites,
            _sprites_for_year(timeline, selector, layout, next_year),
            steps=100,
            include_start=True,
        )
    else:
        frames = motion.interpolate_sprites(
            start_sprites,
            end_sprites,
            steps=101,
        )
    frame_index = round(_clamped_progress(progress) * (len(frames) - 1))

    return frames[frame_index]


def _preview_speed_line_motion(
    *,
    timeline,
    selector,
    layout,
    chart_config,
    years,
    target_frame_index,
):
    if chart_config.background_motion != "horizontal_speed_lines":
        return None

    tracker = SpeedLineMotionTracker.from_config(chart_config)
    if len(years) < 2:
        return tracker.next(0.0)

    sprites_by_year = {
        year: _sprites_for_year(timeline, selector, layout, year)
        for year in years
    }
    motion = MotionEngine(animation_config=chart_config.animation)
    current_frame_index = 0
    latest_motion = None

    for index in range(len(years) - 1):
        year_a = years[index]
        year_b = years[index + 1]
        start_sprites = sprites_by_year[year_a]
        end_sprites = sprites_by_year[year_b]
        if chart_config.animation.continuous_motion:
            previous_year = years[index - 1] if index > 0 else year_a
            next_year = (
                years[index + 2]
                if index + 2 < len(years)
                else year_b
            )
            frames = motion.interpolate_sprites_continuous(
                sprites_by_year[previous_year],
                start_sprites,
                end_sprites,
                sprites_by_year[next_year],
                steps=chart_config.steps_per_transition,
                include_start=index == 0,
            )
        else:
            frames = motion.interpolate_sprites(
                start_sprites,
                end_sprites,
                steps=chart_config.steps_per_transition,
            )

        for frame_sprites in frames:
            target_response = normalized_motion_response(
                frame_sprites,
                start_sprites,
                end_sprites,
                response_mode=chart_config.background_motion_response,
            )
            latest_motion = tracker.next(target_response)
            if current_frame_index >= target_frame_index:
                return latest_motion
            current_frame_index += 1

    return latest_motion or tracker.next(0.0)


def _sprites_for_year(timeline, selector, layout, year):
    bars = selector.select(timeline.get_frame(year))
    return layout.build(bars)


def _clamped_progress(progress):
    try:
        progress = float(progress)
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(1.0, progress))
