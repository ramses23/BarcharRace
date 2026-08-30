def resolved_primary_logo_size(config, sprite, requested_size):
    """Resolve primary-logo outer size from bar height, never bar width."""
    bar_height = max(0.0, float(sprite.height))
    logo_size_percent = max(0.0, min(100.0, float(requested_size)))
    size_from_slider = bar_height * logo_size_percent / 100.0
    configured_minimum = max(0.0, float(config.primary_logo_min_size))
    return min(
        bar_height,
        max(size_from_slider, configured_minimum),
        float(config.width),
        float(config.height),
    )


def primary_logo_horizontal_bounds(sprite, position, size):
    """Return primary outer-badge bounds without crossing the bar origin."""
    position = {"inside": "inside_left"}.get(position, position)
    size = max(0.0, float(size))
    bar_start = float(sprite.x)
    available_width = max(0.0, float(sprite.width))

    if position == "inside_right" and size < available_width:
        right = bar_start + available_width
        return right - size, right

    return bar_start, bar_start + size
