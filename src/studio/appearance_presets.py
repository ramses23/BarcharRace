import copy
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from config.project_file_loader import (
    ProjectFileError,
    load_project_data as load_project_config,
)
from config.layout_config import get_layout_preset
from studio.project_builder import BAR_STYLE_FIELDS
from studio.project_storage import atomic_write_json


APPEARANCE_PRESET_SCHEMA_VERSION = 15
CANVAS_APPEARANCE_FIELDS = (
    "layout_preset",
    "theme",
    "typography_preset",
    "background_mode",
    "background_color_override",
    "background_image_path",
    "background_image_fit",
    "background_motion",
    "background_motion_speed",
    "background_motion_intensity",
    "value_grid_enabled",
    "value_grid_mode",
    "value_grid_tick_labels_enabled",
    "value_grid_tick_value_format",
    "value_grid_line_color",
    "value_grid_line_opacity",
    "value_grid_line_thickness",
    "value_grid_tick_text_color",
    "value_grid_tick_text_opacity",
    "value_grid_tick_font_size",
    "value_grid_tick_font_weight",
    "value_grid_tick_font_style",
    "value_grid_target_tick_count",
    "max_visible_bars",
    "title_font_family",
    "subtitle_font_family",
    "label_font_family",
    "value_font_family",
    "time_label_font_family",
    "source_font_family",
    "rank_label_font_family",
    "title_font_weight",
    "title_font_style",
    "subtitle_font_weight",
    "subtitle_font_style",
    "time_label_font_weight",
    "time_label_font_style",
    "source_font_weight",
    "source_font_style",
    "label_font_weight",
    "label_font_style",
    "value_font_weight",
    "value_font_style",
    "rank_label_font_weight",
    "rank_label_font_style",
    "title_text_color",
    "title_text_opacity",
    "subtitle_text_color",
    "subtitle_text_opacity",
    "label_text_color",
    "label_text_opacity",
    "value_text_color",
    "value_text_opacity",
    "time_label_text_color",
    "time_label_opacity",
    "source_text_color",
    "source_text_opacity",
    "rank_label_text_color",
    "rank_label_text_opacity",
    "title_font_size",
    "subtitle_font_size",
    "label_font_size",
    "value_font_size",
    "time_label_font_size",
    "source_font_size",
    "rank_label_font_size",
    "title_enabled",
    "subtitle_enabled",
    "time_label_enabled",
    "source_label_enabled",
    "rank_labels_enabled",
    "category_labels_enabled",
    "value_labels_enabled",
    "title_x",
    "title_y",
    "subtitle_x",
    "subtitle_y",
    "time_label_x",
    "time_label_y",
    "date_style",
    "flip_calendar_scale",
    "flip_calendar_card_background",
    "flip_calendar_card_opacity",
    "flip_calendar_text_color",
    "flip_calendar_border_color",
    "flip_calendar_shadow_opacity",
    "flip_calendar_corner_radius",
    "flip_calendar_flip_duration_frames",
    "source_x",
    "source_y",
    "label_min_x",
    "left_margin",
    "rank_label_gap",
)
BAR_APPEARANCE_FIELDS = (
    "value_format",
    "bar_gap",
    "bar_color_source",
    "primary_logo_min_size",
    "start_bars_at_zero",
    "leader_full_width_point",
    *BAR_STYLE_FIELDS,
)
FUN_FACT_APPEARANCE_FIELDS = (
    "layout",
    "panel_width",
    "panel_margin",
    "panel_padding",
    "fade_in",
    "fade_out",
    "editorial_background_mode",
    "editorial_background_color",
    "editorial_background_texture",
    "editorial_background_texture_intensity",
    "editorial_headline_size",
    "editorial_headline_font_weight",
    "editorial_headline_font_style",
    "editorial_headline_color",
    "editorial_headline_opacity",
    "editorial_body_size",
    "editorial_body_font_weight",
    "editorial_body_font_style",
    "editorial_body_color",
    "editorial_body_opacity",
    "editorial_credit_size",
    "editorial_credit_font_weight",
    "editorial_credit_font_style",
    "editorial_credit_color",
    "editorial_credit_opacity",
    "editorial_image_area_ratio",
    "editorial_image_fit",
    "editorial_text_image_gap",
    "editorial_top_offset",
    "editorial_reposition_time_label",
    "editorial_orientation",
    "editorial_card_x",
    "editorial_card_y",
    "editorial_card_width",
    "editorial_card_height",
    "editorial_image_position",
    "editorial_collision_gap",
    "editorial_layout_mode",
    "editorial_headline_alignment",
    "editorial_body_alignment",
    "editorial_placement_mode",
    "editorial_keep_inside_safe_area",
    "editorial_background_opacity",
    "editorial_border_color",
    "editorial_border_opacity",
    "editorial_border_width",
    "editorial_corner_radius",
    "editorial_shadow_opacity",
    "editorial_shadow_blur",
    "editorial_shadow_offset",
    "editorial_protect_top_n",
    "editorial_bar_clearance",
)
ANIMATION_APPEARANCE_FIELDS = (
    "rank_movement_duration",
)
APPEARANCE_CHART_FIELDS = (
    *CANVAS_APPEARANCE_FIELDS,
    *BAR_APPEARANCE_FIELDS,
)
_ROOT_FIELDS_BY_VERSION = {
    1: {"schema_version", "name", "canvas", "bars"},
    2: {"schema_version", "name", "canvas", "bars", "fun_facts"},
    3: {"schema_version", "name", "canvas", "bars", "fun_facts"},
    4: {"schema_version", "name", "canvas", "bars", "fun_facts"},
    5: {"schema_version", "name", "canvas", "bars", "fun_facts"},
    6: {"schema_version", "name", "canvas", "bars", "fun_facts"},
    7: {"schema_version", "name", "canvas", "bars", "fun_facts"},
    8: {"schema_version", "name", "canvas", "bars", "fun_facts"},
    9: {"schema_version", "name", "canvas", "bars", "fun_facts"},
    10: {
        "schema_version",
        "name",
        "canvas",
        "bars",
        "fun_facts",
        "animation",
    },
    11: {
        "schema_version",
        "name",
        "canvas",
        "bars",
        "fun_facts",
        "animation",
    },
    12: {
        "schema_version",
        "name",
        "canvas",
        "bars",
        "fun_facts",
        "animation",
    },
    13: {
        "schema_version",
        "name",
        "canvas",
        "bars",
        "fun_facts",
        "animation",
    },
    14: {
        "schema_version",
        "name",
        "canvas",
        "bars",
        "fun_facts",
        "animation",
    },
    15: {
        "schema_version",
        "name",
        "canvas",
        "bars",
        "fun_facts",
        "animation",
    },
}
_MAX_NAME_LENGTH = 80


