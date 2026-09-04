from collections import OrderedDict
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
from threading import RLock
from time import perf_counter
from types import MappingProxyType

from core.bar_value_scale import BarValueScaleResolver, scale_bar_sprites
from core.bar_text_geometry import value_text_metric_cache_info
from core.motion_engine import MotionEngine
from core.scene_geometry import (
    build_scene_geometry,
    build_smart_scene_geometry,
    build_smart_text_bounds,
)
from models.scene import Scene
from studio.fun_fact_layout import editorial_geometry, editorial_safe_area
from utils.text_fit import measurement_font


SMART_CANDIDATE_ORDER = (
    "bottom_center",
    "center",
    "bottom_left",
    "bottom_right",
    "middle_left",
    "middle_right",
    "top_left",
    "top_center",
    "top_right",
)

_SMART_CACHE_MAX_SIZE = 6
_SMART_RESOLVER_CACHE = OrderedDict()
_SMART_CACHE_LOCK = RLock()

_SMART_CHART_FIELDS = (
    "width", "height", "dpi", "left_margin", "right_margin", "top_margin",
    "bottom_margin", "bar_height", "bar_gap", "auto_fit_bar_count",
    "max_visible_bars", "bar_vertical_layout_mode",
    "bar_vertical_top_padding", "bar_vertical_bottom_padding", "bar_shape",
    "bar_appearance_mode", "start_bars_at_zero", "leader_full_width_point",
    "steps_per_transition", "title", "title_font_size", "subtitle_font_size",
    "time_label_font_size", "source_font_size", "label_font_size",
    "value_font_size", "title_font_family", "subtitle_font_family",
    "time_label_font_family", "source_font_family", "label_font_family",
    "value_font_family", "title_font_style", "subtitle_font_style",
    "time_label_font_style", "source_font_style", "label_font_weight",
    "label_font_style", "value_font_weight", "value_font_style",
    "title_font_weight", "subtitle_font_weight", "source_font_weight",
    "title_x", "title_y", "subtitle_x", "subtitle_y", "time_label_x",
    "time_label_y", "source_x", "source_y", "time_label_enabled",
    "date_style", "flip_calendar_scale", "category_labels_enabled",
    "value_labels_enabled", "label_text_opacity", "value_text_opacity",
    "label_min_x", "value_label_gap", "value_label_edge_padding",
    "value_label_min_x", "value_label_inside_padding", "logos_enabled",
    "logo_size", "primary_logo_min_size", "logo_gap", "logo_label_gap",
    "bar_logo_position", "bar_logo_padding", "bar_secondary_logo_enabled",
    "bar_secondary_logo_layout", "bar_secondary_logo_position",
    "bar_secondary_logo_badge_corner", "bar_secondary_logo_size",
    "bar_secondary_logo_gap", "bar_secondary_logo_padding",
    "bar_label_position", "bar_label_offset_y", "bar_label_border_enabled",
    "bar_label_border_width", "bar_label_shadow_enabled",
    "bar_label_shadow_offset_x", "bar_label_shadow_offset_y",
    "bar_value_position", "bar_value_border_enabled",
    "bar_value_border_width", "bar_value_shadow_enabled",
    "bar_value_shadow_offset_x", "bar_value_shadow_offset_y",
)

_SMART_FUN_FACT_FIELDS = (
    "enabled", "layout", "panel_margin", "editorial_card_x",
    "editorial_card_y", "editorial_card_width", "editorial_card_height",
    "editorial_layout_mode", "editorial_placement_mode",
    "editorial_keep_inside_safe_area", "editorial_protect_top_n",
    "editorial_bar_clearance",
)


@dataclass(frozen=True)
class _Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height


@dataclass(frozen=True)
class SmartPlacementDecision:
    fact_id: str
    position: tuple[int, int]
    candidate: str
    score: float
    protected_overlap: float
    used_fallback: bool


@dataclass
class _SchedulerView:
    facts: tuple
    timeline: object


@dataclass
class _TimelineView:
    years: tuple
    time_labels: dict
    period_indexes: dict

    def get_time_label(self, period):
        try:
            numeric_period = float(period)
        except (TypeError, ValueError):
            return str(period)
        nearest = min(self.years, key=lambda value: abs(value - numeric_period))
        return self.time_labels.get(nearest, str(nearest))

    def get_period_index(self, period):
        return self.period_indexes[int(period)]

    def get_timeline_position(self, period_a, *, period_b=None, progress=0.0):
        start = float(self.get_period_index(period_a))
        if period_b is None:
            return start
        end = float(self.get_period_index(period_b))
        progress = max(0.0, min(1.0, float(progress)))
        return start + ((end - start) * progress)


class _CalendarPresence:
    def state_at(self, _frame_index):
        return True


