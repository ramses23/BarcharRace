from dataclasses import replace
from math import ceil, floor, isclose, isfinite, log10

from models.value_axis import ValueAxisState, ValueAxisTick, ValueScale
from utils.text_fit import measure_text_width, measurement_font
from utils.value_formatter import format_adaptive_compact_value, format_value


VALUE_AXIS_HEADROOM = 1.12
VALUE_AXIS_EXPANSION_SMOOTHING = 0.22
VALUE_AXIS_CONTRACTION_SMOOTHING = 0.045
VALUE_AXIS_TICK_FADE_IN = 0.22
VALUE_AXIS_TICK_FADE_OUT = 0.16
MIN_AXIS_DOMAIN = 1e-9
NICE_TICK_FAMILY = (1.0, 2.0, 2.5, 5.0, 10.0)


def nice_tick_step(domain_max, target_tick_count=5):
    domain = _positive_finite(domain_max, default=1.0)
    count = max(1, int(target_tick_count))
    raw_step = domain / count
    exponent = floor(log10(raw_step))
    magnitude = 10.0 ** exponent
    fraction = raw_step / magnitude
    nice_fraction = min(
        NICE_TICK_FAMILY,
        key=lambda candidate: abs(candidate - fraction),
    )
    return nice_fraction * magnitude


def nice_axis_max(value, target_tick_count=5):
    value = _positive_finite(value, default=1.0)
    step = nice_tick_step(value, target_tick_count)
    return max(step, ceil(value / step) * step)


def nice_ticks(domain_max, target_tick_count=5):
    domain = _positive_finite(domain_max, default=1.0)
    step = nice_tick_step(domain, target_tick_count)
    last_index = max(1, floor((domain + (step * 1e-9)) / step))
    return step, tuple(
        _stable_tick_value(index * step)
        for index in range(last_index + 1)
    )


def adaptive_tick_count(
    axis_width,
    requested_count,
    tick_font_size,
    *,
    domain_max,
    value_format,
    font_family,
    dpi,
    font_weight="normal",
    font_style="normal",
    tick_value_format="same",
):
    width = max(1.0, _finite(axis_width, default=1.0))
    requested = max(2, min(12, int(requested_count)))
    domain = _positive_finite(domain_max, default=1.0)
    font = measurement_font(
        tick_font_size,
        dpi,
        font_family,
        font_weight,
        font_style,
    )
    minimum_gap = max(
        8.0,
        float(tick_font_size) * float(dpi) / 144.0,
    )

    for candidate in range(requested, 0, -1):
        step, ticks = nice_ticks(domain, candidate)
        labeled = [
            (
                (value / domain) * width,
                measure_text_width(
                    format_axis_tick(
                        value, step, value_format, tick_value_format
                    ),
                    font,
                ),
            )
            for value in ticks
            if value > 0.0
        ]
        if len(labeled) <= requested and all(
            (current_x - (current_width / 2.0))
            - (previous_x + (previous_width / 2.0))
            >= minimum_gap
            for (previous_x, previous_width), (current_x, current_width)
            in zip(labeled, labeled[1:])
        ):
            return candidate

    return 1


def value_axis_extent(sprite_sets, *, fallback_width):
    static_max = 0.0
    for sprites in sprite_sets:
        visible = [
            sprite
            for sprite in sprites
            if _visible_positive_value(sprite) is not None
        ]
        if not visible:
            continue
        static_max = max(
            static_max,
            max(float(sprite.value) for sprite in visible),
        )
    return max(0.0, float(fallback_width)), static_max


def current_value_axis_width(sprites, *, fallback_width):
    widths = [
        max(0.0, float(sprite.width))
        for sprite in sprites
        if _visible_positive_value(sprite) is not None
    ]
    return max(widths) if widths else max(0.0, float(fallback_width))


def scale_bar_sprites(sprites, scale):
    return [
        replace(
            sprite,
            x=scale.origin_x,
            width=scale.width_for_value(sprite.value),
        )
        for sprite in sprites
    ]


