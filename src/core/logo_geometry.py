def resolved_primary_logo_size(config, sprite, requested_size):
    """Return a primary-logo size that never depends on bar value width."""
    bar_height = max(1.0, float(sprite.height))
    requested = max(1.0, float(requested_size), bar_height)

    if config.bar_vertical_layout_mode == "fill_available":
        gap = bar_height * (
            max(0.0, float(config.bar_gap))
            / max(1.0, float(config.bar_height))
        )
    else:
        gap = max(0.0, float(config.bar_gap))

    natural_size = min(requested, bar_height + gap)
    configured_minimum = max(
        0.0, float(config.primary_logo_min_size)
    )
    return min(
        max(natural_size, configured_minimum),
        float(config.width),
        float(config.height),
    )
