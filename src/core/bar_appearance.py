"""Resolve the internal bar renderer without exposing backend modes in the UI."""


def uses_configurable_bar_content(config):
    """Return whether unified logo/label/value placement controls are active."""
    return config.bar_appearance_mode in ("advanced", "unified")


def uses_material_bar_renderer(config):
    """Select the material compositor only when the active style requires it."""
    mode = config.bar_appearance_mode
    if mode == "advanced":
        return True
    if mode != "unified":
        return False

    if config.bar_fill_type == "texture" or config.bar_texture_enabled:
        return True
    if config.bar_fill_type == "gradient":
        vector_gradient = (
            config.bar_gradient_direction == "horizontal"
            and config.bar_gradient_color_count == 2
            and config.bar_fill_use_category_color
            and config.bar_edge_darkening <= 0
        )
        if not vector_gradient:
            return True
    elif config.bar_fill_type == "solid":
        if not config.bar_fill_use_category_color:
            return True
    else:
        return True

    return any((
        config.bar_bevel_enabled,
        config.bar_inner_shadow_opacity > 0,
        config.bar_top_highlight_opacity > 0,
        config.bar_bottom_shade_opacity > 0,
        config.bar_outer_glow_enabled,
        config.bar_inner_glow_opacity > 0,
        config.bar_shine_enabled,
        config.bar_track_enabled,
    ))


def uses_vector_bar_gradient(config):
    if config.bar_appearance_mode == "simple":
        return config.bar_gradient_enabled
    return (
        config.bar_appearance_mode == "unified"
        and config.bar_fill_type == "gradient"
        and not uses_material_bar_renderer(config)
    )