class ValueAxisTracker:
    def __init__(
        self,
        *,
        mode,
        origin_x,
        axis_width,
        static_max_value,
        target_tick_count,
        tick_font_size,
        value_format,
        chart_config,
        headroom=VALUE_AXIS_HEADROOM,
        expansion_smoothing=VALUE_AXIS_EXPANSION_SMOOTHING,
        contraction_smoothing=VALUE_AXIS_CONTRACTION_SMOOTHING,
    ):
        self.mode = mode if mode in ("static", "dynamic") else "dynamic"
        self.origin_x = float(origin_x)
        self.axis_width = max(0.0, float(axis_width))
        self.target_tick_count = max(2, min(12, int(target_tick_count)))
        self.tick_font_size = max(1, int(tick_font_size))
        self.value_format = value_format
        self.tick_value_format = (
            chart_config.value_grid_tick_value_format
            if chart_config.value_grid_tick_value_format
            in ("same", "full", "compact")
            else "same"
        )
        self.chart_config = chart_config
        self.headroom = max(1.0, float(headroom))
        self.expansion_smoothing = _unit_interval(
            expansion_smoothing,
            default=VALUE_AXIS_EXPANSION_SMOOTHING,
        )
        self.contraction_smoothing = _unit_interval(
            contraction_smoothing,
            default=VALUE_AXIS_CONTRACTION_SMOOTHING,
        )
        self.static_domain = nice_axis_max(
            max(MIN_AXIS_DOMAIN, float(static_max_value)) * self.headroom,
            self.target_tick_count,
        )
        self.domain = None
        self._effective_scale = None
        self._previous_visible_max = None
        self._tick_opacities = {}
        self._started = False

    @classmethod
    def from_config(cls, config, sprite_sets):
        axis_width, static_max = value_axis_extent(
            sprite_sets,
            fallback_width=config.max_bar_width,
        )
        return cls(
            mode=config.value_grid_mode,
            origin_x=config.left_margin,
            axis_width=axis_width,
            static_max_value=static_max,
            target_tick_count=config.value_grid_target_tick_count,
            tick_font_size=config.value_grid_tick_font_size,
            value_format=config.value_format,
            chart_config=config,
        )

    def next(self, sprites):
        self.axis_width = current_value_axis_width(
            sprites,
            fallback_width=self.axis_width,
        )
        visible_max = max(
            (
                value
                for sprite in sprites
                if (value := _visible_positive_value(sprite)) is not None
            ),
            default=0.0,
        )
        target_domain = (
            self.static_domain
            if self.mode == "static"
            else nice_axis_max(
                max(MIN_AXIS_DOMAIN, visible_max) * self.headroom,
                self.target_tick_count,
            )
        )
        if self.domain is None or self.mode == "static":
            self.domain = target_domain
        else:
            smoothing = (
                self.expansion_smoothing
                if target_domain > self.domain
                else self.contraction_smoothing
            )
            self.domain += (target_domain - self.domain) * smoothing
            self.domain = max(self.domain, visible_max * 1.015)

        domain = max(MIN_AXIS_DOMAIN, self.domain)
        desired_scale = self.axis_width / domain
        effective_axis_width = self.axis_width
        if self.mode == "dynamic":
            if self._effective_scale is None:
                self._effective_scale = desired_scale
            elif visible_max >= self._previous_visible_max:
                # Rising/equal maxima must not move persistent ticks right.
                self._effective_scale = min(
                    self._effective_scale,
                    desired_scale,
                )
            elif desired_scale > self._effective_scale:
                self._effective_scale += (
                    desired_scale - self._effective_scale
                ) * self.contraction_smoothing
            else:
                self._effective_scale = desired_scale
            effective_axis_width = min(
                self.axis_width,
                max(0.0, self._effective_scale * domain),
            )
        else:
            self._effective_scale = desired_scale
        self._previous_visible_max = visible_max

        scale = ValueScale(
            origin_x=self.origin_x,
            width=effective_axis_width,
            domain_max=domain,
        )
        effective_tick_count = adaptive_tick_count(
            scale.width,
            self.target_tick_count,
            self.tick_font_size,
            domain_max=scale.domain_max,
            value_format=self.value_format,
            font_family=(
                self.chart_config.value_font_family
                or self.chart_config.font_family
            ),
            dpi=self.chart_config.dpi,
            font_weight=self.chart_config.value_grid_tick_font_weight,
            font_style=self.chart_config.value_grid_tick_font_style,
            tick_value_format=self.tick_value_format,
        )
        tick_step, desired_ticks = nice_ticks(
            scale.domain_max,
            effective_tick_count,
        )
        self._update_tick_opacities(desired_ticks)
        line_top, line_bottom, label_y = _vertical_geometry(
            self.chart_config,
            sprites,
        )
        ticks = tuple(
            ValueAxisTick(
                value=value,
                x=scale.x_for_value(value),
                label=(
                    ""
                    if value == 0.0
                    else format_axis_tick(
                        value,
                        tick_step,
                        self.value_format,
                        self.tick_value_format,
                    )
                ),
                opacity=opacity,
            )
            for value, opacity in sorted(self._tick_opacities.items())
            if opacity > 0.0 and value <= scale.domain_max + (tick_step * 1e-9)
        )
        self._started = True
        return ValueAxisState(
            scale=scale,
            ticks=ticks,
            tick_step=tick_step,
            line_top=line_top,
            line_bottom=line_bottom,
            label_y=label_y,
        )

    def _update_tick_opacities(self, desired_ticks):
        desired = set(desired_ticks)
        if not self._started:
            self._tick_opacities = {value: 1.0 for value in desired}
            return

        updated = {}
        for value in set(self._tick_opacities) | desired:
            opacity = self._tick_opacities.get(value, 0.0)
            if value in desired:
                opacity = min(1.0, opacity + VALUE_AXIS_TICK_FADE_IN)
            else:
                opacity = max(0.0, opacity - VALUE_AXIS_TICK_FADE_OUT)
            if opacity > 0.0:
                updated[value] = opacity
        self._tick_opacities = updated


