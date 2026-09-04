from dataclasses import dataclass, replace
from functools import lru_cache
from math import ceil, floor, isclose, isfinite, log10

from core.bar_value_scale import (
    progressive_bar_scale_active,
)
from core.layout_engine import structural_race_vertical_bounds
from models.value_axis import (
    GridDisplayScale,
    SemanticDataScale,
    ValueAxisState,
    ValueAxisTick,
)
from utils.text_fit import measure_text_width, measurement_font
from utils.value_formatter import format_adaptive_compact_value, format_value


VALUE_AXIS_HEADROOM = 1.12
VALUE_AXIS_EXPANSION_SMOOTHING = 0.22
VALUE_AXIS_CONTRACTION_SMOOTHING = 0.045
VALUE_AXIS_TICK_FADE_IN = 0.22
VALUE_AXIS_TICK_FADE_OUT = 0.16
MIN_AXIS_DOMAIN = 1e-9
NICE_TICK_FAMILY = (1.0, 2.0, 2.5, 5.0, 10.0)


@dataclass(frozen=True)
class ValueAxisTrackerSnapshot:
    """Minimal mutable state needed to resume an axis replay exactly."""

    axis_width: float
    domain: float | None
    effective_scale: float | None
    previous_visible_max: float | None
    tick_opacities: tuple[tuple[float, float], ...]
    last_tick_step: float | None
    started: bool


def nice_tick_step(domain_max, target_tick_count=5):
    domain = _positive_finite(domain_max, default=1.0)
    count = max(1, int(target_tick_count))
    raw_step = domain / count
    exponent = floor(log10(raw_step))
    magnitude = 10.0 ** exponent
    fraction = raw_step / magnitude
    # Midpoints preserve the exact nearest-family/tie-to-earlier behavior of
    # ``min(..., key=distance)`` without allocating a lambda five times for
    # every historical frame.
    if fraction <= 1.5:
        nice_fraction = 1.0
    elif fraction <= 2.25:
        nice_fraction = 2.0
    elif fraction <= 3.75:
        nice_fraction = 2.5
    elif fraction <= 7.5:
        nice_fraction = 5.0
    else:
        nice_fraction = 10.0
    return nice_fraction * magnitude


def nice_axis_max(value, target_tick_count=5):
    value = _positive_finite(value, default=1.0)
    step = nice_tick_step(value, target_tick_count)
    return max(step, ceil(value / step) * step)


def nice_ticks(domain_max, target_tick_count=5):
    domain = _positive_finite(domain_max, default=1.0)
    step = nice_tick_step(domain, target_tick_count)
    last_index = max(1, floor((domain + (step * 1e-9)) / step))
    return step, _tick_values_for_step(step, last_index)


