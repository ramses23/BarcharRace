from dataclasses import dataclass, replace
from time import perf_counter
from types import MappingProxyType

from core.bar_value_scale import BarValueScaleResolver, scale_bar_sprites
from core.motion_engine import MotionEngine
from core.scene_geometry import build_scene_geometry
from models.scene import Scene
from studio.fun_fact_layout import editorial_geometry, editorial_safe_area


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
    started_at = perf_counter()
    periods = tuple(periods)
    scale_resolver = BarValueScaleResolver.from_config(
        chart_config,
        (sprites_by_period[period] for period in periods),
    )
    geometry = _effective_frame_geometry(
        chart_config=chart_config,
        fun_fact_config=fun_fact_config,
        scheduler=scheduler,
        periods=periods,
        sprites_by_period=sprites_by_period,
        source_label=source_label,
        calendar_resolver=calendar_resolver,
        scale_resolver=scale_resolver,
    )
    resolver = SmartEditorialPlacementResolver.from_geometry(
        chart_config,
        fun_fact_config,
        scheduler,
        geometry,
    )
    resolver = SmartEditorialPlacementResolver(
        resolver._decisions,
        precompute_stats={
            **resolver.precompute_stats,
            "precompute_seconds": perf_counter() - started_at,
        },
    )
    scheduler.set_placement_resolver(resolver)
    return resolver


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
