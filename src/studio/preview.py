from pathlib import Path

from config.project_file_loader import load_project_file
from core.bar_selector import BarSelector
from core.layout_engine import LayoutEngine
from core.motion_engine import MotionEngine
from core.timeline import Timeline
from importers.data_source_loader import DataSourceLoader
from models.scene import Scene
from renderer.bar_renderer import BarRenderer
from validators.dataset_validator import DatasetValidator


def render_project_preview(
    project_path,
    output_dir="output/studio_preview",
    year=None,
    preview_mode="year",
    transition_progress=0.0,
):
    preset = load_project_file(project_path)
    dataframe = DataSourceLoader(preset.data_source_config).load()
    dataframe = DatasetValidator(config=preset.dataset_config).validate(dataframe)
    timeline = Timeline(dataframe, config=preset.dataset_config)
    years = timeline.get_years()

    if not years:
        raise ValueError("Preview requires at least one time period.")

    selector = BarSelector(config=preset.chart_config.selection)
    layout = LayoutEngine(config=preset.chart_config)
    preview_mode = _preview_mode(preview_mode, years)

    if preview_mode == "transition":
        year_a, year_b = _selected_transition_years(year, years)
        sprites = _transition_sprites(
            timeline=timeline,
            selector=selector,
            layout=layout,
            animation_config=preset.chart_config.animation,
            year_a=year_a,
            year_b=year_b,
            progress=transition_progress,
        )
        progress = _clamped_progress(transition_progress)
        display_year = year_a + (year_b - year_a) * progress
        subtitle = f"{year_a} -> {year_b}"
        time_label = f"{display_year:.0f}"
    else:
        selected_year = _selected_year(year, years)
        sprites = _sprites_for_year(timeline, selector, layout, selected_year)
        subtitle = str(selected_year)
        time_label = str(selected_year)

    scene = Scene(
        title=preset.chart_config.title,
        subtitle=subtitle,
        time_label=time_label,
        source_label=preset.data_source_config.source_label,
        bars=sprites,
    )

    output_path = Path(output_dir)
    renderer = BarRenderer(output_dir=str(output_path), config=preset.chart_config)

    return renderer.render(scene, filename="preview.png")


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
    frames = MotionEngine(
        animation_config=animation_config
    ).interpolate_sprites(
        start_sprites,
        end_sprites,
        steps=101,
    )
    frame_index = round(_clamped_progress(progress) * (len(frames) - 1))

    return frames[frame_index]


def _sprites_for_year(timeline, selector, layout, year):
    bars = selector.select(timeline.get_frame(year))
    return layout.build(bars)


def _clamped_progress(progress):
    try:
        progress = float(progress)
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(1.0, progress))
