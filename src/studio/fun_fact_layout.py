from dataclasses import replace

from core.display_calendar import flip_calendar_dimensions


DEFAULT_FUN_FACT_PANEL_WIDTH_RATIO = 0.28
DEFAULT_FLOATING_CARD_WIDTH_RATIO = 0.46
DEFAULT_FLOATING_CARD_HEIGHT_RATIO = 0.34


class FunFactLayoutError(ValueError):
    pass


def clamp_editorial_rect(
    left,
    top,
    width,
    height,
    canvas_width,
    canvas_height,
    *,
    min_width=240,
    min_height=140,
):
    """Clamp an editor rectangle to the canvas using final-canvas pixels."""
    canvas_width = max(1, int(round(canvas_width)))
    canvas_height = max(1, int(round(canvas_height)))
    minimum_width = min(canvas_width, max(1, int(round(min_width))))
    minimum_height = min(canvas_height, max(1, int(round(min_height))))
    width = min(canvas_width, max(minimum_width, int(round(width))))
    height = min(canvas_height, max(minimum_height, int(round(height))))
    left = min(canvas_width - width, max(0, int(round(left))))
    top = min(canvas_height - height, max(0, int(round(top))))
    return left, top, width, height


def resolved_panel_width(chart_config, fun_fact_config):
    width = fun_fact_config.panel_width
    if width is None:
        width = round(chart_config.width * DEFAULT_FUN_FACT_PANEL_WIDTH_RATIO)
    return int(width)


def panel_geometry(chart_config, fun_fact_config):
    validate_fun_fact_layout(chart_config, fun_fact_config)
    if fun_fact_config.layout == "editorial_floating":
        left, _, width, height = editorial_geometry(chart_config, fun_fact_config)
        return left, left + width, width
    width = resolved_panel_width(chart_config, fun_fact_config)
    right = chart_config.width - fun_fact_config.panel_margin
    left = right - width
    return left, right, width


def editorial_geometry(chart_config, fun_fact_config):
    """Return the active editorial rectangle as left, top, width, height."""
    if fun_fact_config.layout != "editorial_floating":
        width = resolved_panel_width(chart_config, fun_fact_config)
        left = chart_config.width - fun_fact_config.panel_margin - width
        top = fun_fact_config.panel_margin
        height = chart_config.height - (fun_fact_config.panel_margin * 2)
        return int(left), int(top), int(width), max(1, int(height))

    width = fun_fact_config.editorial_card_width
    if width is None:
        width = max(
            240,
            round(chart_config.width * DEFAULT_FLOATING_CARD_WIDTH_RATIO),
        )
    height = fun_fact_config.editorial_card_height
    if height is None:
        height = max(
            140,
            round(chart_config.height * DEFAULT_FLOATING_CARD_HEIGHT_RATIO),
        )
    left = fun_fact_config.editorial_card_x
    if left is None:
        left = round(chart_config.width * 0.50)
    top = fun_fact_config.editorial_card_y
    if top is None:
        top = round(chart_config.height * 0.54)
    left, top = resolved_editorial_position(
        chart_config,
        fun_fact_config,
        width,
        height,
        manual_left=left,
        manual_top=top,
    )
    return int(left), int(top), int(width), int(height)


def editorial_safe_area(chart_config, fun_fact_config):
    """Return deterministic final-canvas bounds used by card placement."""
    inset = max(0, int(fun_fact_config.panel_margin))
    return (
        inset,
        inset,
        max(inset, int(chart_config.width) - inset),
        max(inset, int(chart_config.height) - inset),
    )


