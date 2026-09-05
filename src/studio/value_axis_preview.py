"""Bounded random-access Value Axis replay for Studio previews."""

from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from threading import RLock

import numpy as np
from pandas.util import hash_pandas_object

from core.bar_appearance import uses_configurable_bar_content
from core.bar_value_scale import (
    progressive_bar_scale_active,
)
from core.motion_engine import MotionEngine
from core.value_axis import ValueAxisTracker, _vertical_geometry
from studio.fun_fact_layout import editorial_geometry


_CACHE_MAX_ENTRIES = 4
_CHECKPOINT_INTERVAL = 256
_MAX_CHECKPOINTS = 512
_STATE_MEMO_SIZE = 64
_cache_lock = RLock()
_resolver_cache = OrderedDict()
_preview_bundle_cache = OrderedDict()
_cache_hits = 0
_cache_misses = 0
_bundle_hits = 0
_bundle_misses = 0


@dataclass(frozen=True, slots=True)
class _TransitionMember:
    cubic: bool
    value_curve: tuple
    width_curve: tuple
    opacity_curve: tuple
    value_uses_easing: bool


@dataclass(frozen=True, slots=True)
class _CompiledTransition:
    members: tuple[_TransitionMember, ...]
    available_curves: tuple[tuple, ...]


@dataclass(frozen=True, slots=True)
class _FrameMeasurements:
    visible_max: float
    visible_width: float | None
    structural_width: float | None


@dataclass(frozen=True, slots=True)
class PreviewValueAxisBundle:
    resolver: object
    sprite_sets: tuple


