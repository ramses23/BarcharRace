import json
from dataclasses import fields, replace
from pathlib import Path

from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
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

    return ProjectPreset(
        name=project_name,
        chart_config=chart_config,
        data_source_config=_build_config(
            base_preset.data_source_config,
            data.get("data_source", {}),
            "data_source",
        ),
        dataset_config=_build_config(
            base_preset.dataset_config,
            data.get("dataset", {}),
            "dataset",
        ),
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

    preset_name = chart_data.get("typography_preset")

    if preset_name is None:
        return base_config

    if not isinstance(preset_name, str):
        raise ProjectFileError(
            "Chart field 'typography_preset' must be a named typography preset."
        )

    try:
        return apply_typography_preset(base_config, preset_name)
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
def _reject_unknown_keys(data, allowed_keys, location):
    unknown_keys = sorted(set(data) - set(allowed_keys))

    if not unknown_keys:
        return

    available = ", ".join(sorted(allowed_keys))
    unknown = ", ".join(unknown_keys)
    raise ProjectFileError(
        f"Unknown key(s) in {location}: {unknown}. Available keys: {available}"
    )