class AppearancePresetError(ValueError):
    pass


@dataclass(frozen=True)
class AppearancePreset:
    name: str
    canvas: dict
    bars: dict
    fun_facts: dict | None = None
    animation: dict | None = None
    path: Path | None = None
    schema_version: int = APPEARANCE_PRESET_SCHEMA_VERSION

    @property
    def chart_values(self):
        return {
            **copy.deepcopy(self.canvas),
            **copy.deepcopy(self.bars),
        }

    def to_dict(self):
        data = {
            "schema_version": self.schema_version,
            "name": self.name,
            "canvas": copy.deepcopy(self.canvas),
            "bars": copy.deepcopy(self.bars),
        }
        if self.schema_version >= 2:
            data["fun_facts"] = copy.deepcopy(self.fun_facts)
        if self.schema_version >= 10:
            data["animation"] = copy.deepcopy(self.animation)
        return data


@dataclass(frozen=True)
class AppearancePresetCatalog:
    presets: tuple[AppearancePreset, ...]
    errors: tuple[str, ...]


def build_appearance_preset(name, project_data):
    name = _validated_name(name)

    if not isinstance(project_data, dict):
        raise AppearancePresetError("Project data must be an object.")

    try:
        preset = load_project_config(project_data, default_name=name)
    except ProjectFileError as exc:
        raise AppearancePresetError(
            f"The current project cannot become an appearance preset: {exc}"
        ) from exc

    chart_config = preset.chart_config
    fun_fact_config = preset.fun_fact_config
    raw_chart = project_data.get("chart")
    raw_chart = raw_chart if isinstance(raw_chart, dict) else {}

    def current_value(field):
        if field == "theme":
            return chart_config.theme.name
        if field == "value_format":
            return raw_chart.get("value_format", "decimal")
        if field == "max_visible_bars":
            return (
                8
                if chart_config.max_visible_bars is None
                else chart_config.max_visible_bars
            )
        return getattr(chart_config, field)

    candidate = AppearancePreset(
        name=name,
        canvas={
            field: copy.deepcopy(current_value(field))
            for field in CANVAS_APPEARANCE_FIELDS
        },
        bars={
            field: copy.deepcopy(current_value(field))
            for field in BAR_APPEARANCE_FIELDS
        },
        fun_facts={
            field: copy.deepcopy(getattr(fun_fact_config, field))
            for field in FUN_FACT_APPEARANCE_FIELDS
        },
        animation={
            field: copy.deepcopy(getattr(chart_config.animation, field))
            for field in ANIMATION_APPEARANCE_FIELDS
        },
    )
    return _validated_preset(candidate.to_dict())