class ValueAxisPreviewResolver:
    """Resolve any preview frame from bounded sequential-state checkpoints."""

    def __init__(self, chart_config, sprite_sets):
        self._config = chart_config
        self._sprite_sets = tuple(tuple(sprites) for sprites in sprite_sets)
        self._motion = MotionEngine(animation_config=chart_config.animation)
        self._steps = max(1, int(chart_config.steps_per_transition))
        self._continuous = chart_config.animation.continuous_motion
        self._transitions = self._compile_transitions(self._sprite_sets)
        (
            self._visible_maxima,
            self._visible_widths,
            self._structural_widths,
        ) = self._compile_frame_measurements()
        self._max_frame_index = (
            0
            if len(self._sprite_sets) < 2
            else (len(self._sprite_sets) - 1) * self._steps
            + (0 if self._continuous else -1)
        )
        self._checkpoints = OrderedDict()
        self._states = OrderedDict()
        self._lock = RLock()

    def state_at(self, frame_index):
        frame_index = max(0, min(int(frame_index), self._max_frame_index))
        with self._lock:
            cached = self._states.get(frame_index)
            if cached is not None:
                self._states.move_to_end(frame_index)
                return cached

            checkpoint_index = max(
                (index for index in self._checkpoints if index <= frame_index),
                default=None,
            )
            tracker = ValueAxisTracker.from_config(
                self._config,
                self._sprite_sets,
            )
            start_index = 0
            if checkpoint_index is not None:
                tracker.restore(self._checkpoints[checkpoint_index])
                start_index = checkpoint_index + 1

            if start_index > frame_index:
                state = tracker.current_state()
            else:
                def store_checkpoint(index, snapshot):
                    self._checkpoints[index] = snapshot
                    while len(self._checkpoints) > _MAX_CHECKPOINTS:
                        self._checkpoints.popitem(last=False)

                state = tracker.advance_measurement_range(
                    self._visible_maxima,
                    self._visible_widths,
                    self._structural_widths,
                    start_index=start_index,
                    end_index=frame_index,
                    checkpoint_interval=_CHECKPOINT_INTERVAL,
                    checkpoint_callback=store_checkpoint,
                )

            self._states[frame_index] = state
            self._states.move_to_end(frame_index)
            while len(self._states) > _STATE_MEMO_SIZE:
                self._states.popitem(last=False)
            return state

    @property
    def checkpoint_count(self):
        return len(self._checkpoints)

    @property
    def memoized_state_count(self):
        return len(self._states)

    @property
    def numeric_array_bytes(self):
        return (
            self._visible_maxima.nbytes
            + self._visible_widths.nbytes
            + self._structural_widths.nbytes
        )

    def _compile_transitions(self, sprite_sets):
        transitions = []
        for index in range(max(0, len(sprite_sets) - 1)):
            start_map = {sprite.name: sprite for sprite in sprite_sets[index]}
            end_map = {sprite.name: sprite for sprite in sprite_sets[index + 1]}
            previous_map = {
                sprite.name: sprite
                for sprite in sprite_sets[index - 1 if index > 0 else index]
            }
            following_index = min(len(sprite_sets) - 1, index + 2)
            following_map = {
                sprite.name: sprite for sprite in sprite_sets[following_index]
            }
            members = []
            available_curves = []
            for name in sorted(set(start_map) | set(end_map)):
                start = start_map.get(name)
                end = end_map.get(name)
                if self._continuous and start is not None and end is not None:
                    previous = previous_map.get(name) or start
                    following = following_map.get(name) or end
                    value_curve = (
                        _compile_monotone_curve(
                            previous.value,
                            start.value,
                            end.value,
                            following.value,
                            self._motion,
                        )
                        if self._config.animation.value_smoothing
                        else ("linear", start.value, end.value, 0.0, 0.0)
                    )
                    available_curve = _compile_optional_curve(
                        previous.bar_available_width,
                        start.bar_available_width,
                        end.bar_available_width,
                        following.bar_available_width,
                    )
                    if (
                        available_curve is not None
                        and available_curve not in available_curves
                    ):
                        available_curves.append(available_curve)
                    members.append(_TransitionMember(
                        cubic=True,
                        value_curve=value_curve,
                        width_curve=_compile_bounded_curve(
                            previous.width,
                            start.width,
                            end.width,
                            following.width,
                        ),
                        opacity_curve=_compile_bounded_curve(
                            previous.opacity,
                            start.opacity,
                            end.opacity,
                            following.opacity,
                        ),
                        value_uses_easing=False,
                    ))
                    continue

                start_value = start.value if start is not None else 0
                end_value = end.value if end is not None else 0
                start_width = start.width if start is not None else 0
                end_width = end.width if end is not None else 0
                enter_exit = self._config.animation.enter_exit
                start_opacity = (
                    start.opacity
                    if start is not None
                    else (0.0 if enter_exit else 1.0)
                )
                end_opacity = (
                    end.opacity
                    if end is not None
                    else (0.0 if enter_exit else 1.0)
                )
                start_available = (
                    start.bar_available_width if start is not None else None
                )
                end_available = (
                    end.bar_available_width if end is not None else None
                )
                if start_available is None:
                    start_available = end_available
                if end_available is None:
                    end_available = start_available
                available_curve = (
                    None
                    if start_available is None
                    else _compile_linear_curve(start_available, end_available)
                )
                if (
                    available_curve is not None
                    and available_curve not in available_curves
                ):
                    available_curves.append(available_curve)
                members.append(_TransitionMember(
                    cubic=False,
                    value_curve=_compile_linear_curve(start_value, end_value),
                    width_curve=_compile_linear_curve(start_width, end_width),
                    opacity_curve=_compile_linear_curve(
                        start_opacity, end_opacity
                    ),
                    value_uses_easing=self._config.animation.value_smoothing,
                ))
            transitions.append(_CompiledTransition(
                members=tuple(members),
                available_curves=tuple(available_curves),
            ))
        return tuple(transitions)

    def _compile_frame_measurements(self):
        if not self._transitions:
            measurements = _measure_period(self._sprite_sets[0])
            return (
                np.asarray((measurements.visible_max,), dtype=float),
                np.asarray((
                    np.nan
                    if measurements.visible_width is None
                    else measurements.visible_width,
                ), dtype=float),
                np.asarray((
                    np.nan
                    if measurements.structural_width is None
                    else measurements.structural_width,
                ), dtype=float),
            )

        maxima_chunks = []
        width_chunks = []
        structural_chunks = []
        for index, transition in enumerate(self._transitions):
            if self._continuous:
                first_step = 0 if index == 0 else 1
                raw_t = np.arange(
                    first_step, self._steps + 1, dtype=float
                ) / self._steps
            elif self._steps > 1:
                raw_t = np.arange(self._steps, dtype=float) / (
                    self._steps - 1
                )
            else:
                raw_t = np.ones(1, dtype=float)
            maximum, width, structural = self._measure_transition(
                transition, raw_t
            )
            maxima_chunks.append(maximum)
            width_chunks.append(width)
            structural_chunks.append(structural)
        return (
            np.concatenate(maxima_chunks),
            np.concatenate(width_chunks),
            np.concatenate(structural_chunks),
        )

    def _measure_transition(self, transition, raw_t):
        visible_max = np.zeros(raw_t.shape, dtype=float)
        visible_width = np.full(raw_t.shape, np.nan, dtype=float)
        structural_width = np.full(raw_t.shape, np.nan, dtype=float)
        easing = self._config.animation.easing_function()
        eased_t = np.fromiter(
            (easing(float(value)) for value in raw_t),
            dtype=float,
            count=len(raw_t),
        )

        for curve in transition.available_curves:
            candidate = (
                _evaluate_bounded_curve_array(curve, raw_t)
                if self._continuous
                else _evaluate_linear_curve_array(curve, eased_t)
            )
            valid = np.isfinite(candidate) & (candidate >= 0.0)
            structural_width = np.where(
                valid,
                np.fmax(structural_width, candidate),
                structural_width,
            )

        for member in transition.members:
            if member.cubic:
                value = _evaluate_monotone_curve_array(
                    member.value_curve, raw_t
                )
                width = np.maximum(0.0, _evaluate_bounded_curve_array(
                    member.width_curve, raw_t
                ))
                opacity = np.minimum(1.0, np.maximum(
                    0.0,
                    _evaluate_bounded_curve_array(member.opacity_curve, raw_t),
                ))
            else:
                value_t = eased_t if member.value_uses_easing else raw_t
                value = _evaluate_linear_curve_array(
                    member.value_curve, value_t
                )
                width = _evaluate_linear_curve_array(
                    member.width_curve, eased_t
                )
                opacity = _evaluate_linear_curve_array(
                    member.opacity_curve, eased_t
                )
            valid = (
                np.isfinite(value)
                & (value > 0.0)
                & np.isfinite(opacity)
                & (opacity > 0.0)
            )
            visible_max = np.where(
                valid, np.maximum(visible_max, value), visible_max
            )
            visible_width = np.where(
                valid,
                np.fmax(visible_width, np.maximum(0.0, width)),
                visible_width,
            )

        return visible_max, visible_width, structural_width


