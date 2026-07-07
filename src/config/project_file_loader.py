import json
from dataclasses import fields, replace
from pathlib import Path

from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.layout_config import apply_layout_preset, get_layout_preset
from config.project_preset import ProjectPreset, get_preset
from config.theme_config import get_theme
from config.typography_config import apply_typography_preset, get_typography_preset
from config.value_format_config import get_value_format


class ProjectFileError(ValueError):
    pass


PROJECT_FILE_SECTIONS = {
    "name",
    "base_preset",
    "animation",
    "categories",
    "selection",
    "chart",
    "data_source",
    "dataset",
}


def load_project_file(path):
    project_path = Path(path)
    data = _read_project_data(project_path)

    _reject_unknown_keys(
        data,
        PROJECT_FILE_SECTIONS,
        "project file",
    )

    base_preset = _base_preset(data, project_path)
    project_name = _project_name(data, project_path)
    chart_data = data.get("chart", {})
    chart_config = _build_config(
        _chart_base_config(base_preset.chart_config, chart_data),
        chart_data,
        "chart",
        _convert_chart_value,
    )
    chart_config = replace(
        chart_config,
        animation=_build_config(
            chart_config.animation,
            data.get("animation", {}),
            "animation",
            _convert_animation_value,
        ),
        selection=_build_config(
            chart_config.selection,
            data.get("selection", {}),
            "selection",
            _convert_selection_value,
        ),
    )

    dataset_config = _build_config(
        base_preset.dataset_config,
        data.get("dataset", {}),
        "dataset",
        _convert_dataset_value,
    )
    dataset_config = _apply_category_styles(
        dataset_config,
        data.get("categories", {}),
    )

    return ProjectPreset(
        name=project_name,
        chart_config=chart_config,
        data_source_config=_build_config(
            base_preset.data_source_config,
            data.get("data_source", {}),
            "data_source",
            _convert_data_source_value,
        ),
        dataset_config=dataset_config,
    )


