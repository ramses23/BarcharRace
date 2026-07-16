import base64
import re
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from ui.component_v2 import (
    component_renderer,
    component_source,
    component_state_value,
    component_v2_runtime_available,
)


BAR_SHAPES = ("rectangle", "rounded", "capsule", "lollipop")

DEFAULT_BAR_STYLE = {
    "bar_shape": "rectangle",
    "bar_appearance_mode": "simple",
    "bar_gradient_enabled": True,
    "bar_gradient_lighten": 0.22,
    "bar_border_enabled": False,
    "bar_border_color": "#FFFFFF",
    "bar_border_width": 1.5,
    "bar_shadow_enabled": True,
    "bar_shadow_color": "#000000",
    "bar_shadow_alpha": 0.12,
    "bar_shadow_offset_x": 5,
    "bar_shadow_offset_y": 4,
    "bar_fill_type": "gradient",
    "bar_gradient_direction": "horizontal",
    "bar_gradient_color_count": 3,
    "bar_fill_use_category_color": True,
    "bar_fill_color_start": "#315F8A",
    "bar_fill_color_center": "#7FAED6",
    "bar_fill_color_end": "#4E79A7",
    "bar_highlight_position": 0.5,
    "bar_edge_darkening": 0.0,
    "bar_texture_enabled": False,
    "bar_texture_preset": "noise",
    "bar_texture_custom_image": None,
    "bar_texture_intensity": 0.2,
    "bar_texture_scale": 1.0,
    "bar_texture_contrast": 1.0,
    "bar_texture_blend_mode": "overlay",
    "bar_bevel_enabled": False,
    "bar_bevel_size": 0.12,
    "bar_bevel_highlight_opacity": 0.25,
    "bar_inner_shadow_opacity": 0.0,
    "bar_inner_shadow_size": 0.12,
    "bar_top_highlight_opacity": 0.0,
    "bar_bottom_shade_opacity": 0.0,
    "bar_outer_glow_enabled": False,
    "bar_glow_color": "#FFFFFF",
    "bar_glow_opacity": 0.25,
    "bar_glow_blur": 8.0,
    "bar_inner_glow_opacity": 0.0,
    "bar_shine_enabled": False,
    "bar_shine_position": 0.5,
    "bar_shine_width": 0.15,
    "bar_shine_opacity": 0.25,
    "bar_track_enabled": False,
    "bar_track_color": "#000000",
    "bar_track_opacity": 0.12,
    "bar_logo_position": "outside_left",
    "bar_logo_shape": "adaptive",
    "bar_logo_padding": 4.0,
    "bar_logo_border_enabled": False,
    "bar_logo_border_color": "#FFFFFF",
    "bar_logo_border_width": 1.5,
    "bar_logo_background_enabled": False,
    "bar_logo_background_color": "#FFFFFF",
    "bar_logo_background_opacity": 1.0,
    "bar_secondary_logo_enabled": True,
    "bar_secondary_logo_layout": "badge",
    "bar_secondary_logo_position": "inside_right",
    "bar_secondary_logo_badge_corner": "bottom_right",
    "bar_secondary_logo_shape": "circle",
    "bar_secondary_logo_size": 24,
    "bar_secondary_logo_gap": 6.0,
    "bar_secondary_logo_padding": 2.0,
    "bar_secondary_logo_border_enabled": True,
    "bar_secondary_logo_border_color": "#FFFFFF",
    "bar_secondary_logo_border_width": 1.5,
    "bar_secondary_logo_background_enabled": False,
    "bar_secondary_logo_background_color": "#FFFFFF",
    "bar_secondary_logo_background_opacity": 1.0,
    "bar_label_position": "left",
    "bar_label_alignment": "auto",
    "bar_value_position": "auto",
    "bar_value_use_theme_color": True,
    "bar_value_color": "#FFFFFF",
    "bar_value_border_enabled": False,
    "bar_value_border_color": "#000000",
    "bar_value_border_width": 1.0,
    "bar_value_shadow_enabled": False,
    "bar_value_shadow_color": "#000000",
    "bar_value_shadow_offset_x": 1,
    "bar_value_shadow_offset_y": 1,
}