def get_value_axis_preview_resolver(chart_config, sprite_sets):
    """Return a process-lifetime resolver keyed only by axis-relevant inputs."""

    global _cache_hits, _cache_misses
    sprite_sets = tuple(tuple(sprites) for sprites in sprite_sets)
    fingerprint = value_axis_preview_fingerprint(chart_config, sprite_sets)
    with _cache_lock:
        resolver = _resolver_cache.get(fingerprint)
        if resolver is not None:
            _cache_hits += 1
            _resolver_cache.move_to_end(fingerprint)
            return resolver
        _cache_misses += 1
        resolver = ValueAxisPreviewResolver(chart_config, sprite_sets)
        _resolver_cache[fingerprint] = resolver
        while len(_resolver_cache) > _CACHE_MAX_ENTRIES:
            _resolver_cache.popitem(last=False)
        return resolver


def get_preview_value_axis_bundle(
    chart_config,
    timeline,
    years,
    selector,
    layout,
):
    """Cache period layouts so warm Preview never rebuilds axis history input."""

    global _bundle_hits, _bundle_misses
    fingerprint = preview_value_axis_source_fingerprint(
        chart_config,
        timeline,
        years,
        selector,
        layout,
    )
    with _cache_lock:
        bundle = _preview_bundle_cache.get(fingerprint)
        if bundle is not None:
            _bundle_hits += 1
            _preview_bundle_cache.move_to_end(fingerprint)
            return bundle
        _bundle_misses += 1
        sprite_sets = tuple(
            layout.build(selector.select(timeline.get_frame(year)))
            for year in years
        )
        bundle = PreviewValueAxisBundle(
            resolver=get_value_axis_preview_resolver(
                chart_config, sprite_sets
            ),
            sprite_sets=sprite_sets,
        )
        _preview_bundle_cache[fingerprint] = bundle
        while len(_preview_bundle_cache) > _CACHE_MAX_ENTRIES:
            _preview_bundle_cache.popitem(last=False)
        return bundle