def _read_project_data(project_path):
    try:
        data = json.loads(project_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProjectFileError(
            f"Project file not found: {project_path}"
        ) from exc
    except OSError as exc:
        raise ProjectFileError(
            f"Could not read project file: {project_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProjectFileError(
            f"Invalid JSON in project file '{project_path}': {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise ProjectFileError("Project file must contain a JSON object.")

    return data


def _base_preset(data, project_path):
    base_name = data.get("base_preset")

    if base_name is None:
        return ProjectPreset(
            name=project_path.stem,
            chart_config=ChartConfig(),
            data_source_config=DataSourceConfig(),
            dataset_config=DatasetConfig(),
        )

    if not isinstance(base_name, str) or not base_name.strip():
        raise ProjectFileError("Project field 'base_preset' must be a string.")

    try:
        return get_preset(base_name)
    except ValueError as exc:
        raise ProjectFileError(str(exc)) from exc


def _project_name(data, project_path):
    name = data.get("name")

    if name is None:
        return project_path.stem

    if not isinstance(name, str) or not name.strip():
        raise ProjectFileError("Project field 'name' must be a non-empty string.")

    return name


def _build_config(base_config, section_data, section_name, convert_value=None):
    if section_data is None:
        section_data = {}

    if not isinstance(section_data, dict):
        raise ProjectFileError(f"Project section '{section_name}' must be an object.")

    allowed_fields = {field.name for field in fields(base_config)}
    _reject_unknown_keys(section_data, allowed_fields, section_name)

    updates = {}

    for key, value in section_data.items():
        if convert_value is not None:
            value = convert_value(key, value)

        updates[key] = value

    if not updates:
        return base_config

    try:
        return replace(base_config, **updates)
    except TypeError as exc:
        raise ProjectFileError(
            f"Invalid values in project section '{section_name}'."
        ) from exc


def _chart_base_config(base_config, chart_data):
    if chart_data is None:
        return base_config

    if not isinstance(chart_data, dict):
        raise ProjectFileError("Project section 'chart' must be an object.")

    layout_preset_name = chart_data.get("layout_preset")

    if layout_preset_name is not None:
        if not isinstance(layout_preset_name, str):
            raise ProjectFileError(
                "Chart field 'layout_preset' must be a named layout preset."
            )

        try:
            base_config = apply_layout_preset(base_config, layout_preset_name)
        except ValueError as exc:
            raise ProjectFileError(str(exc)) from exc

    typography_preset_name = chart_data.get("typography_preset")

    if typography_preset_name is None:
        return base_config

    if not isinstance(typography_preset_name, str):
        raise ProjectFileError(
            "Chart field 'typography_preset' must be a named typography preset."
        )

    try:
        return apply_typography_preset(base_config, typography_preset_name)
    except ValueError as exc:
        raise ProjectFileError(str(exc)) from exc


def _convert_chart_value(key, value):
    if key == "animation":
        raise ProjectFileError(
            "Use the top-level 'animation' section instead of 'chart.animation'."
        )

    if key == "selection":
        raise ProjectFileError(
            "Use the top-level 'selection' section instead of 'chart.selection'."
        )

    if key == "theme":
        if not isinstance(value, str):
            raise ProjectFileError("Chart field 'theme' must be a named theme.")

        return get_theme(value)

    if key == "layout_preset":
        if not isinstance(value, str):
            raise ProjectFileError(
                "Chart field 'layout_preset' must be a named layout preset."
            )

        try:
            get_layout_preset(value)
        except ValueError as exc:
            raise ProjectFileError(str(exc)) from exc

        return value

    if key == "value_format":
        if not isinstance(value, str):
            raise ProjectFileError(
                "Chart field 'value_format' must be a named value format."
            )

        return get_value_format(value)

    if key == "typography_preset":
        if not isinstance(value, str):
            raise ProjectFileError(
                "Chart field 'typography_preset' must be a named typography preset."
            )

        try:
            get_typography_preset(value)
        except ValueError as exc:
            raise ProjectFileError(str(exc)) from exc

        return value

    if key in ("video_codec", "video_pixel_format"):
        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(f"Chart field '{key}' must be a non-empty string.")

        return value

    if key == "video_crf":
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProjectFileError("Chart field 'video_crf' must be null or >= 0.")

        return value

    if key in ("video_bitrate", "ffmpeg_preset"):
        if value is None:
            return None

        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(f"Chart field '{key}' must be null or a string.")

        return value

    if key == "auto_fit_bar_count":
        if not isinstance(value, bool):
            raise ProjectFileError("Chart field 'auto_fit_bar_count' must be boolean.")

        return value

    if key == "max_visible_bars":
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProjectFileError("Chart field 'max_visible_bars' must be null or >= 0.")

        return value

    if key in ("rank_label_min_x", "rank_label_label_gap"):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProjectFileError(f"Chart field '{key}' must be >= 0.")

        return value

    if key == "value_label_min_x":
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProjectFileError(
                "Chart field 'value_label_min_x' must be null or >= 0."
            )

        return value

    if key == "logo_file_extensions":
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ProjectFileError(
                "Chart field 'logo_file_extensions' must be a list of strings."
            )

        return tuple(value)

    return value


def _convert_animation_value(key, value):
    if key == "easing":
        if not isinstance(value, str):
            raise ProjectFileError("Animation field 'easing' must be a string.")

        try:
            AnimationConfig(easing=value).easing_function()
        except ValueError as exc:
            raise ProjectFileError(str(exc)) from exc

        return value

    if key in ("enter_exit", "value_smoothing"):
        if not isinstance(value, bool):
            raise ProjectFileError(f"Animation field '{key}' must be a boolean.")

        return value

    return value


def _convert_selection_value(key, value):
    if key == "top_n":
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ProjectFileError("Selection field 'top_n' must be null or >= 1.")

        return value

    if key == "aggregate_other":
        if not isinstance(value, bool):
            raise ProjectFileError("Selection field 'aggregate_other' must be boolean.")

        return value

    if key == "other_label":
        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(
                "Selection field 'other_label' must be a non-empty string."
            )

        return value

    if key == "other_color":
        if value is None:
            return None

        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(
                "Selection field 'other_color' must be null or a string."
            )

        return value

    return value


def _convert_data_source_value(key, value):
    if key in (
        "source_type",
        "csv_path",
        "sqlite_database_path",
        "sqlite_table_name",
    ):
        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(
                f"Data source field '{key}' must be a non-empty string."
            )

        return value

    if key == "source_label_override":
        if value is None:
            return None

        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(
                "Data source field 'source_label_override' must be null "
                "or a non-empty string."
            )

        return value

    return value


def _convert_dataset_value(key, value):
    if key in ("category_labels", "category_colors", "category_logos"):
        return _convert_string_map(value, f"Dataset field '{key}'")

    return value


def _apply_category_styles(dataset_config, categories):
    if categories is None:
        categories = {}

    if not isinstance(categories, dict):
        raise ProjectFileError("Project section 'categories' must be an object.")

    labels = dict(dataset_config.category_labels)
    colors = dict(dataset_config.category_colors)
    logos = dict(dataset_config.category_logos)

    for raw_name, style in categories.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ProjectFileError("Category names must be non-empty strings.")

        if not isinstance(style, dict):
            raise ProjectFileError(
                f"Category '{raw_name}' must be an object."
            )

        _reject_unknown_keys(
            style,
            {"label", "color", "logo"},
            f"category '{raw_name}'",
        )

        if "label" in style:
            _update_optional_style(
                labels,
                raw_name,
                style["label"],
                f"Category '{raw_name}' field 'label'",
            )

        if "color" in style:
            _update_optional_style(
                colors,
                raw_name,
                style["color"],
                f"Category '{raw_name}' field 'color'",
            )

        if "logo" in style:
            _update_optional_style(
                logos,
                raw_name,
                style["logo"],
                f"Category '{raw_name}' field 'logo'",
            )

    return replace(
        dataset_config,
        category_labels=labels,
        category_colors=colors,
        category_logos=logos,
    )


def _convert_string_map(value, label):
    if not isinstance(value, dict):
        raise ProjectFileError(f"{label} must be an object.")

    converted = {}

    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProjectFileError(f"{label} keys must be non-empty strings.")

        if not isinstance(item, str) or not item.strip():
            raise ProjectFileError(f"{label} values must be non-empty strings.")

        converted[key] = item

    return converted


def _update_optional_style(styles, raw_name, value, label):
    if value is None:
        styles.pop(raw_name, None)
        return

    if not isinstance(value, str) or not value.strip():
        raise ProjectFileError(f"{label} must be null or a non-empty string.")

    styles[raw_name] = value


def _reject_unknown_keys(data, allowed_keys, location):
    unknown_keys = sorted(set(data) - set(allowed_keys))

    if not unknown_keys:
        return

    available = ", ".join(sorted(allowed_keys))
    unknown = ", ".join(unknown_keys)
    raise ProjectFileError(
        f"Unknown key(s) in {location}: {unknown}. Available keys: {available}"
    )
