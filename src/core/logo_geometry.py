from dataclasses import replace
from math import isfinite

from core.rank_motion import visual_rank_motion_sprite


_INSIDE_PRIMARY_LOGO_POSITIONS = frozenset(("inside_left", "inside_right"))


def normalized_primary_logo_position(position):
    return {
        "outside": "outside_left",
        "inside": "inside_left",
    }.get(position, position)


def primary_logo_is_inside(config, sprite):
    return bool(
        config.logos_enabled
        and getattr(sprite, "logo_path", None)
        and normalized_primary_logo_position(config.bar_logo_position)
        in _INSIDE_PRIMARY_LOGO_POSITIONS
    )


def resolved_primary_logo_size(config, sprite, requested_size):
    """Resolve primary-logo outer size from bar height, never bar width."""
    bar_height = max(0.0, float(sprite.height))
    logo_size_percent = max(0.0, min(100.0, float(requested_size)))
    size_from_slider = bar_height * logo_size_percent / 100.0
    configured_minimum = max(0.0, float(config.primary_logo_min_size))
    size = min(
        bar_height,
        max(size_from_slider, configured_minimum),
        float(config.width),
        float(config.height),
    )
    if normalized_primary_logo_position(
        config.bar_logo_position
    ) in _INSIDE_PRIMARY_LOGO_POSITIONS:
        size = min(size, _primary_logo_containment_width(config, sprite))
    return size


def final_visual_bar_sprite(
    config,
    sprite,
    *,
    primary_logo_available=False,
):
    """Return render-only bar geometry after rank emphasis and logo floor."""
    visual = visual_rank_motion_sprite(sprite)
    if not primary_logo_is_inside(config, visual):
        return visual

    logo_width = resolved_primary_logo_size(
        config,
        visual,
        config.logo_size,
    )
    if callable(primary_logo_available):
        primary_logo_available = primary_logo_available(visual, logo_width)
    if not primary_logo_available or logo_width <= 0.0:
        return visual

    return replace(
        visual,
        width=max(0.0, float(visual.width), logo_width),
    )


def primary_logo_horizontal_bounds(sprite, position, size):
    """Return primary outer-badge bounds without crossing the bar origin."""
    position = normalized_primary_logo_position(position)
    size = max(0.0, float(size))
    bar_start = float(sprite.x)
    available_width = max(0.0, float(sprite.width))

    if position == "inside_right" and size < available_width:
        right = bar_start + available_width
        return right - size, right

    return bar_start, bar_start + size


def _primary_logo_containment_width(config, sprite):
    structural_width = getattr(sprite, "bar_available_width", None)
    try:
        structural_width = float(structural_width)
    except (TypeError, ValueError):
        structural_width = None
    if structural_width is None or not isfinite(structural_width):
        canvas_width = max(0.0, float(config.width) - float(sprite.x))
        configured_width = max(0.0, float(config.max_bar_width))
        structural_width = (
            min(configured_width, canvas_width)
            if configured_width > 0.0
            else canvas_width
        )
    return max(0.0, structural_width)
