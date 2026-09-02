from dataclasses import dataclass, replace
from types import MappingProxyType

from core.bar_value_scale import BarValueScaleResolver, scale_bar_sprites
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

    def __init__(self, decisions):
        self._decisions = MappingProxyType(dict(decisions))

    def position_for(self, fact_id):
        decision = self._decisions.get(str(fact_id))
        return decision.position if decision is not None else None

    def decision_for(self, fact_id):
        return self._decisions.get(str(fact_id))

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
        for resolved in scheduler.facts:
            window = [
                geometry
                for index, geometry in sorted(geometry_by_timeline_index.items())
                if resolved.start_index - 1 <= index <= resolved.end_index + 1
            ]
            if not window:
                continue
            decisions[resolved.fact.id] = _resolve_window(
                chart_config,
                fun_fact_config,
                resolved.fact.id,
                window,
            )
        return cls(decisions)


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
    scale_resolver = BarValueScaleResolver.from_config(
        chart_config,
        (sprites_by_period[period] for period in periods),
    )
    geometry = {}
    for period_offset, period in enumerate(periods):
        frame_index = period_offset * chart_config.steps_per_transition
        sprites = sprites_by_period[period]
        scale = scale_resolver.for_sprites(sprites, frame_index=frame_index)
        scene = Scene(
            title=chart_config.title,
            subtitle=scheduler.timeline.get_time_label(period),
            time_label=scheduler.timeline.get_time_label(period),
            display_calendar=(
                calendar_resolver.state_at(frame_index)
                if calendar_resolver is not None
                else None
            ),
            source_label=source_label,
            bars=scale_bar_sprites(sprites, scale),
            frame_index=frame_index,
            bar_value_scale=scale,
        )
        timeline_index = scheduler.timeline.get_period_index(period)
        geometry[timeline_index] = build_scene_geometry(
            chart_config,
            fun_fact_config,
            scene,
        )
    resolver = SmartEditorialPlacementResolver.from_geometry(
        chart_config,
        fun_fact_config,
        scheduler,
        geometry,
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
        bar_rects = tuple(_rect(item) for item in geometry.get("bar_rects", ()))
        category_lane = _rect(geometry.get("category_lane"))
        rank_lane = _rect(geometry.get("ranking_lane"))
        canvas = _rect(geometry.get("canvas"))
        for index, bar in enumerate(bar_rects):
            left = min(bar.x, category_lane.x, rank_lane.x)
            right = min(canvas.right, max(bar.right + 160.0, bar.right))
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