@lru_cache(maxsize=512)
def _tick_values_for_step(step, last_index):
    return tuple(
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
    minimum_gap = max(
        8.0,
        float(tick_font_size) * float(dpi) / 144.0,
    )

    for candidate in range(requested, 0, -1):
        step, ticks = nice_ticks(domain, candidate)
        positive_ticks = tuple(value for value in ticks if value > 0.0)
        label_widths = _axis_tick_label_widths(
            positive_ticks,
            step,
            value_format,
            tick_value_format,
            tick_font_size,
            dpi,
            font_family,
            font_weight,
            font_style,
        )
        if len(positive_ticks) > requested:
            continue
        previous_x = None
        previous_width = None
        fits = True
        for value, label_width in zip(positive_ticks, label_widths):
            current_x = (value / domain) * width
            if previous_x is not None and (
                (current_x - (label_width / 2.0))
                - (previous_x + (previous_width / 2.0))
                < minimum_gap
            ):
                fits = False
                break
            previous_x = current_x
            previous_width = label_width
        if fits:
            return candidate

    return 1


@lru_cache(maxsize=512)
def _axis_tick_label_widths(
    ticks,
    step,
    value_format,
    tick_value_format,
    tick_font_size,
    dpi,
    font_family,
    font_weight,
    font_style,
):
    """Measure stable tick identities once per bounded formatting variant."""

    font = measurement_font(
        tick_font_size,
        dpi,
        font_family,
        font_weight,
        font_style,
    )
    return tuple(
        measure_text_width(
            format_axis_tick(value, step, value_format, tick_value_format),
            font,
        )
        for value in ticks
    )


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
        self.semantic_dynamic = (
            self.mode == "dynamic"
            and progressive_bar_scale_active(chart_config)
        )
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
        self._last_tick_step = None
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
        structural_width = None
        if self.semantic_dynamic:
            structural_widths = [
                width
                for sprite in sprites
                if (width := _finite(
                    getattr(sprite, "bar_available_width", None),
                    default=None,
                )) is not None
                and width >= 0.0
            ]
            if structural_widths:
                structural_width = max(structural_widths)
        visible_widths = [
            max(0.0, float(sprite.width))
            for sprite in sprites
            if _visible_positive_value(sprite) is not None
        ]
        visible_width = max(visible_widths) if visible_widths else None
        visible_max = max(
            (
                value
                for sprite in sprites
                if (value := _visible_positive_value(sprite)) is not None
            ),
            default=0.0,
        )
        return self.next_measurements(
            visible_max=visible_max,
            visible_width=visible_width,
            structural_width=structural_width,
        )

    def next_measurements(
        self,
        *,
        visible_max,
        visible_width,
        structural_width=None,
        build_state=True,
    ):
        """Advance from the numeric inputs consumed by ``next``.

        Preview replay can use this entry point without constructing complete
        BarSprite objects for every historical frame.  RenderJob continues to
        call ``next`` and therefore remains the sequential reference path.
        """

        if self.semantic_dynamic and structural_width is not None:
            self.axis_width = max(0.0, float(structural_width))
        elif visible_width is not None:
            self.axis_width = max(0.0, float(visible_width))
        visible_max = max(0.0, _finite(visible_max, default=0.0))
        if self.semantic_dynamic:
            # MotionEngine already supplies a smooth interpolated leader. Use
            # it directly so tick X remains numerically exact; smoothing is
            # retained only for tick identity and opacity lifecycle.
            self.domain = max(MIN_AXIS_DOMAIN, visible_max)
            self._effective_scale = self.axis_width / self.domain
            scale_width = self.axis_width
            scale_domain = self.domain
        else:
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
            scale_width = effective_axis_width
            scale_domain = domain
        self._previous_visible_max = visible_max
        effective_tick_count = adaptive_tick_count(
            scale_width,
            self.target_tick_count,
            self.tick_font_size,
            domain_max=scale_domain,
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
            scale_domain,
            effective_tick_count,
        )
        self._update_tick_opacities(desired_ticks)
        self._last_tick_step = tick_step
        self._started = True
        if not build_state:
            return None
        return self.current_state()

    def advance_measurement_range(
        self,
        visible_maxima,
        visible_widths,
        structural_widths,
        *,
        start_index,
        end_index,
        checkpoint_interval=None,
        checkpoint_callback=None,
    ):
        """Advance a contiguous numeric range with the exact scalar recurrence."""

        axis_width = self.axis_width
        domain = self.domain
        effective_scale = self._effective_scale
        previous_visible_max = self._previous_visible_max
        tick_opacities = self._tick_opacities
        last_tick_step = self._last_tick_step
        started = self._started
        semantic_dynamic = self.semantic_dynamic
        dynamic = self.mode == "dynamic"
        static = self.mode == "static"
        target_tick_count = self.target_tick_count
        tick_font_size = self.tick_font_size
        value_format = self.value_format
        tick_value_format = self.tick_value_format
        chart_config = self.chart_config
        font_family = chart_config.value_font_family or chart_config.font_family
        dpi = chart_config.dpi
        font_weight = chart_config.value_grid_tick_font_weight
        font_style = chart_config.value_grid_tick_font_style

        for index in range(start_index, end_index + 1):
            visible_width = _finite(visible_widths[index], default=None)
            structural_width = _finite(
                structural_widths[index], default=None
            )
            if semantic_dynamic and structural_width is not None:
                axis_width = max(0.0, structural_width)
            elif visible_width is not None:
                axis_width = max(0.0, visible_width)
            visible_max = max(
                0.0,
                _finite(visible_maxima[index], default=0.0),
            )

            if semantic_dynamic:
                domain = max(MIN_AXIS_DOMAIN, visible_max)
                effective_scale = axis_width / domain
                scale_width = axis_width
                scale_domain = domain
            else:
                target_domain = (
                    self.static_domain
                    if static
                    else nice_axis_max(
                        max(MIN_AXIS_DOMAIN, visible_max) * self.headroom,
                        target_tick_count,
                    )
                )
                if domain is None or static:
                    domain = target_domain
                else:
                    smoothing = (
                        self.expansion_smoothing
                        if target_domain > domain
                        else self.contraction_smoothing
                    )
                    domain += (target_domain - domain) * smoothing
                    domain = max(domain, visible_max * 1.015)

                scale_domain = max(MIN_AXIS_DOMAIN, domain)
                desired_scale = axis_width / scale_domain
                scale_width = axis_width
                if dynamic:
                    if effective_scale is None:
                        effective_scale = desired_scale
                    elif visible_max >= previous_visible_max:
                        effective_scale = min(effective_scale, desired_scale)
                    elif desired_scale > effective_scale:
                        effective_scale += (
                            desired_scale - effective_scale
                        ) * self.contraction_smoothing
                    else:
                        effective_scale = desired_scale
                    scale_width = min(
                        axis_width,
                        max(0.0, effective_scale * scale_domain),
                    )
                else:
                    effective_scale = desired_scale

            previous_visible_max = visible_max
            effective_tick_count = adaptive_tick_count(
                scale_width,
                target_tick_count,
                tick_font_size,
                domain_max=scale_domain,
                value_format=value_format,
                font_family=font_family,
                dpi=dpi,
                font_weight=font_weight,
                font_style=font_style,
                tick_value_format=tick_value_format,
            )
            last_tick_step, desired_ticks = nice_ticks(
                scale_domain,
                effective_tick_count,
            )
            desired = set(desired_ticks)
            if not started:
                tick_opacities = {value: 1.0 for value in desired}
            else:
                updated = {}
                for value in set(tick_opacities) | desired:
                    opacity = tick_opacities.get(value, 0.0)
                    if value in desired:
                        opacity = min(
                            1.0, opacity + VALUE_AXIS_TICK_FADE_IN
                        )
                    else:
                        opacity = max(
                            0.0, opacity - VALUE_AXIS_TICK_FADE_OUT
                        )
                    if opacity > 0.0:
                        updated[value] = opacity
                tick_opacities = updated
            started = True

            if (
                checkpoint_interval
                and checkpoint_callback is not None
                and index % checkpoint_interval == 0
            ):
                self._assign_replay_state(
                    axis_width,
                    domain,
                    effective_scale,
                    previous_visible_max,
                    tick_opacities,
                    last_tick_step,
                    started,
                )
                checkpoint_callback(index, self.snapshot())

        self._assign_replay_state(
            axis_width,
            domain,
            effective_scale,
            previous_visible_max,
            tick_opacities,
            last_tick_step,
            started,
        )
        return self.current_state()

    def _assign_replay_state(
        self,
        axis_width,
        domain,
        effective_scale,
        previous_visible_max,
        tick_opacities,
        last_tick_step,
        started,
    ):
        self.axis_width = axis_width
        self.domain = domain
        self._effective_scale = effective_scale
        self._previous_visible_max = previous_visible_max
        self._tick_opacities = tick_opacities
        self._last_tick_step = last_tick_step
        self._started = started

    def current_state(self):
        """Materialize the current immutable state without advancing replay."""

        if not self._started or self.domain is None:
            raise RuntimeError("ValueAxisTracker has not processed a frame.")
        domain = max(MIN_AXIS_DOMAIN, self.domain)
        if self.semantic_dynamic:
            scale = SemanticDataScale(
                origin_x=self.origin_x,
                width=self.axis_width,
                domain_max=domain,
            )
        else:
            effective_width = self.axis_width
            if self.mode == "dynamic" and self._effective_scale is not None:
                effective_width = min(
                    self.axis_width,
                    max(0.0, self._effective_scale * domain),
                )
            scale = GridDisplayScale(
                origin_x=self.origin_x,
                width=effective_width,
                domain_max=domain,
            )
        tick_step = self._last_tick_step
        if tick_step is None:
            raise RuntimeError("ValueAxisTracker has no tick state.")
        line_top, line_bottom, label_y = _vertical_geometry(self.chart_config)
        tick_tolerance = max(1e-6, scale.width * 1e-9)
        ticks = []
        for value, opacity in sorted(self._tick_opacities.items()):
            tick_x = scale.x_for_value(value)
            if opacity <= 0.0:
                continue
            if self.semantic_dynamic:
                if not (
                    scale.origin_x - tick_tolerance
                    <= tick_x
                    <= scale.right_x + tick_tolerance
                ):
                    continue
            elif value > scale.domain_max + (tick_step * 1e-9):
                continue
            ticks.append(ValueAxisTick(
                value=value,
                x=tick_x,
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
            ))
        return ValueAxisState(
            scale=scale,
            ticks=tuple(ticks),
            tick_step=tick_step,
            line_top=line_top,
            line_bottom=line_bottom,
            label_y=label_y,
        )

    def snapshot(self):
        return ValueAxisTrackerSnapshot(
            axis_width=self.axis_width,
            domain=self.domain,
            effective_scale=self._effective_scale,
            previous_visible_max=self._previous_visible_max,
            tick_opacities=tuple(sorted(self._tick_opacities.items())),
            last_tick_step=self._last_tick_step,
            started=self._started,
        )

    def restore(self, snapshot):
        if not isinstance(snapshot, ValueAxisTrackerSnapshot):
            raise TypeError("snapshot must be a ValueAxisTrackerSnapshot")
        self.axis_width = snapshot.axis_width
        self.domain = snapshot.domain
        self._effective_scale = snapshot.effective_scale
        self._previous_visible_max = snapshot.previous_visible_max
        self._tick_opacities = dict(snapshot.tick_opacities)
        self._last_tick_step = snapshot.last_tick_step
        self._started = snapshot.started
        return self

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


def _vertical_geometry(config):
    row_top, row_bottom = structural_race_vertical_bounds(config)
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
