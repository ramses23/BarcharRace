from dataclasses import dataclass
from functools import lru_cache
from math import ceil, floor

from core.bar_appearance import uses_configurable_bar_content
from utils.text_fit import (
    fit_text_to_width,
    formatted_value_bbox,
    measure_text_width,
    measurement_font,
)


@dataclass(frozen=True)
class ResolvedValueTextGeometry:
    text: str
    x: float
    y: float
    horizontal_alignment: str
    vertical_alignment: str
    color: str
    left: float
    top: float
    width: float
    height: float

    def layout_dict(self):
        return {
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "ha": self.horizontal_alignment,
            "va": self.vertical_alignment,
            "color": self.color,
        }

    def rect_dict(self):
        return {
            "x": round(float(self.left), 3),
            "y": round(float(self.top), 3),
            "width": round(float(self.width), 3),
            "height": round(float(self.height), 3),
        }


def resolve_value_text_geometry(
    config,
    sprite,
    value_text,
    *,
    inside_left_logo_extent=None,
    inside_right_logo_extent=None,
):
    """Resolve the rendered Value Text layout and its visual bounding box."""
    font = measurement_font(
        config.value_font_size,
        config.dpi,
        config.value_font_family or config.font_family,
        config.value_font_weight,
        config.value_font_style,
    )
    max_right = float(config.width - config.value_label_edge_padding)
    min_x = _value_label_min_x(config, max_right)
    max_width = max(0.0, max_right - min_x)
    text, text_width = _fit_value_text(value_text, max_width, font)
    outside_x = float(sprite.x + sprite.width + config.value_label_gap)
    if inside_right_logo_extent:
        outside_x = max(
            outside_x,
            float(inside_right_logo_extent[1]) + config.logo_label_gap,
        )

    configurable = uses_configurable_bar_content(config)
    color = _outside_color(config)
    x = outside_x
    y = float(sprite.y)
    ha = "left"
    va = "center"

    if configurable and config.bar_value_position == "inside":
        inside_x = float(sprite.x + sprite.width - config.value_label_gap)
        if inside_right_logo_extent:
            inside_x = min(
                inside_x,
                float(inside_right_logo_extent[0]) - config.logo_label_gap,
            )
        left_limit = float(sprite.x + config.value_label_inside_padding)
        if inside_left_logo_extent:
            left_limit = max(
                left_limit,
                float(inside_left_logo_extent[1]) + config.logo_label_gap,
            )
        if inside_x - text_width < left_limit:
            fits_outside = outside_x + text_width <= max_right
            x = outside_x if fits_outside else max_right
            ha = "left" if fits_outside else "right"
            color = _outside_color(config)
        else:
            x = inside_x
            ha = "right"
            color = _inside_color(config)
    elif configurable and config.bar_value_position == "above":
        x = min(max_right, float(sprite.x + sprite.width))
        y = float(sprite.y - (sprite.height / 2) - 7)
        ha = "right"
        va = "bottom"
    elif configurable and config.bar_value_position == "outside":
        available_width = max(0.0, max_right - outside_x)
        text, text_width = _fit_value_text(text, available_width, font)
        if config.bar_label_position in ("outside", "outside_right"):
            y += float(sprite.height) * 0.2
    elif outside_x + text_width <= max_right:
        if configurable and config.bar_label_position in (
            "outside", "outside_right"
        ):
            y += float(sprite.height) * 0.2
    else:
        inside_x = float(sprite.x + sprite.width - config.value_label_gap)
        if inside_right_logo_extent:
            inside_x = min(
                inside_x,
                float(inside_right_logo_extent[0]) - config.logo_label_gap,
            )
        required = text_width + (config.value_label_inside_padding * 2)
        if config.bar_shape != "lollipop" and sprite.width >= required:
            x = inside_x
            ha = "right"
            color = _inside_color(config)
        else:
            x = max_right
            ha = "right"

    left, top, right, bottom = _rendered_text_bbox(
        config,
        text,
        font,
        x=x,
        y=y,
        horizontal_alignment=ha,
        vertical_alignment=va,
    )
    return ResolvedValueTextGeometry(
        text=text,
        x=x,
        y=y,
        horizontal_alignment=ha,
        vertical_alignment=va,
        color=color,
        left=left,
        top=top,
        width=right - left,
        height=bottom - top,
    )


