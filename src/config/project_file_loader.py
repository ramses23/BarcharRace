import json
from dataclasses import fields, replace
from pathlib import Path

from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.export_config import ExportConfig
from config.fun_fact_config import FunFactConfig
from config.layout_config import apply_layout_preset, get_layout_preset
from config.project_preset import ProjectPreset, get_preset
from config.project_schema import ProjectSchemaError, migrate_project_data
from config.theme_config import get_theme
from config.typography_config import apply_typography_preset, get_typography_preset
from config.value_format_config import get_value_format


class ProjectFileError(ValueError):
    pass


PROJECT_FILE_SECTIONS = {
    "schema_version",
    "name",
    "base_preset",
    "animation",
    "categories",
    "selection",
    "chart",
    "data_source",
    "dataset",
    "fun_facts",
    "export",
}


def load_project_file(path):
    project_path = Path(path)
    data = _read_project_data(project_path)
    return _project_preset_from_data(data, project_path)


def load_project_data(data, *, default_name="project"):
    try:
        migrated_data = migrate_project_data(data).data
    except ProjectSchemaError as exc:
        raise ProjectFileError(str(exc)) from exc

    default_name = str(default_name).strip() or "project"
    return _project_preset_from_data(migrated_data, Path(default_name))


def _project_preset_from_data(data, project_path):
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
    fun_fact_config = _build_config(
        base_preset.fun_fact_config,
        data.get("fun_facts", {}),
        "fun_facts",
        _convert_fun_fact_value,
    )
    export_config = _build_config(
        ExportConfig(),
        data.get("export", {}),
        "export",
        _convert_export_value,
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
        fun_fact_config=fun_fact_config,
        export_config=export_config,
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

    try:
        return migrate_project_data(data).data
    except ProjectSchemaError as exc:
        raise ProjectFileError(str(exc)) from exc


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

    if key in (
        "title_font_size",
        "subtitle_font_size",
        "label_font_size",
        "value_font_size",
        "time_label_font_size",
        "source_font_size",
        "rank_label_font_size",
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ProjectFileError(f"Chart field '{key}' must be at least 1.")

        return value

    if key in ("title_x", "subtitle_x") and value is None:
        return None

    if key in (
        "title_x",
        "title_y",
        "subtitle_x",
        "subtitle_y",
        "time_label_x",
        "time_label_y",
        "source_x",
        "source_y",
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProjectFileError(f"Chart field '{key}' must be at least 0.")

        return value

    if key in ("video_codec", "video_pixel_format"):
        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(f"Chart field '{key}' must be a non-empty string.")

        return value

    if key.endswith("_font_family"):
        if value is None:
            return None

        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(
                f"Chart field '{key}' must be null or a non-empty string."
            )

        return value.strip()

    if key.endswith("_font_weight"):
        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(
                f"Chart field '{key}' must be a non-empty font weight."
            )
        return value.strip()

    if key.endswith("_font_style"):
        if value not in ("normal", "italic"):
            raise ProjectFileError(
                f"Chart field '{key}' must be 'normal' or 'italic'."
            )
        return value

    if key == "bar_shape":
        if value not in ("rectangle", "rounded", "capsule", "lollipop"):
            raise ProjectFileError(
                "Chart field 'bar_shape' must be 'rectangle', 'rounded', "
                "'capsule', or 'lollipop'."
            )
        return value

    bar_enum_options = {
        "bar_appearance_mode": ("simple", "advanced", "unified"),
        "bar_fill_type": ("solid", "gradient", "texture"),
        "bar_gradient_direction": ("horizontal", "vertical", "diagonal"),
        "bar_texture_preset": (
            "noise",
            "brushed_metal",
            "grunge",
            "paper",
            "carbon",
            "custom_image",
        ),
        "bar_texture_blend_mode": (
            "overlay",
            "multiply",
            "screen",
            "soft_light",
        ),
        "bar_logo_position": (
            "outside",
            "inside",
            "outside_left",
            "inside_left",
            "inside_right",
            "hidden",
        ),
        "bar_logo_shape": ("adaptive", "circle", "rounded", "square"),
        "bar_secondary_logo_layout": ("badge", "side_by_side", "independent"),
        "bar_secondary_logo_position": (
            "outside_left",
            "inside_left",
            "inside_right",
            "hidden",
        ),
        "bar_secondary_logo_badge_corner": (
            "top_left",
            "top_right",
            "bottom_left",
            "bottom_right",
        ),
        "bar_secondary_logo_shape": ("adaptive", "circle", "rounded", "square"),
        "bar_vertical_layout_mode": ("manual", "fill_available"),
        "bar_label_position": (
            "left", "inside", "above", "outside", "outside_left",
            "inside_left", "inside_center", "inside_right", "outside_right",
        ),
        "bar_label_alignment": ("auto", "left", "center", "right"),
        "bar_value_position": ("auto", "outside", "inside", "above"),
        "bar_color_source": ("manual", "primary_logo"),
        "background_mode": ("color", "image"),
        "background_image_fit": ("cover", "contain", "stretch"),
        "background_motion": ("off", "forward_motion"),
    }

    if key in bar_enum_options:
        if value not in bar_enum_options[key]:
            options = ", ".join(bar_enum_options[key])
            raise ProjectFileError(
                f"Chart field '{key}' must be one of: {options}."
            )
        return value

    if key in (
        "bar_gradient_enabled",
        "bar_border_enabled",
        "bar_shadow_enabled",
        "bar_fill_use_category_color",
        "bar_texture_enabled",
        "bar_bevel_enabled",
        "bar_outer_glow_enabled",
        "bar_shine_enabled",
        "bar_track_enabled",
        "bar_logo_border_enabled",
        "bar_logo_background_enabled",
        "bar_secondary_logo_enabled",
        "bar_secondary_logo_border_enabled",
        "bar_secondary_logo_background_enabled",
        "bar_value_use_theme_color",
        "bar_value_border_enabled",
        "bar_value_shadow_enabled",
        "title_enabled",
        "subtitle_enabled",
        "time_label_enabled",
        "source_label_enabled",
        "rank_labels_enabled",
        "category_labels_enabled",
        "value_labels_enabled",
    ):
        if not isinstance(value, bool):
            raise ProjectFileError(f"Chart field '{key}' must be boolean.")
        return value

    if key in (
        "bar_border_color",
        "bar_shadow_color",
        "bar_fill_color_start",
        "bar_fill_color_center",
        "bar_fill_color_end",
        "bar_glow_color",
        "bar_track_color",
        "bar_logo_border_color",
        "bar_logo_background_color",
        "bar_secondary_logo_border_color",
        "bar_secondary_logo_background_color",
        "bar_value_color",
        "bar_value_border_color",
        "bar_value_shadow_color",
        "title_text_color",
        "subtitle_text_color",
        "label_text_color",
        "value_text_color",
        "time_label_text_color",
        "source_text_color",
        "rank_label_text_color",
    ):
        if key.endswith("_text_color") and value is None:
            return None

        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(f"Chart field '{key}' must be a non-empty color.")
        return value.strip()

    if key in (
        "bar_gradient_lighten",
        "bar_shadow_alpha",
        "bar_highlight_position",
        "bar_edge_darkening",
        "bar_texture_intensity",
        "bar_bevel_highlight_opacity",
        "bar_inner_shadow_opacity",
        "bar_top_highlight_opacity",
        "bar_bottom_shade_opacity",
        "bar_glow_opacity",
        "bar_inner_glow_opacity",
        "bar_shine_position",
        "bar_shine_opacity",
        "bar_track_opacity",
        "bar_logo_background_opacity",
        "bar_secondary_logo_background_opacity",
        "title_text_opacity",
        "subtitle_text_opacity",
        "label_text_opacity",
        "value_text_opacity",
        "time_label_opacity",
        "source_text_opacity",
        "rank_label_text_opacity",
        "background_motion_intensity",
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= value <= 1
        ):
            raise ProjectFileError(f"Chart field '{key}' must be from 0 to 1.")
        return value

    if key in (
        "bar_border_width",
        "bar_glow_blur",
        "bar_value_border_width",
        "bar_texture_contrast",
        "bar_logo_padding",
        "bar_logo_border_width",
        "bar_secondary_logo_size",
        "bar_secondary_logo_gap",
        "bar_secondary_logo_padding",
        "bar_secondary_logo_border_width",
        "background_motion_speed",
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value < 0
        ):
            raise ProjectFileError(f"Chart field '{key}' must be >= 0.")
        return value

    if key in (
        "bar_texture_scale",
        "bar_bevel_size",
        "bar_inner_shadow_size",
        "bar_shine_width",
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value <= 0
        ):
            raise ProjectFileError(f"Chart field '{key}' must be > 0.")
        return value

    if key in (
        "bar_gradient_color_count",
        "bar_shadow_offset_x",
        "bar_shadow_offset_y",
        "bar_value_shadow_offset_x",
        "bar_value_shadow_offset_y",
        "bar_vertical_top_padding",
        "bar_vertical_bottom_padding",
        "bar_label_offset_x",
        "bar_label_offset_y",
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProjectFileError(f"Chart field '{key}' must be an integer.")

        if key == "bar_gradient_color_count" and value not in (2, 3):
            raise ProjectFileError(
                "Chart field 'bar_gradient_color_count' must be 2 or 3."
            )
        if key in (
            "bar_vertical_top_padding",
            "bar_vertical_bottom_padding",
        ) and value < 0:
            raise ProjectFileError(f"Chart field '{key}' must be >= 0.")
        if key in ("bar_label_offset_x", "bar_label_offset_y") and not (
            -500 <= value <= 500
        ):
            raise ProjectFileError(
                f"Chart field '{key}' must be from -500 to 500."
            )
        return value

    if key == "bar_texture_custom_image":
        if value is None:
            return None

        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(
                "Chart field 'bar_texture_custom_image' must be null or a path."
            )

        return value.strip()

    if key in ("background_color_override", "background_image_path"):
        if value is None:
            return None

        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(
                f"Chart field '{key}' must be null or a non-empty string."
            )

        return value.strip()

    if key == "frame_output_mode":
        if value not in ("png_sequence", "ffmpeg_stream"):
            raise ProjectFileError(
                "Chart field 'frame_output_mode' must be 'png_sequence' "
                "or 'ffmpeg_stream'."
            )
        return value

    if key == "png_compress_level":
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 9:
            raise ProjectFileError(
                "Chart field 'png_compress_level' must be an integer from 0 to 9."
            )

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

    if key in (
        "rank_label_min_x",
        "rank_label_label_gap",
        "label_min_x",
        "bar_gap",
        "primary_logo_min_size",
    ):
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


def _convert_export_value(key, value):
    if key == "mode":
        if value not in ("standard", "short"):
            raise ProjectFileError(
                "Export field 'mode' must be 'standard' or 'short'."
            )
        return value

    if key in ("short_width", "short_height"):
        expected = 1080 if key == "short_width" else 1920
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value != expected
        ):
            raise ProjectFileError(
                f"Export field '{key}' must be {expected}."
            )
        return value

    if key in ("short_from_period", "short_to_period"):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProjectFileError(
                f"Export field '{key}' must be null or an integer period."
            )
        return value

    if key in (
        "short_intro_enabled",
        "short_context_enabled",
        "short_outro_enabled",
        "short_include_fun_facts",
    ):
        if not isinstance(value, bool):
            raise ProjectFileError(f"Export field '{key}' must be boolean.")
        return value

    if key in ("short_intro_duration", "short_outro_duration"):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= value <= 60
        ):
            raise ProjectFileError(
                f"Export field '{key}' must be from 0 to 60 seconds."
            )
        return float(value)

    if key in (
        "short_intro_text",
        "short_context_title",
        "short_context_subtitle",
        "short_outro_text",
    ):
        if not isinstance(value, str):
            raise ProjectFileError(f"Export field '{key}' must be a string.")
        return value

    return value


def _convert_animation_value(key, value):
    if key == "motion_mode":
        if value not in ("transition_easing", "continuous"):
            raise ProjectFileError(
                "Animation field 'motion_mode' must be 'transition_easing' "
                "or 'continuous'."
            )

        return value

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
    if key in ("year_column", "name_column", "value_column"):
        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(
                f"Dataset field '{key}' must be a non-empty string."
            )
        return value.strip()

    if key == "time_label_column":
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(
                "Dataset field 'time_label_column' must be null or a non-empty string."
            )
        return value.strip()

    if key in (
        "category_labels",
        "category_colors",
        "category_logos",
        "category_secondary_logos",
    ):
        return _convert_string_map(value, f"Dataset field '{key}'")

    return value


def _convert_fun_fact_value(key, value):
    if key.endswith("_font_weight"):
        if value not in ("normal", "bold"):
            raise ProjectFileError(
                f"Fun facts field '{key}' must be 'normal' or 'bold'."
            )
        return value
    if key.endswith("_font_style"):
        if value not in ("normal", "italic"):
            raise ProjectFileError(
                f"Fun facts field '{key}' must be 'normal' or 'italic'."
            )
        return value
    if key == "enabled":
        if not isinstance(value, bool):
            raise ProjectFileError("Fun facts field 'enabled' must be boolean.")
        return value
    if key == "source":
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ProjectFileError(
                "Fun facts field 'source' must be null or a non-empty path."
            )
        return value.strip()
    if key == "layout":
        if value not in ("right_panel", "editorial_right", "editorial_floating"):
            raise ProjectFileError(
                "Fun facts field 'layout' must be 'right_panel', "
                "'editorial_right', or 'editorial_floating'."
            )
        return value
    if key == "panel_width":
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 160:
            raise ProjectFileError(
                "Fun facts field 'panel_width' must be null or at least 160."
            )
        return value
    if key == "panel_margin":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProjectFileError("Fun facts field 'panel_margin' must be >= 0.")
        return value
    if key == "panel_padding":
        if isinstance(value, bool) or not isinstance(value, int) or value < 8:
            raise ProjectFileError("Fun facts field 'panel_padding' must be >= 8.")
        return value
    if key in ("fade_in", "fade_out"):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= value <= 1
        ):
            raise ProjectFileError(f"Fun facts field '{key}' must be from 0 to 1.")
        return float(value)
    if key == "editorial_background_mode":
        if value not in ("transparent", "solid", "card"):
            raise ProjectFileError("Invalid editorial background mode.")
        return value
    if key == "editorial_background_texture":
        if value not in ("none", "grain", "paper", "dots", "diagonal"):
            raise ProjectFileError("Invalid editorial background texture.")
        return value
    if key == "editorial_image_fit":
        if value not in ("contain", "cover"):
            raise ProjectFileError("Invalid editorial image fit.")
        return value
    if key == "editorial_orientation":
        if value not in ("vertical", "horizontal"):
            raise ProjectFileError(
                "Editorial orientation must be 'vertical' or 'horizontal'."
            )
        return value
    if key == "editorial_image_position":
        if value not in ("left", "right"):
            raise ProjectFileError(
                "Editorial image position must be 'left' or 'right'."
            )
        return value
    if key in (
        "editorial_background_color",
        "editorial_headline_color",
        "editorial_body_color",
        "editorial_credit_color",
    ):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ProjectFileError(f"Fun facts field '{key}' must be null or a color.")
        return value.strip() if isinstance(value, str) else None
    if key in (
        "editorial_background_texture_intensity",
        "editorial_headline_opacity",
        "editorial_body_opacity",
        "editorial_credit_opacity",
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= value <= 1
        ):
            raise ProjectFileError(f"Fun facts field '{key}' must be from 0 to 1.")
        return float(value)
    if key == "editorial_image_area_ratio":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 0.8:
            raise ProjectFileError("Editorial image area ratio must be from 0 to 0.8.")
        return float(value)
    if key in ("editorial_headline_size", "editorial_body_size", "editorial_credit_size", "editorial_text_image_gap", "editorial_top_offset"):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProjectFileError(f"Fun facts field '{key}' must be a non-negative integer.")
        return value
    if key in ("editorial_card_x", "editorial_card_y"):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProjectFileError(
                f"Fun facts field '{key}' must be null or a non-negative integer."
            )
        return value
    if key in ("editorial_card_width", "editorial_card_height"):
        if value is None:
            return None
        minimum = 240 if key == "editorial_card_width" else 140
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ProjectFileError(
                f"Fun facts field '{key}' must be null or at least {minimum}."
            )
        return value
    if key == "editorial_collision_gap":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProjectFileError(
                "Fun facts field 'editorial_collision_gap' must be >= 0."
            )
        return value
    if key == "editorial_reposition_time_label":
        if not isinstance(value, bool):
            raise ProjectFileError("editorial_reposition_time_label must be boolean.")
        return value
    return value


def _apply_category_styles(dataset_config, categories):
    if categories is None:
        categories = {}

    if not isinstance(categories, dict):
        raise ProjectFileError("Project section 'categories' must be an object.")

    labels = dict(dataset_config.category_labels)
    colors = dict(dataset_config.category_colors)
    logos = dict(dataset_config.category_logos)
    secondary_logos = dict(dataset_config.category_secondary_logos)

    for raw_name, style in categories.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ProjectFileError("Category names must be non-empty strings.")

        if not isinstance(style, dict):
            raise ProjectFileError(
                f"Category '{raw_name}' must be an object."
            )

        _reject_unknown_keys(
            style,
            {"label", "color", "logo", "secondary_logo"},
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

        if "secondary_logo" in style:
            _update_optional_style(
                secondary_logos,
                raw_name,
                style["secondary_logo"],
                f"Category '{raw_name}' field 'secondary_logo'",
            )

    return replace(
        dataset_config,
        category_labels=labels,
        category_colors=colors,
        category_logos=logos,
        category_secondary_logos=secondary_logos,
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