def preview_value_axis_source_fingerprint(
    chart_config,
    timeline,
    years,
    selector,
    layout,
):
    """Fingerprint source data and only layout inputs that can alter the axis."""

    dataset = timeline.config
    columns = (
        dataset.year_column,
        dataset.name_column,
        dataset.value_column,
    )
    relevant = timeline.df.loc[
        timeline.df[dataset.year_column].isin(years),
        list(columns),
    ].sort_values(list(columns), kind="mergesort")
    row_hashes = hash_pandas_object(
        relevant,
        index=False,
        categorize=False,
    ).values.tobytes()
    visible_counts = _effective_visible_counts(
        chart_config,
        relevant,
        dataset,
        selector,
        years,
    )
    source = (
        tuple(years),
        sha256(row_hashes).digest(),
        tuple(sorted(dataset.category_labels.items())),
        (
            selector.config.top_n,
            selector.config.aggregate_other,
            selector.config.other_label,
        ),
        _axis_settings_fingerprint(chart_config),
        _layout_axis_fingerprint(
            chart_config,
            layout.fun_fact_config,
            visible_counts,
        ),
    )
    return sha256(repr(source).encode("utf-8")).digest()


def value_axis_preview_fingerprint(chart_config, sprite_sets):
    """Hash numerical history and the settings that can alter axis output."""

    axis_settings = _axis_settings_fingerprint(chart_config)
    periods = tuple(
        tuple(
            (
                sprite.name,
                _fingerprint_float(sprite.value),
                _fingerprint_float(sprite.width),
                _fingerprint_float(sprite.opacity),
                _fingerprint_float(sprite.bar_available_width),
            )
            for sprite in sorted(sprites, key=lambda item: item.name)
        )
        for sprites in sprite_sets
    )
    return sha256(repr((axis_settings, periods)).encode("utf-8")).digest()


def _axis_settings_fingerprint(chart_config):
    animation = chart_config.animation
    value_format = chart_config.value_format
    return (
        chart_config.value_grid_mode,
        int(chart_config.steps_per_transition),
        bool(animation.continuous_motion),
        bool(animation.value_smoothing),
        bool(animation.enter_exit),
        animation.easing,
        float(chart_config.left_margin),
        float(chart_config.max_bar_width),
        progressive_bar_scale_active(chart_config),
        int(chart_config.value_grid_target_tick_count),
        int(chart_config.value_grid_tick_font_size),
        chart_config.value_grid_tick_font_weight,
        chart_config.value_grid_tick_font_style,
        chart_config.value_grid_tick_value_format,
        chart_config.value_font_family or chart_config.font_family,
        int(chart_config.dpi),
        (
            value_format.decimal_places,
            value_format.compact,
            value_format.prefix,
            value_format.suffix,
            value_format.multiplier,
        ),
        _vertical_geometry(chart_config),
    )


