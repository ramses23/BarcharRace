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