def _fit_value_text(text, max_width, font):
    text = str(text)
    if not text or max_width <= 0:
        return "", 0.0
    width = measure_text_width(text, font)
    if width <= max_width:
        return text, width
    fitted = fit_text_to_width(text, max_width=max_width, font=font)
    return (
        fitted,
        measure_text_width(fitted, font) if fitted else 0.0,
    )


def _value_label_min_x(config, max_right):
    if config.value_label_min_x is not None:
        return float(config.value_label_min_x)
    if config.left_margin < max_right:
        return float(config.left_margin)
    return float(config.label_min_x)


def _outside_color(config):
    if uses_configurable_bar_content(config) and not config.bar_value_use_theme_color:
        return config.bar_value_color
    return config.resolved_value_text_color


def _inside_color(config):
    if uses_configurable_bar_content(config) and not config.bar_value_use_theme_color:
        return config.bar_value_color
    if config.value_text_color is not None:
        return config.resolved_value_text_color
    return config.value_label_inside_color or config.background_color


def _rendered_text_bbox(
    config,
    text,
    font,
    *,
    x,
    y,
    horizontal_alignment,
    vertical_alignment,
):
    horizontal_anchor = {
        "left": "l", "center": "m", "right": "r",
    }.get(horizontal_alignment, "l")
    vertical_anchor = {
        "top": "t", "center": "m", "bottom": "b", "baseline": "s",
    }.get(vertical_alignment, "m")
    anchor = horizontal_anchor + vertical_anchor
    stroke_pixels = (
        max(0, int(round(
            float(config.bar_value_border_width) * (config.dpi / 72)
        )))
        if config.bar_value_border_enabled
        else 0
    )
    if not text:
        return float(round(x)), float(round(y)), float(round(x)), float(round(y))
    shadow_offset = None
    if config.bar_value_shadow_enabled:
        shadow_offset = (
            int(round(float(config.bar_value_shadow_offset_x) * (config.dpi / 72))),
            int(round(float(config.bar_value_shadow_offset_y) * (config.dpi / 72))),
        )
    left, top, right, bottom = _cached_rendered_text_extents(
        text,
        font,
        anchor,
        stroke_pixels,
        shadow_offset,
    )
    local_left = floor(left) - 1
    local_top = floor(top) - 1
    width = max(1, (ceil(right) + 1) - local_left)
    height = max(1, (ceil(bottom) + 1) - local_top)
    rendered_left = round(float(x) + local_left)
    rendered_top = round(float(y) + local_top)
    return (
        float(rendered_left),
        float(rendered_top),
        float(rendered_left + width),
        float(rendered_top + height),
    )


@lru_cache(maxsize=8192)
def _cached_rendered_text_extents(
    text,
    font,
    anchor,
    stroke_pixels,
    shadow_offset,
):
    left, top, right, bottom = formatted_value_bbox(
        text,
        font,
        anchor=anchor,
        stroke_width=stroke_pixels,
    )
    if shadow_offset is not None:
        shadow_left, shadow_top, shadow_right, shadow_bottom = formatted_value_bbox(
            text,
            font,
            anchor=anchor,
        )
        shadow = (
            shadow_left + shadow_offset[0],
            shadow_top + shadow_offset[1],
            shadow_right + shadow_offset[0],
            shadow_bottom + shadow_offset[1],
        )
        left = min(left, shadow[0])
        top = min(top, shadow[1])
        right = max(right, shadow[2])
        bottom = max(bottom, shadow[3])
    return left, top, right, bottom


def value_text_metric_cache_info():
    """Return bounded metric-cache counters for profiling diagnostics."""
    return _cached_rendered_text_extents.cache_info()


def clear_value_text_metric_cache():
    _cached_rendered_text_extents.cache_clear()