def apply_appearance_preset(project_data, preset):
    if not isinstance(project_data, dict):
        raise AppearancePresetError("Project data must be an object.")
    if not isinstance(preset, AppearancePreset):
        raise AppearancePresetError("Appearance preset is invalid.")

    updated = copy.deepcopy(project_data)
    chart = updated.setdefault("chart", {})

    if not isinstance(chart, dict):
        raise AppearancePresetError("Project section 'chart' must be an object.")

    chart.update(preset.chart_values)
    animation = updated.setdefault("animation", {})
    if not isinstance(animation, dict):
        raise AppearancePresetError(
            "Project section 'animation' must be an object."
        )
    animation.update(copy.deepcopy(preset.animation or {
        "rank_movement_duration": 1.0,
    }))
    if preset.fun_facts is not None:
        fun_facts = updated.setdefault("fun_facts", {})
        if not isinstance(fun_facts, dict):
            raise AppearancePresetError(
                "Project section 'fun_facts' must be an object."
            )
        fun_facts.update(copy.deepcopy(preset.fun_facts))
    return updated


def load_appearance_preset(path):
    path = Path(path)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AppearancePresetError(
            f"Appearance preset not found: {path}"
        ) from exc
    except OSError as exc:
        raise AppearancePresetError(
            f"Could not read appearance preset: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise AppearancePresetError(
            f"Invalid JSON in appearance preset '{path.name}': {exc.msg}"
        ) from exc

    preset = _validated_preset(data)
    return AppearancePreset(
        name=preset.name,
        canvas=preset.canvas,
        bars=preset.bars,
        fun_facts=preset.fun_facts,
        animation=preset.animation,
        path=path,
        schema_version=preset.schema_version,
    )


def load_appearance_preset_catalog(directory):
    directory = Path(directory)

    if not directory.exists():
        return AppearancePresetCatalog((), ())
    if not directory.is_dir():
        return AppearancePresetCatalog(
            (),
            (f"Appearance preset path is not a directory: {directory}",),
        )

    presets = []
    errors = []

    for path in sorted(directory.glob("*.json"), key=lambda item: item.name.casefold()):
        try:
            presets.append(load_appearance_preset(path))
        except AppearancePresetError as exc:
            errors.append(str(exc))

    presets.sort(key=lambda preset: preset.name.casefold())
    return AppearancePresetCatalog(tuple(presets), tuple(errors))


def save_appearance_preset(preset, directory, *, overwrite=False):
    if not isinstance(preset, AppearancePreset):
        raise AppearancePresetError("Appearance preset is invalid.")

    preset = _validated_preset(preset.to_dict())
    directory = Path(directory)
    path = directory / f"{appearance_preset_key(preset.name)}.json"

    if path.exists() and not overwrite:
        raise AppearancePresetError(
            f"Appearance preset '{preset.name}' already exists."
        )

    try:
        atomic_write_json(preset.to_dict(), path)
    except OSError as exc:
        raise AppearancePresetError(
            f"Could not save appearance preset '{preset.name}': {exc}"
        ) from exc

    return AppearancePreset(
        name=preset.name,
        canvas=preset.canvas,
        bars=preset.bars,
        fun_facts=preset.fun_facts,
        animation=preset.animation,
        path=path,
        schema_version=preset.schema_version,
    )


def delete_appearance_preset(preset, directory):
    if not isinstance(preset, AppearancePreset) or preset.path is None:
        raise AppearancePresetError("Appearance preset is not stored on disk.")

    directory = Path(directory).resolve()
    path = preset.path.resolve()

    if path.parent != directory or path.suffix.lower() != ".json":
        raise AppearancePresetError("Appearance preset path is outside its library.")

    try:
        path.unlink()
    except FileNotFoundError as exc:
        raise AppearancePresetError(
            f"Appearance preset not found: {preset.name}"
        ) from exc
    except OSError as exc:
        raise AppearancePresetError(
            f"Could not delete appearance preset '{preset.name}': {exc}"
        ) from exc


def appearance_preset_key(name):
    name = _validated_name(name)
    normalized = unicodedata.normalize("NFKD", name)
    without_accents = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    key = re.sub(r"[^a-z0-9]+", "_", without_accents.casefold()).strip("_")

    if not key:
        raise AppearancePresetError(
            "Appearance preset name must contain a letter or number."
        )

    return key


