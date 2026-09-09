"""Deterministic timing only: never changes checkpoint or interpolated values."""

from bisect import bisect_left
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING
from fractions import Fraction
from itertools import accumulate
from math import isfinite


@dataclass(frozen=True)
class TransitionActivity:
    score: float
    changed_bars: int
    relevant_bars: int
    value_activity: float
    magnitude: float
    rank_activity: float


def transition_activity(start, end):
    """Equal-weight mean of three unit-independent components in [0, 1].

    Use the union of effective visible endpoints. Missing bars have value zero
    and rank just below the union (entry/exit counts as rank activity). Magnitude
    is L1 change / L1 endpoint mass; rank is mean normalized displacement.
    Endpoint order is the effective ranking, not alphabetical name order.
    """
    a = {bar.name: (float(bar.value), i) for i, bar in enumerate(start)}
    b = {bar.name: (float(bar.value), i) for i, bar in enumerate(end)}
    names = sorted(a.keys() | b.keys())
    n = len(names)
    if not n:
        return TransitionActivity(0.0, 0, 0, 0.0, 0.0, 0.0)
    pairs = [(a.get(name, (0.0, n)), b.get(name, (0.0, n))) for name in names]
    if any(not isfinite(v) for pair in pairs for v, _ in pair):
        raise ValueError("Activity timing requires finite endpoint values.")
    changed = sum(x[0] != y[0] for x, y in pairs)
    # Scale before summation to avoid overflowing for large numeric units.
    scale = max(abs(v) for pair in pairs for v, _ in pair)
    mass = sum(abs(x[0] / scale) + abs(y[0] / scale) for x, y in pairs) if scale else 0
    magnitude = sum(abs(y[0] / scale - x[0] / scale) for x, y in pairs) / mass if mass else 0.0
    rank = sum(abs(y[1] - x[1]) for x, y in pairs) / (n * n)
    value = changed / n
    return TransitionActivity((value + magnitude + rank) / 3, changed, n, value, magnitude, rank)


def minimum_transition_frames(seconds, fps):
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0.5 <= seconds <= 2.0:
        raise ValueError("Minimum transition duration must be from 0.5 to 2.0 seconds.")
    if isinstance(fps, bool) or not isfinite(fps) or fps <= 0:
        raise ValueError("FPS must be positive and finite.")
    # Ceiling guarantees AT LEAST the requested duration, including fractional FPS.
    return int((Decimal(str(seconds)) * Decimal(str(fps))).to_integral_value(rounding=ROUND_CEILING))


def allocate_transition_steps(scores, uniform_steps, minimum_frames):
    """Hamilton allocation, exact rational quotas, stable index tie-breaking."""
    scores = tuple(scores)
    if type(uniform_steps) is not int or uniform_steps < 1 or type(minimum_frames) is not int or minimum_frames < 1:
        raise ValueError("Transition frame budgets must be positive integers.")
    if minimum_frames > uniform_steps:
        raise ValueError(
            f"Minimum transition duration requires {minimum_frames} frames per transition, "
            f"but the average frame budget is only {uniform_steps}. Increase Steps or reduce the minimum."
        )
    if any(not isfinite(s) or s < 0 for s in scores):
        raise ValueError("Activity scores must be finite and non-negative.")
    weights = tuple(Fraction(s) for s in scores)
    total = sum(weights)
    if not total:
        return (uniform_steps,) * len(scores)
    remaining = len(scores) * (uniform_steps - minimum_frames)
    quotas = tuple(remaining * w / total for w in weights)
    floors = [q.numerator // q.denominator for q in quotas]
    residual = remaining - sum(floors)
    order = sorted(range(len(scores)), key=lambda i: (-(quotas[i] - floors[i]), i))
    for i in order[:residual]:
        floors[i] += 1
    return tuple(minimum_frames + f for f in floors)


@dataclass(frozen=True)
class TransitionTimingPlan:
    steps_per_transition: tuple[int, ...]
    continuous_motion: bool
    activities: tuple[TransitionActivity, ...] = ()
    prefix_offsets: tuple[int, ...] = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "steps_per_transition", tuple(self.steps_per_transition))
        if any(type(s) is not int or s < 1 for s in self.steps_per_transition):
            raise ValueError("Transition steps must be positive integers.")
        object.__setattr__(self, "prefix_offsets", (0, *accumulate(self.steps_per_transition)))

    @property
    def total_transition_frames(self):
        return self.prefix_offsets[-1]

    @property
    def frame_count(self):
        return max(1, self.total_transition_frames + int(self.continuous_motion))

    def frame_bounds(self, index):
        """Owned global [start, end); continuous shared endpoint belongs to prior transition."""
        return (self.prefix_offsets[index] + int(self.continuous_motion and index > 0),
                self.prefix_offsets[index + 1] + int(self.continuous_motion))

    def progress(self, index, local_step):
        steps = self.steps_per_transition[index]
        if self.continuous_motion:
            return (local_step + int(index > 0)) / steps
        return local_step / (steps - 1) if steps > 1 else 1.0

    def locate(self, global_frame):
        if type(global_frame) is not int or not 0 <= global_frame < self.frame_count or not self.steps_per_transition:
            raise ValueError("Global frame is outside the transition timing plan.")
        target = global_frame if self.continuous_motion else global_frame + 1
        index = max(0, bisect_left(self.prefix_offsets, target) - 1)
        local = global_frame - self.frame_bounds(index)[0]
        return index, local, self.progress(index, local)

    def frame_at_progress(self, index, progress):
        span = self.steps_per_transition[index] - int(not self.continuous_motion)
        return self.prefix_offsets[index] + round(max(0.0, min(1.0, progress)) * span)


def build_transition_timing_plan(chart_config, sprite_sets):
    endpoints = tuple(tuple(s) for s in sprite_sets)
    n = max(0, len(endpoints) - 1)
    animation = chart_config.animation
    steps = max(1, int(chart_config.steps_per_transition))
    if animation.transition_duration_mode == "uniform":
        return TransitionTimingPlan((steps,) * n, animation.continuous_motion)
    activities = tuple(transition_activity(a, b) for a, b in zip(endpoints, endpoints[1:]))
    minimum = minimum_transition_frames(animation.minimum_transition_duration_seconds, chart_config.fps)
    allocated = allocate_transition_steps((a.score for a in activities), steps, minimum)
    return TransitionTimingPlan(allocated, animation.continuous_motion, activities)


def timing_plan_from_timeline(chart_config, timeline, periods):
    """Use production selection/visibility without constructing raster geometry."""
    from core.bar_selector import BarSelector
    from core.layout_engine import LayoutEngine

    periods = tuple(periods)
    if chart_config.animation.transition_duration_mode == "uniform":
        return TransitionTimingPlan((chart_config.steps_per_transition,) * max(0, len(periods) - 1), chart_config.animation.continuous_motion)
    selector = BarSelector(chart_config.selection)
    layout = LayoutEngine(chart_config)
    return build_transition_timing_plan(chart_config, (
        layout.select_visible_bars(selector.select(timeline.get_frame(p))) for p in periods
    ))


def sample_timed_sprites(motion, sprite_sets, plan, global_frame):
    """Resolve one global frame, including continuous checkpoint ownership."""
    index, _, raw_t = plan.locate(global_frame)
    start, end = sprite_sets[index:index + 2]
    if plan.continuous_motion:
        return motion.interpolate_sprites_continuous_at(
            sprite_sets[max(0, index - 1)], start, end,
            sprite_sets[min(len(sprite_sets) - 1, index + 2)], raw_t,
        )
    return motion.interpolate_sprites_at(start, end, raw_t)
