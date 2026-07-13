import base64
import re
from io import BytesIO
from pathlib import Path

import streamlit.components.v1 as components
from PIL import Image, ImageOps


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
    "bar_value_border_width": (0.0, 8.0),
}
_INTEGER_BOUNDS = {
    "bar_gradient_color_count": (2, 3),
    "bar_shadow_offset_x": (-40, 40),
    "bar_shadow_offset_y": (-40, 40),
    "bar_value_shadow_offset_x": (-20, 20),
    "bar_value_shadow_offset_y": (-20, 20),
}

_COMPONENT_DIR = Path(__file__).resolve().parent / "components" / "bar_style_editor"
_bar_style_component = components.declare_component(
    "bar_style_editor",
    path=str(_COMPONENT_DIR),
)
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def bar_style_editor(*, settings, bar_colors, background_color, key=None):
    normalized = normalize_bar_style(settings)
    result = _bar_style_component(
        settings=normalized,
        bar_colors=list(bar_colors[:3]),
        background_color=background_color,
        custom_texture_data=_custom_texture_data(normalized),
        default=normalized,
        key=key,
    )
    return normalize_bar_style(result, fallback=normalized)


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