_ENUM_FIELDS = {
    "bar_shape": BAR_SHAPES,
    "bar_appearance_mode": ("simple", "advanced"),
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
    "bar_texture_blend_mode": ("overlay", "multiply", "screen", "soft_light"),
    "bar_logo_position": (
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
    "bar_label_position": ("left", "inside", "above", "outside"),
    "bar_label_alignment": ("auto", "left", "center", "right"),
    "bar_value_position": ("auto", "outside", "inside", "above"),
}
_BOOLEAN_FIELDS = (
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
)
_COLOR_FIELDS = (
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
)
_FLOAT_BOUNDS = {
    "bar_gradient_lighten": (0.0, 1.0),
    "bar_border_width": (0.0, 12.0),
    "bar_shadow_alpha": (0.0, 1.0),
    "bar_highlight_position": (0.0, 1.0),
    "bar_edge_darkening": (0.0, 1.0),
    "bar_texture_intensity": (0.0, 1.0),
    "bar_texture_scale": (0.1, 8.0),
    "bar_texture_contrast": (0.0, 3.0),
    "bar_bevel_size": (0.01, 0.5),
    "bar_bevel_highlight_opacity": (0.0, 1.0),
    "bar_inner_shadow_opacity": (0.0, 1.0),
    "bar_inner_shadow_size": (0.01, 0.5),
    "bar_top_highlight_opacity": (0.0, 1.0),
    "bar_bottom_shade_opacity": (0.0, 1.0),
    "bar_glow_opacity": (0.0, 1.0),
    "bar_glow_blur": (0.0, 40.0),
    "bar_inner_glow_opacity": (0.0, 1.0),
    "bar_shine_position": (0.0, 1.0),
    "bar_shine_width": (0.01, 0.8),
    "bar_shine_opacity": (0.0, 1.0),
    "bar_track_opacity": (0.0, 1.0),
    "bar_logo_padding": (0.0, 20.0),
    "bar_logo_border_width": (0.0, 8.0),
    "bar_logo_background_opacity": (0.0, 1.0),
    "bar_secondary_logo_size": (4.0, 160.0),
    "bar_secondary_logo_gap": (0.0, 40.0),
    "bar_secondary_logo_padding": (0.0, 20.0),
    "bar_secondary_logo_border_width": (0.0, 8.0),
    "bar_secondary_logo_background_opacity": (0.0, 1.0),
    "bar_value_border_width": (0.0, 8.0),
}
_INTEGER_BOUNDS = {
    "bar_gradient_color_count": (2, 3),
    "bar_shadow_offset_x": (-40, 40),
    "bar_shadow_offset_y": (-40, 40),
    "bar_value_shadow_offset_x": (-20, 20),
    "bar_value_shadow_offset_y": (-20, 20),
}

_SIMPLE_FIELDS = {
    "bar_gradient_enabled",
    "bar_gradient_lighten",
}
_FRAME_FIELDS = {
    "bar_border_enabled",
    "bar_border_color",
    "bar_border_width",
    "bar_shadow_enabled",
    "bar_shadow_color",
    "bar_shadow_alpha",
    "bar_shadow_offset_x",
    "bar_shadow_offset_y",
}
_FILL_FIELDS = {
    "bar_fill_type",
    "bar_gradient_direction",
    "bar_gradient_color_count",
    "bar_fill_use_category_color",
    "bar_fill_color_start",
    "bar_fill_color_center",
    "bar_fill_color_end",
    "bar_highlight_position",
    "bar_edge_darkening",
}
_TEXTURE_FIELDS = {
    "bar_texture_enabled",
    "bar_texture_preset",
    "bar_texture_intensity",
    "bar_texture_scale",
    "bar_texture_contrast",
    "bar_texture_blend_mode",
}
_DEPTH_FIELDS = {
    "bar_bevel_enabled",
    "bar_bevel_size",
    "bar_bevel_highlight_opacity",
    "bar_inner_shadow_opacity",
    "bar_inner_shadow_size",
    "bar_top_highlight_opacity",
    "bar_bottom_shade_opacity",
}
_EFFECT_FIELDS = {
    "bar_outer_glow_enabled",
    "bar_glow_color",
    "bar_glow_opacity",
    "bar_glow_blur",
    "bar_inner_glow_opacity",
    "bar_shine_enabled",
    "bar_shine_position",
    "bar_shine_width",
    "bar_shine_opacity",
}
_TRACK_FIELDS = {
    "bar_track_enabled",
    "bar_track_color",
    "bar_track_opacity",
}


def visible_bar_style_fields(settings):
    settings = normalize_bar_style(settings)
    descriptors = []

    for field in DEFAULT_BAR_STYLE:
        if field in {"bar_shape", "bar_appearance_mode", "bar_texture_custom_image"}:
            continue

        group = _bar_style_group(field)
        if not _bar_style_field_visible(field, group, settings):
            continue

        descriptor = {
            "field": field,
            "label": _bar_style_label(field),
            "group": group,
            "value": settings[field],
        }
        if field in _ENUM_FIELDS:
            descriptor.update(type="enum", options=list(_ENUM_FIELDS[field]))
        elif field in _BOOLEAN_FIELDS:
            descriptor["type"] = "boolean"
        elif field in _COLOR_FIELDS:
            descriptor["type"] = "color"
        else:
            minimum, maximum = (
                _FLOAT_BOUNDS.get(field)
                or _INTEGER_BOUNDS[field]
            )
            descriptor.update(
                type="range",
                minimum=minimum,
                maximum=maximum,
                step=_range_step(field, minimum, maximum),
            )
        descriptors.append(descriptor)

    return descriptors


def _bar_style_group(field):
    if field in _SIMPLE_FIELDS:
        return "Simple"
    if field in _FRAME_FIELDS:
        return "Frame"
    if field in _FILL_FIELDS:
        return "Fill"
    if field in _TEXTURE_FIELDS:
        return "Texture"
    if field in _DEPTH_FIELDS:
        return "Depth"
    if field in _EFFECT_FIELDS:
        return "Effects"
    if field in _TRACK_FIELDS:
        return "Track"
    return "Content"


def _bar_style_field_visible(field, group, settings):
    advanced = settings["bar_appearance_mode"] == "advanced"
    if group == "Simple":
        return not advanced and (
            field != "bar_gradient_lighten"
            or settings["bar_gradient_enabled"]
        )
    if group == "Frame":
        if field in {"bar_border_color", "bar_border_width"}:
            return settings["bar_border_enabled"]
        if field.startswith("bar_shadow_") and field != "bar_shadow_enabled":
            return settings["bar_shadow_enabled"]
        return True
    if not advanced:
        return False

    fill_type = settings["bar_fill_type"]
    if field in {
        "bar_gradient_direction",
        "bar_gradient_color_count",
        "bar_highlight_position",
    }:
        return fill_type == "gradient"
    if field in {"bar_fill_color_center", "bar_fill_color_end"}:
        return fill_type == "gradient" and not settings["bar_fill_use_category_color"]
    if field == "bar_fill_color_start":
        return not settings["bar_fill_use_category_color"]

    texture_active = settings["bar_texture_enabled"] or fill_type == "texture"
    if group == "Texture" and field != "bar_texture_enabled":
        return texture_active
    if field in {"bar_bevel_size", "bar_bevel_highlight_opacity"}:
        return settings["bar_bevel_enabled"]
    if field == "bar_inner_shadow_size":
        return settings["bar_inner_shadow_opacity"] > 0
    if field in {"bar_glow_color", "bar_glow_opacity", "bar_glow_blur"}:
        return settings["bar_outer_glow_enabled"]
    if field in {"bar_shine_position", "bar_shine_width", "bar_shine_opacity"}:
        return settings["bar_shine_enabled"]
    if field in {"bar_track_color", "bar_track_opacity"}:
        return settings["bar_track_enabled"]
    if field in {"bar_logo_border_color", "bar_logo_border_width"}:
        return settings["bar_logo_border_enabled"]
    if field in {"bar_logo_background_color", "bar_logo_background_opacity"}:
        return settings["bar_logo_background_enabled"]
    if field.startswith("bar_secondary_logo_") and field != "bar_secondary_logo_enabled":
        if not settings["bar_secondary_logo_enabled"]:
            return False
        if field == "bar_secondary_logo_badge_corner":
            return settings["bar_secondary_logo_layout"] == "badge"
        if field == "bar_secondary_logo_position":
            return settings["bar_secondary_logo_layout"] == "independent"
        if field == "bar_secondary_logo_gap":
            return settings["bar_secondary_logo_layout"] == "side_by_side"
        if field in {
            "bar_secondary_logo_border_color",
            "bar_secondary_logo_border_width",
        }:
            return settings["bar_secondary_logo_border_enabled"]
        if field in {
            "bar_secondary_logo_background_color",
            "bar_secondary_logo_background_opacity",
        }:
            return settings["bar_secondary_logo_background_enabled"]
    if field.startswith("bar_logo_") and field != "bar_logo_position":
        if settings["bar_logo_position"] == "hidden":
            return False
    if field in {"bar_value_border_color", "bar_value_border_width"}:
        return settings["bar_value_border_enabled"]
    if field.startswith("bar_value_shadow_") and field != "bar_value_shadow_enabled":
        return settings["bar_value_shadow_enabled"]
    if field == "bar_value_color":
        return not settings["bar_value_use_theme_color"]
    return True


def _bar_style_label(field):
    return field.removeprefix("bar_").replace("_", " ").title()


def _range_step(field, minimum, maximum):
    if field in _INTEGER_BOUNDS:
        return 1
    span = maximum - minimum
    return 0.01 if span <= 1 else 0.1 if span <= 10 else 1

_COMPONENT_HTML = """
<div data-component="bar-style-editor"></div>
"""
_COMPONENT_CSS = component_source("bar_style_editor", "component.css")
_COMPONENT_JS = component_source("bar_style_editor", "component.js")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def bar_style_editor(*, settings, bar_colors, background_color, key=None):
    normalized = normalize_bar_style(settings)
    current_settings = normalize_bar_style(
        component_state_value(key, "settings", normalized),
        fallback=normalized,
    )
    if not component_v2_runtime_available():
        return current_settings

    component = component_renderer(
        "bar_style_editor_v2",
        html=_COMPONENT_HTML,
        css=_COMPONENT_CSS,
        js=_COMPONENT_JS,
    )
    component(
        data={
            "settings": current_settings,
            "fields": visible_bar_style_fields(current_settings),
            "bar_colors": list(bar_colors[:3]),
            "background_color": background_color,
            "custom_texture_data": _custom_texture_data(current_settings),
        },
        key=key,
        height="content",
    )
    return current_settings


def _custom_texture_data(settings):
    if settings.get("bar_texture_preset") != "custom_image":
        return None

    path_value = settings.get("bar_texture_custom_image")

    if not path_value:
        return None

    path = Path(path_value)

    try:
        with Image.open(path) as image:
            preview = ImageOps.fit(
                image.convert("RGB"),
                (256, 64),
                method=Image.Resampling.BILINEAR,
            )
            buffer = BytesIO()
            preview.save(buffer, format="PNG", optimize=True)
    except (OSError, ValueError):
        return None

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def normalize_bar_style(settings, fallback=None):
    fallback_values = dict(DEFAULT_BAR_STYLE)

    if isinstance(fallback, dict):
        fallback_values.update(fallback)

    legacy_logo_positions = {
        "outside": "outside_left",
        "inside": "inside_left",
    }
    fallback_values["bar_logo_position"] = legacy_logo_positions.get(
        fallback_values.get("bar_logo_position"),
        fallback_values.get("bar_logo_position"),
    )

    values = dict(fallback_values)

    if isinstance(settings, dict):
        values.update(settings)

    values["bar_logo_position"] = legacy_logo_positions.get(
        values.get("bar_logo_position"),
        values.get("bar_logo_position"),
    )

    normalized = {}

    for field, options in _ENUM_FIELDS.items():
        value = values.get(field)
        normalized[field] = (
            value if value in options else fallback_values[field]
        )

    for field in _BOOLEAN_FIELDS:
        normalized[field] = bool(values.get(field))

    for field in _COLOR_FIELDS:
        normalized[field] = _color(
            values.get(field),
            fallback_values[field],
        )

    for field, (minimum, maximum) in _FLOAT_BOUNDS.items():
        normalized[field] = _bounded_float(
            values.get(field),
            fallback_values[field],
            minimum,
            maximum,
        )

    for field, (minimum, maximum) in _INTEGER_BOUNDS.items():
        normalized[field] = _bounded_int(
            values.get(field),
            fallback_values[field],
            minimum,
            maximum,
        )

    custom_image = values.get("bar_texture_custom_image")
    normalized["bar_texture_custom_image"] = (
        custom_image.strip()
        if isinstance(custom_image, str) and custom_image.strip()
        else None
    )
    return normalized


def _bounded_float(value, fallback, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(fallback)

    return min(maximum, max(minimum, parsed))


def _bounded_int(value, fallback, minimum, maximum):
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        parsed = int(fallback)

    return min(maximum, max(minimum, parsed))


def _color(value, fallback):
    if isinstance(value, str) and _HEX_COLOR.fullmatch(value):
        return value.upper()

    return str(fallback).upper()