class SmartEditorialPlacementResolver:
    """Immutable O(1) lookup of one deterministic position per card window."""

    def __init__(self, decisions, *, precompute_stats=None):
        self._decisions = MappingProxyType(dict(decisions))
        self._precompute_stats = MappingProxyType(dict(precompute_stats or {}))

    def position_for(self, fact_id):
        decision = self._decisions.get(str(fact_id))
        return decision.position if decision is not None else None

    def decision_for(self, fact_id):
        return self._decisions.get(str(fact_id))

    @property
    def precompute_stats(self):
        return self._precompute_stats

    @classmethod
    def from_geometry(
        cls,
        chart_config,
        fun_fact_config,
        scheduler,
        geometry_by_timeline_index,
    ):
        if (
            fun_fact_config.editorial_placement_mode != "smart"
            or fun_fact_config.layout != "editorial_floating"
            or fun_fact_config.editorial_layout_mode != "overlay"
        ):
            return cls({})
        decisions = {}
        frames_by_card = {}
        for resolved in scheduler.facts:
            window = [
                geometry
                for index, geometry in sorted(geometry_by_timeline_index.items())
                if resolved.start_index - 1
                <= _timeline_position(index)
                <= resolved.end_index + 1
            ]
            if not window:
                continue
            frames_by_card[resolved.fact.id] = len(window)
            decisions[resolved.fact.id] = _resolve_window(
                chart_config,
                fun_fact_config,
                resolved.fact.id,
                window,
            )
        return cls(decisions, precompute_stats={
            "active_cards": len(decisions),
            "frames_analyzed": len(geometry_by_timeline_index),
            "frames_by_card": frames_by_card,
            "obstacles_analyzed": sum(
                len(geometry.get("bar_obstacles", geometry.get("bar_rects", ())))
                for geometry in geometry_by_timeline_index.values()
            ),
        })


def build_smart_editorial_placement_resolver(
    *,
    chart_config,
    fun_fact_config,
    scheduler,
    periods,
    sprites_by_period,
    source_label,
    calendar_resolver=None,
):
    if (
        scheduler is None
        or fun_fact_config.editorial_placement_mode != "smart"
        or fun_fact_config.layout != "editorial_floating"
        or fun_fact_config.editorial_layout_mode != "overlay"
    ):
        return None
    periods = tuple(periods)
    started_at = perf_counter()
    logo_availability, asset_signatures = _logo_asset_inventory(
        periods, sprites_by_period,
    )
    fingerprint = _smart_geometry_fingerprint(
        chart_config=chart_config,
        fun_fact_config=fun_fact_config,
        scheduler=scheduler,
        periods=periods,
        sprites_by_period=sprites_by_period,
        source_label=source_label,
        calendar_resolver=calendar_resolver,
        asset_signatures=asset_signatures,
    )
    cached = _smart_cache_get(fingerprint)
    if cached is not None:
        decisions, cached_stats = cached
        resolver = SmartEditorialPlacementResolver(
            decisions,
            precompute_stats={
                **cached_stats,
                "cache_hit": True,
                "fingerprint": fingerprint,
                "precompute_seconds": perf_counter() - started_at,
            },
        )
        scheduler.set_placement_resolver(resolver)
        return resolver

    scale_resolver = BarValueScaleResolver.from_config(
        chart_config,
        (sprites_by_period[period] for period in periods),
    )
    metric_before = value_text_metric_cache_info()
    font_before = measurement_font.cache_info()
    stream_args = {
        "chart_config": chart_config,
        "fun_fact_config": fun_fact_config,
        "scheduler": scheduler,
        "periods": periods,
        "sprites_by_period": sprites_by_period,
        "source_label": source_label,
        "calendar_resolver": calendar_resolver,
        "scale_resolver": scale_resolver,
        "logo_availability": logo_availability,
    }
    resolver = (
        _parallel_stream_smart_editorial_placement(**stream_args)
        if len(periods) >= 80 and len(scheduler.facts) >= 3
        else _stream_smart_editorial_placement(**stream_args)
    )
    resolver = SmartEditorialPlacementResolver(
        resolver._decisions,
        precompute_stats={
            **_metric_stats(
                metric_before,
                value_text_metric_cache_info(),
                font_before,
                measurement_font.cache_info(),
            ),
            **resolver.precompute_stats,
            "logo_metadata_loads": len(asset_signatures),
            "cache_hit": False,
            "fingerprint": fingerprint,
            "precompute_seconds": perf_counter() - started_at,
        },
    )
    _smart_cache_put(
        fingerprint,
        (dict(resolver._decisions), dict(resolver.precompute_stats)),
    )
    scheduler.set_placement_resolver(resolver)
    return resolver


