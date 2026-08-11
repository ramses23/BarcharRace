from dataclasses import replace


DEFAULT_FUN_FACT_PANEL_WIDTH_RATIO = 0.28


class FunFactLayoutError(ValueError):
    pass


def resolved_panel_width(chart_config, fun_fact_config):
    width = fun_fact_config.panel_width
    if width is None:
        width = round(chart_config.width * DEFAULT_FUN_FACT_PANEL_WIDTH_RATIO)
    return int(width)


def panel_geometry(chart_config, fun_fact_config):
    validate_fun_fact_layout(chart_config, fun_fact_config)
    width = resolved_panel_width(chart_config, fun_fact_config)
    right = chart_config.width - fun_fact_config.panel_margin
    left = right - width
    return left, right, width


def apply_fun_fact_layout(chart_config, fun_fact_config):
    if not fun_fact_config.enabled:
        return chart_config

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
            + (chart_config.time_label_font_size * chart_config.dpi / 144.0)
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


def validate_fun_fact_layout(chart_config, fun_fact_config):
    if fun_fact_config.layout not in ("right_panel", "editorial_right"):
        raise FunFactLayoutError(
            "fun_facts.layout must be 'right_panel' or 'editorial_right'."
        )
    width = resolved_panel_width(chart_config, fun_fact_config)
    margin = fun_fact_config.panel_margin
    padding = fun_fact_config.panel_padding
    if width < 160:
        raise FunFactLayoutError("fun_facts.panel_width must be at least 160 pixels.")
    if margin < 0:
        raise FunFactLayoutError("fun_facts.panel_margin must be >= 0.")
    if padding < 8:
        raise FunFactLayoutError("fun_facts.panel_padding must be at least 8 pixels.")
    if padding * 2 >= width:
        raise FunFactLayoutError(
            "fun_facts.panel_padding leaves no usable panel content width."
        )
    if margin * 2 >= chart_config.height:
        raise FunFactLayoutError(
            "fun_facts.panel_margin leaves no usable panel height."
        )
    if padding * 2 >= chart_config.height - (margin * 2):
        raise FunFactLayoutError(
            "fun_facts.panel_padding leaves no usable vertical panel content."
        )
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