def _layout_axis_fingerprint(chart_config, fun_fact_config, visible_counts):
    result = [
        chart_config.width,
        chart_config.left_margin,
        chart_config.right_margin,
        visible_counts,
    ]
    reserved_editorial = (
        fun_fact_config.enabled
        and fun_fact_config.layout == "editorial_floating"
        and fun_fact_config.editorial_layout_mode == "reserved"
    )
    reserves_value_lane = (
        chart_config.value_labels_enabled
        and uses_configurable_bar_content(chart_config)
        and (
            chart_config.bar_value_position == "outside"
            or (
                chart_config.bar_value_position == "auto"
                and reserved_editorial
            )
        )
    )
    if reserves_value_lane:
        value_format = chart_config.value_format
        result.append((
            chart_config.bar_appearance_mode,
            chart_config.bar_value_position,
            chart_config.value_label_gap,
            chart_config.value_label_edge_padding,
            chart_config.value_font_size,
            chart_config.value_font_family or chart_config.font_family,
            chart_config.value_font_weight,
            chart_config.value_font_style,
            chart_config.dpi,
            value_format.decimal_places,
            value_format.compact,
            value_format.prefix,
            value_format.suffix,
            value_format.multiplier,
        ))
    if reserved_editorial:
        result.append((
            editorial_geometry(chart_config, fun_fact_config),
            fun_fact_config.editorial_collision_gap,
            chart_config.bar_vertical_layout_mode,
            chart_config.bar_height,
            chart_config.bar_gap,
            chart_config.top_margin,
            chart_config.bottom_margin,
            chart_config.bar_vertical_top_padding,
            chart_config.bar_vertical_bottom_padding,
        ))
    return tuple(result)


def _effective_visible_counts(
    chart_config,
    relevant,
    dataset_config,
    selector,
    years,
):
    counts = []
    for year in years:
        period = relevant.loc[
            relevant[dataset_config.year_column] == year
        ]
        count = int((period[dataset_config.value_column] != 0).sum())
        top_n = selector.config.top_n
        if top_n is not None and count > top_n:
            count = top_n + (1 if selector.config.aggregate_other else 0)
        if chart_config.max_visible_bars is not None:
            count = min(count, max(0, chart_config.max_visible_bars))
        if (
            chart_config.auto_fit_bar_count
            and chart_config.bar_vertical_layout_mode != "fill_available"
        ):
            count = min(count, chart_config.bar_capacity)
        counts.append(count)
    return tuple(counts)


def clear_value_axis_preview_cache():
    global _cache_hits, _cache_misses, _bundle_hits, _bundle_misses
    with _cache_lock:
        _resolver_cache.clear()
        _preview_bundle_cache.clear()
        _cache_hits = 0
        _cache_misses = 0
        _bundle_hits = 0
        _bundle_misses = 0


def value_axis_preview_cache_info():
    with _cache_lock:
        return {
            "entries": len(_resolver_cache),
            "max_entries": _CACHE_MAX_ENTRIES,
            "hits": _cache_hits,
            "misses": _cache_misses,
            "bundle_entries": len(_preview_bundle_cache),
            "bundle_hits": _bundle_hits,
            "bundle_misses": _bundle_misses,
            "checkpoints": sum(
                resolver.checkpoint_count for resolver in _resolver_cache.values()
            ),
            "memoized_states": sum(
                resolver.memoized_state_count
                for resolver in _resolver_cache.values()
            ),
            "numeric_array_bytes": sum(
                resolver.numeric_array_bytes
                for resolver in _resolver_cache.values()
            ),
            "max_checkpoints_per_resolver": _MAX_CHECKPOINTS,
        }