def format_axis_tick(value, tick_step, value_format, tick_value_format="same"):
    decimal_places = _tick_decimal_places(
        tick_step * float(value_format.multiplier)
    )
    if tick_value_format == "compact":
        return format_adaptive_compact_value(value, value_format)
    if tick_value_format == "full":
        value_format = replace(value_format, compact=False)
    return format_value(
        value,
        replace(value_format, decimal_places=decimal_places),
    )


def _tick_decimal_places(scaled_step):
    step = abs(_finite(scaled_step, default=1.0))
    if step <= 0.0:
        return 0
    for places in range(7):
        if isclose(step, round(step, places), rel_tol=1e-9, abs_tol=1e-9):
            return places
    return 6


def _vertical_geometry(config, sprites):
    row_top = min(
        (sprite.y - (sprite.height / 2.0) for sprite in sprites),
        default=float(config.top_margin),
    )
    row_bottom = max(
        (sprite.y + (sprite.height / 2.0) for sprite in sprites),
        default=float(config.height - config.bottom_margin),
    )
    font_pixels = max(
        1.0,
        float(config.value_grid_tick_font_size) * float(config.dpi) / 72.0,
    )
    label_y = row_top - (font_pixels / 2.0) - 6.0
    return row_top, row_bottom, label_y


def _visible_positive_value(sprite):
    value = _finite(getattr(sprite, "value", None), default=None)
    opacity = _finite(getattr(sprite, "opacity", 1.0), default=0.0)
    if value is None or value <= 0.0 or opacity <= 0.0:
        return None
    return value


def _stable_tick_value(value):
    return round(float(value), 12)


def _positive_finite(value, *, default):
    value = _finite(value, default=default)
    return value if value > 0.0 else default


def _finite(value, *, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if isfinite(value) else default


def _unit_interval(value, *, default):
    value = _finite(value, default=default)
    return max(0.0, min(1.0, value))