def resolved_editorial_position(
    chart_config,
    fun_fact_config,
    width,
    height,
    *,
    manual_left,
    manual_top,
):
    """Resolve Manual or a stable nine-point placement in canvas pixels."""
    left_edge, top_edge, right_edge, bottom_edge = editorial_safe_area(
        chart_config,
        fun_fact_config,
    )
    mode = fun_fact_config.editorial_placement_mode
    horizontal = {
        "top_left": left_edge,
        "middle_left": left_edge,
        "bottom_left": left_edge,
        "top_center": left_edge + ((right_edge - left_edge - width) / 2),
        "center": left_edge + ((right_edge - left_edge - width) / 2),
        "bottom_center": left_edge + ((right_edge - left_edge - width) / 2),
        "top_right": right_edge - width,
        "middle_right": right_edge - width,
        "bottom_right": right_edge - width,
    }
    vertical = {
        "top_left": top_edge,
        "top_center": top_edge,
        "top_right": top_edge,
        "middle_left": top_edge + ((bottom_edge - top_edge - height) / 2),
        "center": top_edge + ((bottom_edge - top_edge - height) / 2),
        "middle_right": top_edge + ((bottom_edge - top_edge - height) / 2),
        "bottom_left": bottom_edge - height,
        "bottom_center": bottom_edge - height,
        "bottom_right": bottom_edge - height,
    }
    left = horizontal.get(mode, manual_left)
    top = vertical.get(mode, manual_top)
    if fun_fact_config.editorial_keep_inside_safe_area:
        max_left = max(left_edge, right_edge - width)
        max_top = max(top_edge, bottom_edge - height)
        left = min(max_left, max(left_edge, left))
        top = min(max_top, max(top_edge, top))
    return int(round(left)), int(round(top))


def apply_fun_fact_layout(chart_config, fun_fact_config):
    if not fun_fact_config.enabled:
        return chart_config

    validate_fun_fact_layout(chart_config, fun_fact_config)
    if fun_fact_config.editorial_layout_mode == "overlay":
        return chart_config
    if fun_fact_config.layout == "editorial_floating":
        if not fun_fact_config.editorial_reposition_time_label:
            return chart_config
        left, top, width, _ = editorial_geometry(chart_config, fun_fact_config)
        time_label_x = min(
            chart_config.width,
            left + width - fun_fact_config.panel_padding,
        )
        date_half_height = _date_half_height(chart_config)
        if top > date_half_height + fun_fact_config.panel_padding:
            time_label_y = top - fun_fact_config.panel_padding - date_half_height
        else:
            time_label_y = chart_config.time_label_y
        return replace(
            chart_config,
            time_label_x=time_label_x,
            time_label_y=time_label_y,
        )

    left, _, width = panel_geometry(chart_config, fun_fact_config)
    data_right = left - fun_fact_config.panel_margin
    right_margin = max(chart_config.right_margin, chart_config.width - data_right)
    title_x = chart_config.left_margin if chart_config.title_x is None else chart_config.title_x
    subtitle_x = (
        chart_config.left_margin
        if chart_config.subtitle_x is None
        else chart_config.subtitle_x
    )
    title_max = _limited_width(chart_config.title_max_width, data_right - title_x)
    subtitle_max = _limited_width(
        chart_config.subtitle_max_width,
        data_right - subtitle_x,
    )
    source_max = _limited_width(
        chart_config.source_max_width,
        data_right - chart_config.source_x,
    )
    time_label_x = min(chart_config.time_label_x, data_right)
    time_label_y = chart_config.time_label_y
    if fun_fact_config.layout == "editorial_right" and fun_fact_config.editorial_reposition_time_label:
        time_label_x = chart_config.width - fun_fact_config.panel_margin - fun_fact_config.panel_padding
        time_label_y = (
            fun_fact_config.panel_margin
            + fun_fact_config.panel_padding
            + _date_half_height(chart_config)
        )
    value_label_edge_padding = max(
        chart_config.value_label_edge_padding,
        chart_config.width - data_right,
    )
    return replace(
        chart_config,
        right_margin=right_margin,
        title_max_width=title_max,
        subtitle_max_width=subtitle_max,
        source_max_width=source_max,
        time_label_x=time_label_x,
        time_label_y=time_label_y,
        value_label_edge_padding=value_label_edge_padding,
    )


def _date_half_height(chart_config):
    if chart_config.date_style == "flip_calendar":
        _, height = flip_calendar_dimensions(chart_config.flip_calendar_scale)
        return height / 2.0
    return chart_config.time_label_font_size * chart_config.dpi / 144.0