def _measure_period(sprites):
    visible_max = 0.0
    visible_width = None
    structural_width = None
    for sprite in sprites:
        available = _finite(sprite.bar_available_width)
        if available is not None and available >= 0.0:
            structural_width = (
                available
                if structural_width is None
                else max(structural_width, available)
            )
        value = _finite(sprite.value)
        opacity = _finite(sprite.opacity)
        if value is None or value <= 0.0 or opacity is None or opacity <= 0.0:
            continue
        visible_max = max(visible_max, value)
        width = max(0.0, float(sprite.width))
        visible_width = width if visible_width is None else max(visible_width, width)
    return _FrameMeasurements(visible_max, visible_width, structural_width)


def _compile_bounded_curve(p0, p1, p2, p3):
    if p0 == p1 == p2 == p3:
        return (p1,)
    return (
        p1,
        p2,
        2 * p1,
        -p0 + p2,
        2 * p0 - 5 * p1 + 4 * p2 - p3,
        -p0 + 3 * p1 - 3 * p2 + p3,
    )


def _compile_optional_curve(p0, p1, p2, p3):
    if p1 is None and p2 is None:
        return None
    p1 = p2 if p1 is None else p1
    p2 = p1 if p2 is None else p2
    p0 = p1 if p0 is None else p0
    p3 = p2 if p3 is None else p3
    return _compile_bounded_curve(p0, p1, p2, p3)


def _evaluate_bounded_curve_array(curve, t):
    if len(curve) == 1:
        return np.full(t.shape, curve[0], dtype=float)
    p1, p2, c0, c1, c2, c3 = curve
    value = 0.5 * (
        c0
        + c1 * t
        + c2 * (t * t)
        + c3 * (t * t * t)
    )
    return np.minimum(max(p1, p2), np.maximum(min(p1, p2), value))


def _compile_linear_curve(start, end):
    return (start,) if start == end else (start, end)


def _evaluate_linear_curve_array(curve, t):
    if len(curve) == 1:
        return np.full(t.shape, curve[0], dtype=float)
    return curve[0] + (curve[1] - curve[0]) * t


def _compile_monotone_curve(p0, p1, p2, p3, motion):
    if p1 == p2:
        return ("constant", p1, p2, 0.0, 0.0)
    points = tuple(float(value) for value in (p0, p1, p2, p3))
    if not all(isfinite(value) for value in points):
        return ("linear", p1, p2, 0.0, 0.0)
    scale = max(1.0, *(abs(value) for value in points))
    q0, q1, q2, q3 = (value / scale for value in points)
    d0 = q1 - q0
    d1 = q2 - q1
    d2 = q3 - q2
    if d1 == 0.0:
        return ("linear", p1, p2, 0.0, 0.0)
    alpha = motion._pchip_tangent(d0, d1) / d1
    beta = motion._pchip_tangent(d1, d2) / d1
    return ("pchip", p1, p2, alpha, beta)


def _evaluate_monotone_curve_array(curve, t):
    kind, p1, p2, alpha, beta = curve
    if kind == "constant":
        return np.full(t.shape, p1, dtype=float)
    if kind == "linear":
        result = p1 + (p2 - p1) * t
    else:
        t2 = t * t
        t3 = t2 * t
        h10 = t3 - (2.0 * t2) + t
        h01 = (-2.0 * t3) + (3.0 * t2)
        h11 = t3 - t2
        progress = h01 + (h10 * alpha) + (h11 * beta)
        segment_delta = p2 - p1
        if isfinite(segment_delta):
            result = p1 + (segment_delta * progress)
        else:
            result = (p1 * (1.0 - progress)) + (p2 * progress)
    if t[0] <= 0.0:
        result[0] = p1
    if t[-1] >= 1.0:
        result[-1] = p2
    return result


def _fingerprint_float(value):
    if value is None:
        return None
    try:
        return float(value).hex()
    except (TypeError, ValueError):
        return repr(value)


def _finite(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None