def _validated_preset(data):
    if not isinstance(data, dict):
        raise AppearancePresetError("Appearance preset root must be an object.")

    schema_version = data.get("schema_version")
    expected_root_fields = _ROOT_FIELDS_BY_VERSION.get(schema_version)

    if expected_root_fields is None:
        raise AppearancePresetError(
            "Unsupported appearance preset schema version: "
            f"{schema_version}"
        )

    unknown = set(data) - expected_root_fields
    missing = expected_root_fields - set(data)

    if unknown:
        raise AppearancePresetError(
            "Unknown appearance preset fields: " + ", ".join(sorted(unknown))
        )
    if missing:
        raise AppearancePresetError(
            "Missing appearance preset fields: " + ", ".join(sorted(missing))
        )
    name = _validated_name(data["name"])
    canvas_defaults = {}
    if schema_version <= 10:
        canvas_defaults.update({
            "date_style": "standard",
            "flip_calendar_scale": 1.0,
            "flip_calendar_card_background": "#20252B",
            "flip_calendar_text_color": "#F5F4EF",
            "flip_calendar_border_color": "#4B5159",
            "flip_calendar_shadow_opacity": 0.32,
            "flip_calendar_corner_radius": 12.0,
            "flip_calendar_flip_duration_frames": 4,
        })
    if schema_version <= 11:
        canvas_defaults["flip_calendar_card_opacity"] = 1.0
    if schema_version <= 7:
        canvas_defaults["value_grid_tick_value_format"] = "same"
    if schema_version <= 6:
        canvas_defaults.update({
            "value_grid_enabled": False,
            "value_grid_mode": "dynamic",
            "value_grid_tick_labels_enabled": True,
            "value_grid_line_color": "#FFFFFF",
            "value_grid_line_opacity": 0.18,
            "value_grid_line_thickness": 1.0,
            "value_grid_tick_text_color": None,
            "value_grid_tick_text_opacity": 0.72,
            "value_grid_tick_font_size": 16,
            "value_grid_tick_font_weight": "normal",
            "value_grid_tick_font_style": "normal",
            "value_grid_target_tick_count": 5,
        })
    if schema_version <= 5:
        canvas_defaults.update({
            "background_motion": "off",
            "background_motion_speed": 1.0,
            "background_motion_intensity": 0.35,
            "title_font_weight": "bold",
            "title_font_style": "normal",
            "subtitle_font_weight": "normal",
            "subtitle_font_style": "normal",
            "time_label_font_weight": "bold",
            "time_label_font_style": "normal",
            "source_font_weight": "normal",
            "source_font_style": "normal",
            "label_font_weight": "normal",
            "label_font_style": "normal",
            "value_font_weight": "normal",
            "value_font_style": "normal",
            "rank_label_font_weight": "bold",
            "rank_label_font_style": "normal",
        })
    if schema_version <= 4:
        canvas_defaults.update({
            "title_text_opacity": 1.0,
            "subtitle_text_opacity": 1.0,
            "label_text_opacity": 1.0,
            "value_text_opacity": 1.0,
            "source_text_opacity": 1.0,
            "rank_label_text_opacity": 1.0,
        })
        if schema_version <= 3:
            canvas_defaults["time_label_opacity"] = 0.22
    canvas = _validated_section(
        data["canvas"],
        expected_fields=CANVAS_APPEARANCE_FIELDS,
        section_name="canvas",
        missing_defaults=canvas_defaults or None,
    )
    bar_defaults = {}
    if schema_version <= 12:
        bar_defaults.update({
            "bar_label_border_enabled": False,
            "bar_label_border_color": "#000000",
            "bar_label_border_opacity": 1.0,
            "bar_label_border_width": 1.0,
            "bar_label_shadow_enabled": False,
            "bar_label_shadow_color": "#000000",
            "bar_label_shadow_opacity": 0.45,
            "bar_label_shadow_offset_x": 1,
            "bar_label_shadow_offset_y": 1,
        })
    if schema_version <= 8:
        bar_defaults.update({
            "start_bars_at_zero": False,
            "leader_full_width_point": 1.0,
        })
    if schema_version <= 5:
        bar_defaults.update({
            "bar_gap": _legacy_bar_gap(data["canvas"]),
            "bar_color_source": "manual",
            "primary_logo_min_size": 0,
        })
        if schema_version == 1:
            bar_defaults.update({
                "bar_label_offset_x": 0,
                "bar_label_offset_y": 0,
            })
    bars = _validated_section(
        data["bars"],
        expected_fields=BAR_APPEARANCE_FIELDS,
        section_name="bars",
        missing_defaults=bar_defaults or None,
    )
    fun_facts = None
    if schema_version >= 2:
        fun_fact_defaults = None
        if schema_version <= 13:
            fun_fact_defaults = {
                "editorial_layout_mode": "reserved",
                "editorial_headline_alignment": "left",
                "editorial_body_alignment": "left",
                "editorial_placement_mode": "manual",
                "editorial_keep_inside_safe_area": False,
                "editorial_background_opacity": 1.0,
                "editorial_border_color": None,
                "editorial_border_opacity": 1.0,
                "editorial_border_width": 1,
                "editorial_corner_radius": None,
                "editorial_shadow_opacity": 0.0,
                "editorial_shadow_blur": 0,
                "editorial_shadow_offset": 0,
                "editorial_protect_top_n": 3,
                "editorial_bar_clearance": 16,
            }
        elif schema_version == 14:
            fun_fact_defaults = {
                "editorial_protect_top_n": 3,
                "editorial_bar_clearance": 16,
            }
        if schema_version <= 5:
            fun_fact_defaults.update({
                "editorial_headline_font_weight": "bold",
                "editorial_headline_font_style": "normal",
                "editorial_body_font_weight": "normal",
                "editorial_body_font_style": "normal",
                "editorial_credit_font_weight": "normal",
                "editorial_credit_font_style": "normal",
                "editorial_background_texture": "none",
                "editorial_background_texture_intensity": 0.25,
                "editorial_headline_color": None,
                "editorial_headline_opacity": 1.0,
                "editorial_body_color": None,
                "editorial_body_opacity": 1.0,
                "editorial_credit_color": None,
                "editorial_credit_opacity": 1.0,
            })
            if schema_version == 2:
                fun_fact_defaults.update({
                    "editorial_orientation": "vertical",
                    "editorial_card_x": None,
                    "editorial_card_y": None,
                    "editorial_card_width": None,
                    "editorial_card_height": None,
                    "editorial_image_position": "right",
                    "editorial_collision_gap": 24,
                })
        fun_facts = _validated_section(
            data["fun_facts"],
            expected_fields=FUN_FACT_APPEARANCE_FIELDS,
            section_name="fun_facts",
            missing_defaults=fun_fact_defaults,
        )

    animation = _validated_section(
        (
            data["animation"]
            if schema_version >= 10
            else {"rank_movement_duration": 1.0}
        ),
        expected_fields=ANIMATION_APPEARANCE_FIELDS,
        section_name="animation",
    )

    try:
        validation_project = {
            "name": name,
            "chart": {**canvas, **bars},
            "animation": animation,
        }
        if fun_facts is not None:
            validation_project["fun_facts"] = fun_facts
        load_project_config(validation_project, default_name=name)
    except ProjectFileError as exc:
        raise AppearancePresetError(
            f"Invalid appearance preset '{name}': {exc}"
        ) from exc

    return AppearancePreset(
        name=name,
        canvas=canvas,
        bars=bars,
        fun_facts=fun_facts,
        animation=animation,
        schema_version=schema_version,
    )


