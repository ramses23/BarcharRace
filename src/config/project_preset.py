from dataclasses import dataclass

from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.theme_config import get_theme
from config.value_format_config import get_value_format


DEFAULT_PRESET_NAME = "csv_sample"


class PresetError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectPreset:
    name: str
    chart_config: ChartConfig
    data_source_config: DataSourceConfig
    dataset_config: DatasetConfig


PRESETS = {
    "csv_sample": ProjectPreset(
        name="csv_sample",
        chart_config=ChartConfig(
            title="Bar Chart Studio",
            output_file="output/video.mp4",
            theme=get_theme("studio_light"),
        ),
        data_source_config=DataSourceConfig(
            source_type="csv",
            csv_path="data/datasets/sample_dynamic.csv",
        ),
        dataset_config=DatasetConfig(),
    ),
    "sqlite_population": ProjectPreset(
        name="sqlite_population",
        chart_config=ChartConfig(
            title="Population Race",
            output_file="output/sqlite_population.mp4",
            theme=get_theme("clean_report"),
            value_format=get_value_format("population_millions"),
        ),
        data_source_config=DataSourceConfig(
            source_type="sqlite",
            sqlite_database_path="data/database/barchart.db",
            sqlite_table_name="population",
        ),
        dataset_config=DatasetConfig(),
    ),
    "youtube_1080p": ProjectPreset(
        name="youtube_1080p",
        chart_config=ChartConfig(
            title="Bar Chart Studio",
            output_file="output/youtube_1080p.mp4",
            theme=get_theme("midnight_contrast"),
            steps_per_transition=45,
            time_label_font_size=140,
            value_format=get_value_format("compact"),
        ),
        data_source_config=DataSourceConfig(
            source_type="csv",
            csv_path="data/datasets/sample_dynamic.csv",
        ),
        dataset_config=DatasetConfig(),
    ),
}


def get_preset(name):
    try:
        return PRESETS[name]
    except KeyError as exc:
        available = ", ".join(list_presets())
        raise PresetError(
            f"Unknown preset '{name}'. Available presets: {available}"
        ) from exc


def list_presets():
    return tuple(sorted(PRESETS))