def validate_fun_fact_layout(chart_config, fun_fact_config):
    if fun_fact_config.layout not in (
        "right_panel",
        "editorial_right",
        "editorial_floating",
    ):
        raise FunFactLayoutError(
            "fun_facts.layout must be 'right_panel', 'editorial_right', "
            "or 'editorial_floating'."
        )
    margin = fun_fact_config.panel_margin
    padding = fun_fact_config.panel_padding
    if fun_fact_config.editorial_orientation not in ("vertical", "horizontal"):
        raise FunFactLayoutError(
            "fun_facts.editorial_orientation must be 'vertical' or 'horizontal'."
        )
    if fun_fact_config.editorial_layout_mode not in ("reserved", "overlay"):
        raise FunFactLayoutError(
            "fun_facts.editorial_layout_mode must be 'reserved' or 'overlay'."
        )
    if fun_fact_config.editorial_headline_alignment not in (
        "left", "center", "right", "justify",
    ) or fun_fact_config.editorial_body_alignment not in (
        "left", "center", "right", "justify",
    ):
        raise FunFactLayoutError("Editorial text alignment is invalid.")
    if fun_fact_config.editorial_placement_mode not in (
        "manual", "top_left", "top_center", "top_right",
        "middle_left", "center", "middle_right", "bottom_left",
        "bottom_center", "bottom_right", "smart",
    ):
        raise FunFactLayoutError("Editorial placement mode is invalid.")
    if fun_fact_config.editorial_background_texture not in (
        "none", "grain", "paper", "dots", "diagonal",
    ):
        raise FunFactLayoutError(
            "fun_facts.editorial_background_texture is invalid."
        )
    for field in (
        "editorial_background_texture_intensity",
        "editorial_headline_opacity",
        "editorial_body_opacity",
        "editorial_credit_opacity",
    ):
        value = getattr(fun_fact_config, field)
        if not 0 <= value <= 1:
            raise FunFactLayoutError(f"fun_facts.{field} must be from 0 to 1.")
    if fun_fact_config.editorial_image_position not in ("left", "right"):
        raise FunFactLayoutError(
            "fun_facts.editorial_image_position must be 'left' or 'right'."
        )
    if fun_fact_config.editorial_collision_gap < 0:
        raise FunFactLayoutError(
            "fun_facts.editorial_collision_gap must be >= 0."
        )
    if margin < 0:
        raise FunFactLayoutError("fun_facts.panel_margin must be >= 0.")
    if padding < 8:
        raise FunFactLayoutError("fun_facts.panel_padding must be at least 8 pixels.")
    if fun_fact_config.layout == "editorial_floating":
        left, top, width, height = editorial_geometry(chart_config, fun_fact_config)
        if width < 240 or height < 140:
            raise FunFactLayoutError(
                "A floating editorial card must be at least 240 x 140 pixels."
            )
        if left < 0 or top < 0 or left + width > chart_config.width or top + height > chart_config.height:
            raise FunFactLayoutError(
                "The floating editorial card must remain inside the canvas."
            )
        if (
            fun_fact_config.editorial_layout_mode == "reserved"
            and left - fun_fact_config.editorial_collision_gap - chart_config.left_margin < 80
        ):
            raise FunFactLayoutError(
                "The floating editorial card leaves no useful bar space on intersecting rows."
            )
    else:
        width = resolved_panel_width(chart_config, fun_fact_config)
        height = chart_config.height - (margin * 2)
        if width < 160:
            raise FunFactLayoutError(
                "fun_facts.panel_width must be at least 160 pixels."
            )
    if padding * 2 >= width:
        raise FunFactLayoutError(
            "fun_facts.panel_padding leaves no usable panel content width."
        )
    if fun_fact_config.layout != "editorial_floating" and margin * 2 >= chart_config.height:
        raise FunFactLayoutError(
            "fun_facts.panel_margin leaves no usable panel height."
        )
    if padding * 2 >= height:
        raise FunFactLayoutError(
            "fun_facts.panel_padding leaves no usable vertical panel content."
        )
    if fun_fact_config.layout == "editorial_floating":
        return
    data_width = chart_config.width - chart_config.left_margin - width - (margin * 2)
    if data_width < 160:
        raise FunFactLayoutError(
            "fun_facts.panel_width is too large for the selected canvas and bar start."
        )


def _limited_width(configured, available):
    available = max(1, int(available))
    if configured is None:
        return available
    return min(int(configured), available)
