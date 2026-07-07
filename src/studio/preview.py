from pathlib import Path

from config.project_file_loader import load_project_file
from core.bar_selector import BarSelector
from core.layout_engine import LayoutEngine
from core.timeline import Timeline
from importers.data_source_loader import DataSourceLoader
from models.scene import Scene
from renderer.bar_renderer import BarRenderer
from validators.dataset_validator import DatasetValidator


def render_project_preview(project_path, output_dir="output/studio_preview", year=None):
    preset = load_project_file(project_path)
    dataframe = DataSourceLoader(preset.data_source_config).load()
    dataframe = DatasetValidator(config=preset.dataset_config).validate(dataframe)
    timeline = Timeline(dataframe, config=preset.dataset_config)
    years = timeline.get_years()

    if not years:
        raise ValueError("Preview requires at least one time period.")

    selected_year = _selected_year(year, years)
    bars = BarSelector(config=preset.chart_config.selection).select(
        timeline.get_frame(selected_year)
    )
    sprites = LayoutEngine(config=preset.chart_config).build(bars)
    scene = Scene(
        title=preset.chart_config.title,
        subtitle=str(selected_year),
        time_label=str(selected_year),
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