def _metric_stats(metric_before, metric_after, font_before, font_after):
    hits = metric_after.hits - metric_before.hits
    misses = metric_after.misses - metric_before.misses
    requests = hits + misses
    return {
        "value_metric_requests": requests,
        "value_metric_unique_keys": misses,
        "value_metric_cache_hits": hits,
        "value_metric_cache_misses": misses,
        "value_metric_hit_rate": hits / requests if requests else 0.0,
        "font_object_loads": font_after.misses - font_before.misses,
    }


def _parallel_stream_smart_editorial_placement(**stream_args):
    """Split large, non-overlapping card windows across three processes."""
    facts = tuple(stream_args["scheduler"].facts)
    worker_count = min(4, len(facts))
    chunk_size = (len(facts) + worker_count - 1) // worker_count
    chunks = tuple(
        facts[index:index + chunk_size]
        for index in range(0, len(facts), chunk_size)
    )
    if len(chunks) < 3:
        return _stream_smart_editorial_placement(**stream_args)
    tasks = []
    font_overrides = _font_path_overrides(stream_args["chart_config"])
    timeline = stream_args["scheduler"].timeline
    timeline_view = _TimelineView(
        years=tuple(timeline.years),
        time_labels=dict(timeline._time_labels),
        period_indexes=dict(timeline._period_indexes),
    )
    for chunk in chunks:
        task = dict(stream_args)
        task["scheduler"] = _SchedulerView(
            facts=tuple(chunk),
            timeline=timeline_view,
        )
        if task["calendar_resolver"] is not None:
            task["calendar_resolver"] = _CalendarPresence()
        task["font_path_overrides"] = font_overrides
        tasks.append(task)
    worker_path = Path(__file__).with_name("smart_placement_worker.py")
    processes = []
    results = []
    try:
        with tempfile.TemporaryDirectory(prefix="barchart-smart-") as temp_dir:
            temp_dir = Path(temp_dir)
            for index, task in enumerate(tasks[:-1]):
                input_path = temp_dir / f"input-{index}.pickle"
                output_path = temp_dir / f"output-{index}.pickle"
                with input_path.open("wb") as handle:
                    pickle.dump(task, handle, protocol=pickle.HIGHEST_PROTOCOL)
                process = subprocess.Popen(
                    [
                        sys.executable,
                        str(worker_path),
                        str(input_path),
                        str(output_path),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                processes.append((process, output_path))
            local_task = dict(tasks[-1])
            local_task.pop("font_path_overrides", None)
            local_metric_before = value_text_metric_cache_info()
            local_font_before = measurement_font.cache_info()
            local_result = _stream_smart_editorial_placement(**local_task)
            results.append(SmartEditorialPlacementResolver(
                local_result._decisions,
                precompute_stats={
                    **local_result.precompute_stats,
                    **_metric_stats(
                        local_metric_before,
                        value_text_metric_cache_info(),
                        local_font_before,
                        measurement_font.cache_info(),
                    ),
                },
            ))
            for process, output_path in processes:
                _, stderr = process.communicate()
                if process.returncode != 0:
                    raise RuntimeError(
                        "Smart placement worker failed: " + stderr.strip()
                    )
                with output_path.open("rb") as handle:
                    decisions, stats = pickle.load(handle)
                results.append(SmartEditorialPlacementResolver(
                    decisions, precompute_stats=stats,
                ))
    except (OSError, RuntimeError, pickle.PickleError, EOFError):
        for process, _ in processes:
            if process.poll() is None:
                process.terminate()
        return _stream_smart_editorial_placement(**stream_args)
    decisions = {}
    frames_by_card = {}
    for result in results:
        decisions.update(result._decisions)
        frames_by_card.update(result.precompute_stats["frames_by_card"])
    return SmartEditorialPlacementResolver(decisions, precompute_stats={
        "active_cards": len(decisions),
        "frames_analyzed": sum(
            result.precompute_stats["frames_analyzed"] for result in results
        ),
        "frames_by_card": frames_by_card,
        "obstacles_analyzed": sum(
            result.precompute_stats["obstacles_analyzed"] for result in results
        ),
        "scene_geometry_objects_retained": 0,
        "smart_frame_geometry_constructions": sum(
            result.precompute_stats["smart_frame_geometry_constructions"]
            for result in results
        ),
        "parallel_workers": len(results),
        **{
            key: sum(result.precompute_stats.get(key, 0) for result in results)
            for key in (
                "value_metric_requests", "value_metric_unique_keys",
                "value_metric_cache_hits", "value_metric_cache_misses",
                "font_object_loads",
            )
        },
        "value_metric_hit_rate": (
            sum(
                result.precompute_stats.get("value_metric_cache_hits", 0)
                for result in results
            )
            / max(1, sum(
                result.precompute_stats.get("value_metric_requests", 0)
                for result in results
            ))
        ),
    })


def _font_path_overrides(chart_config):
    specifications = {
        (
            chart_config.value_font_size,
            chart_config.dpi,
            chart_config.value_font_family or chart_config.font_family,
            chart_config.value_font_weight,
            chart_config.value_font_style,
        ),
        (
            chart_config.title_font_size, chart_config.dpi,
            chart_config.title_font_family,
            chart_config.title_font_weight, chart_config.title_font_style,
        ),
        (
            chart_config.subtitle_font_size, chart_config.dpi,
            chart_config.subtitle_font_family,
            chart_config.subtitle_font_weight, chart_config.subtitle_font_style,
        ),
        (
            chart_config.source_font_size, chart_config.dpi,
            chart_config.source_font_family,
            chart_config.source_font_weight, chart_config.source_font_style,
        ),
        (
            chart_config.source_font_size, chart_config.dpi,
            chart_config.source_font_family or chart_config.font_family,
            chart_config.source_font_weight, chart_config.source_font_style,
        ),
        (
            chart_config.time_label_font_size, chart_config.dpi,
            chart_config.time_label_font_family,
            chart_config.time_label_font_weight,
            chart_config.time_label_font_style,
        ),
    }
    return {
        specification: str(measurement_font(*specification).path)
        for specification in specifications
    }


def clear_smart_editorial_placement_cache():
    """Clear the bounded process cache (primarily for deterministic tests)."""
    with _SMART_CACHE_LOCK:
        _SMART_RESOLVER_CACHE.clear()


def smart_editorial_placement_cache_info():
    with _SMART_CACHE_LOCK:
        return {
            "size": len(_SMART_RESOLVER_CACHE),
            "max_size": _SMART_CACHE_MAX_SIZE,
            "fingerprints": tuple(_SMART_RESOLVER_CACHE),
        }


def _smart_cache_get(key):
    with _SMART_CACHE_LOCK:
        value = _SMART_RESOLVER_CACHE.get(key)
        if value is not None:
            _SMART_RESOLVER_CACHE.move_to_end(key)
        return value


def _smart_cache_put(key, value):
    with _SMART_CACHE_LOCK:
        _SMART_RESOLVER_CACHE[key] = value
        _SMART_RESOLVER_CACHE.move_to_end(key)
        while len(_SMART_RESOLVER_CACHE) > _SMART_CACHE_MAX_SIZE:
            _SMART_RESOLVER_CACHE.popitem(last=False)


def _smart_geometry_fingerprint(
    *, chart_config, fun_fact_config, scheduler, periods,
    sprites_by_period, source_label, calendar_resolver, asset_signatures,
):
    chart = {
        name: getattr(chart_config, name)
        for name in _SMART_CHART_FIELDS
    }
    chart["animation"] = asdict(chart_config.animation)
    chart["value_format"] = asdict(chart_config.value_format)
    chart["font_family"] = chart_config.font_family
    facts = [
        (
            str(resolved.fact.id),
            float(resolved.start_index),
            float(resolved.end_index),
        )
        for resolved in scheduler.facts
    ]
    sprites = []
    for period in periods:
        sprites.append((
            _stable_value(period),
            [
                (
                    str(sprite.name), float(sprite.value), float(sprite.x),
                    float(sprite.y), float(sprite.width), float(sprite.height),
                    _stable_value(sprite.rank), float(sprite.opacity),
                    str(sprite.rank_motion_state),
                    float(sprite.rank_motion_progress),
                    _stable_value(sprite.rank_motion_target),
                    _stable_value(sprite.bar_available_width),
                    str(sprite.logo_path or ""),
                    str(sprite.secondary_logo_path or ""),
                )
                for sprite in sprites_by_period[period]
            ],
        ))
    payload = {
        "chart": chart,
        "fun_fact": {
            name: getattr(fun_fact_config, name)
            for name in _SMART_FUN_FACT_FIELDS
        },
        "facts": facts,
        "periods": [_stable_value(period) for period in periods],
        "time_labels": [
            scheduler.timeline.get_time_label(period) for period in periods
        ],
        "sprites": sprites,
        "assets": asset_signatures,
        "source_label": str(source_label or ""),
        "calendar": calendar_resolver is not None,
        "algorithm": 2,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _stable_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _logo_asset_inventory(periods, sprites_by_period):
    paths = {
        str(path)
        for period in periods
        for sprite in sprites_by_period[period]
        for path in (sprite.logo_path, sprite.secondary_logo_path)
        if path
    }
    availability = {}
    signatures = []
    for raw_path in sorted(paths):
        try:
            stat = Path(raw_path).stat()
            availability[raw_path] = True
            signatures.append((raw_path, stat.st_size, stat.st_mtime_ns))
        except (OSError, TypeError, ValueError):
            availability[raw_path] = False
            signatures.append((raw_path, None, None))
    return availability, signatures


def _stream_smart_editorial_placement(
    *, chart_config, fun_fact_config, scheduler, periods, sprites_by_period,
    source_label, calendar_resolver, scale_resolver, logo_availability,
):
    accumulators = {
        str(resolved.fact.id): _new_card_accumulator(
            chart_config, fun_fact_config,
        )
        for resolved in scheduler.facts
    }
    frames_by_card = {str(resolved.fact.id): 0 for resolved in scheduler.facts}
    frames_analyzed = 0
    obstacles_analyzed = 0
    for _, position, geometry in _iter_effective_smart_geometry(
        chart_config=chart_config,
        fun_fact_config=fun_fact_config,
        scheduler=scheduler,
        periods=periods,
        sprites_by_period=sprites_by_period,
        source_label=source_label,
        calendar_resolver=calendar_resolver,
        scale_resolver=scale_resolver,
        logo_availability=logo_availability,
    ):
        frames_analyzed += 1
        obstacles_analyzed += len(geometry.bar_obstacles)
        active_ids = [
            str(resolved.fact.id)
            for resolved in scheduler.facts
            if resolved.start_index - 1 <= position <= resolved.end_index + 1
        ]
        for fact_id in active_ids:
            frames_by_card[fact_id] += 1
            _accumulate_smart_geometry(
                accumulators[fact_id], geometry, fun_fact_config,
            )
    decisions = {
        fact_id: _decision_from_accumulator(fact_id, accumulator)
        for fact_id, accumulator in accumulators.items()
        if frames_by_card[fact_id] > 0
    }
    return SmartEditorialPlacementResolver(decisions, precompute_stats={
        "active_cards": len(decisions),
        "frames_analyzed": frames_analyzed,
        "frames_by_card": {
            fact_id: count
            for fact_id, count in frames_by_card.items()
            if count > 0
        },
        "obstacles_analyzed": obstacles_analyzed,
        "scene_geometry_objects_retained": 0,
        "smart_frame_geometry_constructions": frames_analyzed,
    })


def _new_card_accumulator(chart_config, config):
    safe_left, safe_top, safe_right, safe_bottom = editorial_safe_area(
        chart_config, config,
    )
    candidates = []
    for tie_index, mode in enumerate(SMART_CANDIDATE_ORDER):
        candidate_config = replace(
            config,
            editorial_placement_mode=mode,
            editorial_keep_inside_safe_area=True,
        )
        left, top, width, height = editorial_geometry(
            chart_config, candidate_config,
        )
        candidate = _Rect(left, top, width, height)
        outside = (
            max(0.0, safe_left - candidate.x)
            + max(0.0, safe_top - candidate.y)
            + max(0.0, candidate.right - safe_right)
            + max(0.0, candidate.bottom - safe_bottom)
        )
        candidates.append({
            "tie_index": tie_index,
            "mode": mode,
            "candidate": candidate,
            "left": candidate.x,
            "top": candidate.y,
            "right": candidate.right,
            "bottom": candidate.bottom,
            "outside": outside,
            "protected": 0.0,
            "bars": 0.0,
            "static": 0.0,
        })
    return candidates


def _accumulate_smart_geometry(accumulator, geometry, config):
    clearance = max(0, int(config.editorial_bar_clearance))
    protect_top_n = max(0, int(config.editorial_protect_top_n))
    visible = [
        (index, item)
        for index, item in enumerate(geometry.bar_obstacles)
        if item.opacity > 0.0
    ]
    protected_indices = {
        index
        for index, _ in sorted(
            visible,
            key=lambda pair: _rank_sort_value(pair[1].rank),
        )[:protect_top_n]
    }
    for index, item in visible:
        for component in item.components:
            _accumulate_rect_overlap(
                accumulator,
                component,
                "bars",
                protected=index in protected_indices,
                clearance=clearance,
            )
    for item in geometry.text_bounds:
        _accumulate_rect_overlap(accumulator, item, "static")


def _accumulate_rect_overlap(
    accumulator, obstacle, score_key, protected=False, clearance=0.0,
):
    clearance = float(clearance)
    obstacle_left = obstacle.x - clearance
    obstacle_top = obstacle.y - clearance
    obstacle_right = obstacle.right + clearance
    obstacle_bottom = obstacle.bottom + clearance
    # Candidates share three vertical bands.  Reject a whole band once, then
    # evaluate only its three horizontal positions (rather than all nine).
    for indices in ((0, 2, 3), (1, 4, 5), (6, 7, 8)):
        band = accumulator[indices[0]]
        if band["bottom"] <= obstacle_top or band["top"] >= obstacle_bottom:
            continue
        height = min(band["bottom"], obstacle_bottom) - max(
            band["top"], obstacle_top,
        )
        for index in indices:
            item = accumulator[index]
            width = min(item["right"], obstacle_right) - max(
                item["left"], obstacle_left,
            )
            if width <= 0.0:
                continue
            overlap = width * height
            item[score_key] += overlap
            if protected:
                item["protected"] += overlap


def _decision_from_accumulator(fact_id, accumulator):
    scored = []
    for item in accumulator:
        score = (
            item["outside"] * 1_000_000_000.0
            + item["protected"] * 1_000_000.0
            + item["bars"] * 100.0
            + item["static"] * 500.0
            + item["tie_index"] * 0.001
        )
        scored.append((score, item))
    score, selected = min(
        scored, key=lambda pair: (pair[0], pair[1]["tie_index"]),
    )
    return SmartPlacementDecision(
        fact_id=fact_id,
        position=(
            int(selected["candidate"].x),
            int(selected["candidate"].y),
        ),
        candidate=selected["mode"],
        score=score,
        protected_overlap=selected["protected"],
        used_fallback=all(item["protected"] > 0 for item in accumulator),
    )


def _iter_effective_smart_geometry(
    *, chart_config, fun_fact_config, scheduler, periods, sprites_by_period,
    source_label, calendar_resolver, scale_resolver, logo_availability,
):
    motion = MotionEngine(chart_config.animation)
    text_bounds_cache = {}
    frame_id = 0
    if len(periods) == 1:
        period = periods[0]
        position = scheduler.timeline.get_period_index(period)
        if not _is_relevant_timeline_position(scheduler, position):
            return
        sprites = sprites_by_period[period]
        scale = scale_resolver.for_sprites(sprites, frame_index=0)
        scene = Scene(
            title=chart_config.title,
            subtitle=scheduler.timeline.get_time_label(period),
            time_label=scheduler.timeline.get_time_label(period),
            display_calendar=(
                calendar_resolver.state_at(0)
                if calendar_resolver is not None else None
            ),
            source_label=source_label,
            bars=scale_bar_sprites(sprites, scale),
            frame_index=0,
            bar_value_scale=scale,
        )
        text_bounds = _cached_smart_text_bounds(
            text_bounds_cache, chart_config, fun_fact_config, scene,
        )
        yield 0, position, build_smart_scene_geometry(
            chart_config,
            fun_fact_config,
            scene,
            logo_availability=logo_availability,
            text_bounds=text_bounds,
        )
        return
    for index, (period_a, period_b) in enumerate(zip(periods, periods[1:])):
        transition_start = scheduler.timeline.get_period_index(period_a)
        transition_end = scheduler.timeline.get_period_index(period_b)
        if not any(
            resolved.start_index - 1 <= transition_end
            and resolved.end_index + 1 >= transition_start
            for resolved in scheduler.facts
        ):
            frame_id += (
                chart_config.steps_per_transition + (1 if index == 0 else 0)
                if chart_config.animation.continuous_motion
                else chart_config.steps_per_transition
            )
            continue
        start = sprites_by_period[period_a]
        end = sprites_by_period[period_b]
        label_a = scheduler.timeline.get_time_label(period_a)
        label_b = scheduler.timeline.get_time_label(period_b)
        subtitle = f"{label_a} -> {label_b}"
        if chart_config.animation.continuous_motion:
            previous = periods[index - 1] if index > 0 else period_a
            following = (
                periods[index + 2]
                if index + 2 < len(periods) else period_b
            )
            include_start = index == 0
            frames = motion.interpolate_sprites_continuous(
                sprites_by_period[previous], start, end,
                sprites_by_period[following],
                steps=chart_config.steps_per_transition,
                include_start=include_start,
            )
        else:
            include_start = True
            frames = motion.interpolate_sprites(
                start, end, steps=chart_config.steps_per_transition,
            )
        for step_index, sprites in enumerate(frames):
            if chart_config.animation.continuous_motion:
                progress = (
                    step_index if include_start else step_index + 1
                ) / chart_config.steps_per_transition
            else:
                progress = (
                    step_index / (len(frames) - 1)
                    if len(frames) > 1 else 1.0
                )
            position = scheduler.timeline.get_timeline_position(
                period_a, period_b=period_b, progress=progress,
            )
            if not _is_relevant_timeline_position(scheduler, position):
                frame_id += 1
                continue
            scale = scale_resolver.for_sprites(sprites, frame_index=frame_id)
            time_label = label_a if progress <= 0.5 else label_b
            scene = Scene(
                title=chart_config.title,
                subtitle=subtitle,
                time_label=time_label,
                display_calendar=(
                    calendar_resolver.state_at(frame_id)
                    if calendar_resolver is not None else None
                ),
                source_label=source_label,
                bars=scale_bar_sprites(sprites, scale),
                frame_index=frame_id,
                bar_value_scale=scale,
            )
            text_bounds = _cached_smart_text_bounds(
                text_bounds_cache,
                chart_config,
                fun_fact_config,
                scene,
            )
            yield frame_id, position, build_smart_scene_geometry(
                chart_config,
                fun_fact_config,
                scene,
                logo_availability=logo_availability,
                text_bounds=text_bounds,
            )
            frame_id += 1


def _cached_smart_text_bounds(
    cache, chart_config, fun_fact_config, scene,
):
    key = (
        str(scene.title or ""),
        str(scene.subtitle or ""),
        str(scene.time_label or ""),
        scene.display_calendar is not None,
        str(scene.source_label or ""),
    )
    bounds = cache.get(key)
    if bounds is None:
        bounds = build_smart_text_bounds(
            chart_config, fun_fact_config, scene,
        )
        cache[key] = bounds
    return bounds


def _resolve_window(chart_config, config, fact_id, geometries):
    protected = []
    bars = []
    static = []
    clearance = max(0, int(config.editorial_bar_clearance))
    protect_top_n = max(0, int(config.editorial_protect_top_n))
    for geometry in geometries:
        structured = geometry.get("bar_obstacles")
        if structured is not None:
            visible = [
                (index, item)
                for index, item in enumerate(structured)
                if float(item.get("opacity", 1.0)) > 0.0
            ]
            protected_indices = {
                index
                for index, _ in sorted(
                    visible,
                    key=lambda pair: _rank_sort_value(pair[1].get("rank")),
                )[:protect_top_n]
            }
            for index, item in visible:
                components = [
                    item.get("bar"),
                    item.get("category_text"),
                    item.get("value_text"),
                    *item.get("primary_logos", ()),
                    *item.get("secondary_logos", ()),
                ]
                for component in components:
                    if not component:
                        continue
                    expanded = _expanded(_rect(component), clearance)
                    bars.append(expanded)
                    if index in protected_indices:
                        protected.append(expanded)
            text = geometry.get("text_bounds", {})
            for name in ("date", "source", "title", "subtitle"):
                item = text.get(name)
                if item:
                    static.append(_rect(item))
            continue
        bar_rects = tuple(_rect(item) for item in geometry.get("bar_rects", ()))
        category_lane = _rect(geometry.get("category_lane"))
        rank_lane = _rect(geometry.get("ranking_lane"))
        canvas = _rect(geometry.get("canvas"))
        for index, bar in enumerate(bar_rects):
            left = min(bar.x, category_lane.x, rank_lane.x)
            right = min(canvas.right, bar.right)
            visual = _Rect(left, bar.y, max(0.0, right - left), bar.height)
            expanded = _expanded(visual, clearance)
            bars.append(expanded)
            if index < protect_top_n:
                protected.append(expanded)
        for key in ("primary_logo_rects", "secondary_logo_rects"):
            bars.extend(
                _expanded(_rect(item), clearance)
                for item in geometry.get(key, ())
            )
        text = geometry.get("text_bounds", {})
        for name in ("date", "source", "title", "subtitle"):
            item = text.get(name)
            if item:
                static.append(_rect(item))

    candidates = []
    safe_left, safe_top, safe_right, safe_bottom = editorial_safe_area(
        chart_config,
        config,
    )
    for tie_index, mode in enumerate(SMART_CANDIDATE_ORDER):
        candidate_config = replace(
            config,
            editorial_placement_mode=mode,
            editorial_keep_inside_safe_area=True,
        )
        left, top, width, height = editorial_geometry(
            chart_config,
            candidate_config,
        )
        candidate = _Rect(left, top, width, height)
        outside = (
            max(0.0, safe_left - candidate.x)
            + max(0.0, safe_top - candidate.y)
            + max(0.0, candidate.right - safe_right)
            + max(0.0, candidate.bottom - safe_bottom)
        )
        protected_overlap = sum(_intersection_area(candidate, item) for item in protected)
        bar_overlap = sum(_intersection_area(candidate, item) for item in bars)
        static_overlap = sum(_intersection_area(candidate, item) for item in static)
        score = (
            outside * 1_000_000_000.0
            + protected_overlap * 1_000_000.0
            + bar_overlap * 100.0
            + static_overlap * 500.0
            + tie_index * 0.001
        )
        candidates.append((score, tie_index, mode, candidate, protected_overlap))
    score, _, mode, candidate, protected_overlap = min(candidates)
    no_protected_free_candidate = all(item[4] > 0 for item in candidates)
    return SmartPlacementDecision(
        fact_id=fact_id,
        position=(int(candidate.x), int(candidate.y)),
        candidate=mode,
        score=score,
        protected_overlap=protected_overlap,
        used_fallback=no_protected_free_candidate,
    )


def _effective_frame_geometry(
    *,
    chart_config,
    fun_fact_config,
    scheduler,
    periods,
    sprites_by_period,
    source_label,
    calendar_resolver,
    scale_resolver,
):
    motion = MotionEngine(chart_config.animation)
    geometry = {}
    frame_id = 0
    if len(periods) == 1:
        period = periods[0]
        sprites = sprites_by_period[period]
        scale = scale_resolver.for_sprites(sprites, frame_index=0)
        scene = Scene(
            title=chart_config.title,
            subtitle=scheduler.timeline.get_time_label(period),
            time_label=scheduler.timeline.get_time_label(period),
            display_calendar=(
                calendar_resolver.state_at(0)
                if calendar_resolver is not None
                else None
            ),
            source_label=source_label,
            bars=scale_bar_sprites(sprites, scale),
            frame_index=0,
            bar_value_scale=scale,
        )
        position = scheduler.timeline.get_period_index(period)
        if not _is_relevant_timeline_position(scheduler, position):
            return geometry
        geometry[(0, position)] = build_scene_geometry(
            chart_config,
            fun_fact_config,
            scene,
        )
        return geometry
    for index, (period_a, period_b) in enumerate(zip(periods, periods[1:])):
        start = sprites_by_period[period_a]
        end = sprites_by_period[period_b]
        if chart_config.animation.continuous_motion:
            previous = periods[index - 1] if index > 0 else period_a
            following = periods[index + 2] if index + 2 < len(periods) else period_b
            include_start = index == 0
            frames = motion.interpolate_sprites_continuous(
                sprites_by_period[previous],
                start,
                end,
                sprites_by_period[following],
                steps=chart_config.steps_per_transition,
                include_start=include_start,
            )
        else:
            include_start = True
            frames = motion.interpolate_sprites(
                start,
                end,
                steps=chart_config.steps_per_transition,
            )
        for step_index, sprites in enumerate(frames):
            if chart_config.animation.continuous_motion:
                progress = (
                    step_index if include_start else step_index + 1
                ) / chart_config.steps_per_transition
            else:
                progress = (
                    step_index / (len(frames) - 1)
                    if len(frames) > 1
                    else 1.0
                )
            timeline_position = scheduler.timeline.get_timeline_position(
                period_a,
                period_b=period_b,
                progress=progress,
            )
            if not _is_relevant_timeline_position(
                scheduler, timeline_position,
            ):
                frame_id += 1
                continue
            scale = scale_resolver.for_sprites(
                sprites,
                frame_index=frame_id,
            )
            scaled = scale_bar_sprites(sprites, scale)
            display_period = period_a + ((period_b - period_a) * progress)
            scene = Scene(
                title=chart_config.title,
                subtitle=(
                    f"{scheduler.timeline.get_time_label(period_a)} -> "
                    f"{scheduler.timeline.get_time_label(period_b)}"
                ),
                time_label=scheduler.timeline.get_time_label(display_period),
                display_calendar=(
                    calendar_resolver.state_at(frame_id)
                    if calendar_resolver is not None
                    else None
                ),
                source_label=source_label,
                bars=scaled,
                frame_index=frame_id,
                bar_value_scale=scale,
            )
            geometry[(frame_id, timeline_position)] = build_scene_geometry(
                chart_config,
                fun_fact_config,
                scene,
            )
            frame_id += 1
    return geometry


def _timeline_position(index):
    if isinstance(index, tuple) and len(index) >= 2:
        return float(index[1])
    return float(index)


def _is_relevant_timeline_position(scheduler, position):
    return any(
        resolved.start_index - 1 <= position <= resolved.end_index + 1
        for resolved in scheduler.facts
    )


def _rank_sort_value(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("inf")


def _rect(value):
    if hasattr(value, "x"):
        return _Rect(
            round(float(value.x), 3),
            round(float(value.y), 3),
            max(0.0, round(float(value.width), 3)),
            max(0.0, round(float(value.height), 3)),
        )
    value = value or {}
    return _Rect(
        float(value.get("x", 0.0)),
        float(value.get("y", 0.0)),
        max(0.0, float(value.get("width", 0.0))),
        max(0.0, float(value.get("height", 0.0))),
    )


def _expanded(rect, amount):
    amount = max(0.0, float(amount))
    return _Rect(
        rect.x - amount,
        rect.y - amount,
        rect.width + (amount * 2),
        rect.height + (amount * 2),
    )


def _intersection_area(first, second):
    width = max(0.0, min(first.right, second.right) - max(first.x, second.x))
    height = max(0.0, min(first.bottom, second.bottom) - max(first.y, second.y))
    return width * height