def _validated_section(
    data,
    *,
    expected_fields,
    section_name,
    missing_defaults=None,
):
    if not isinstance(data, dict):
        raise AppearancePresetError(
            f"Appearance preset section '{section_name}' must be an object."
        )

    values = copy.deepcopy(data)
    if isinstance(missing_defaults, dict):
        for field, value in missing_defaults.items():
            values.setdefault(field, copy.deepcopy(value))

    expected = set(expected_fields)
    unknown = set(values) - expected
    missing = expected - set(values)

    if unknown:
        raise AppearancePresetError(
            f"Unknown {section_name} fields: " + ", ".join(sorted(unknown))
        )
    if missing:
        raise AppearancePresetError(
            f"Missing {section_name} fields: " + ", ".join(sorted(missing))
        )

    return {
        field: copy.deepcopy(values[field])
        for field in expected_fields
    }


def _legacy_bar_gap(canvas):
    try:
        return get_layout_preset(
            canvas.get("layout_preset", "youtube_1080p")
        ).bar_gap
    except (AttributeError, ValueError):
        return 18


def _validated_name(name):
    if not isinstance(name, str) or not name.strip():
        raise AppearancePresetError(
            "Appearance preset name must be a non-empty string."
        )

    name = " ".join(name.strip().split())

    if len(name) > _MAX_NAME_LENGTH:
        raise AppearancePresetError(
            f"Appearance preset name must be {_MAX_NAME_LENGTH} characters or fewer."
        )
    if any(ord(character) < 32 for character in name):
        raise AppearancePresetError(
            "Appearance preset name cannot contain control characters."
        )

    return name
