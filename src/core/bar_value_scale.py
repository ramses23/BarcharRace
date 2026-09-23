from dataclasses import dataclass, field, replace
from math import isfinite, sqrt

from core.motion_engine import MotionEngine
from models.bar_value_scale import BarValueScale
from utils.video_duration import estimate_video_duration


MIN_BAR_DOMAIN = 1.0


@dataclass(frozen=True)
class BarValueScaleResolver:
    """Resolve a stable bar domain against per-frame structural race width."""

    origin_x: float
    domain_max: float
    fallback_width: float
    project_max: float
    start_bars_at_zero: bool
    full_width_point: float
    initial_leader_occupancy: float
    legacy_mode: bool
    frame_count: int
    expanding_axis: bool = False
    leader_history: tuple = ()
    timing_plan: object = None
    display_timeline: object = field(default=None, compare=False, repr=False)

    @classmethod
    def from_config(cls, config, sprite_sets):
        sprite_sets = tuple(tuple(sprites) for sprites in sprite_sets)
        global_max = max(
            (
                value
                for sprites in sprite_sets
                for sprite in sprites
                if (value := _visible_positive_value(sprite)) is not None
            ),
            default=0.0,
        )
        project_max = max(MIN_BAR_DOMAIN, global_max)
        configured_point = _valid_full_width_point(
            getattr(config, "leader_full_width_point", 1.0)
        )
        full_width_point = configured_point or 1.0
        start_bars_at_zero = bool(
            getattr(config, "start_bars_at_zero", False)
        )
        legacy_scale = not progressive_bar_scale_active(config)
        reference_value = project_max
        if not legacy_scale and configured_point is not None:
            sampled_sprites = _sprites_at_effective_progress(
                config,
                sprite_sets,
                full_width_point,
            )
            sampled_leader = max(
                (
                    value
                    for sprite in sampled_sprites
                    if (value := _visible_positive_value(sprite)) is not None
                ),
                default=0.0,
            )
            if sampled_leader > 0.0 and isfinite(sampled_leader):
                reference_value = sampled_leader
        initial_leader = _leader_value(sprite_sets[0] if sprite_sets else ())
        initial_leader_occupancy = (
            1.0
            if legacy_scale
            else _safe_ratio(initial_leader, reference_value)
        )
        duration = estimate_video_duration(
            period_count=len(sprite_sets),
            steps_per_transition=config.steps_per_transition,
            fps=config.fps,
            continuous_motion=config.animation.continuous_motion,
        )
        expanding_axis = config.value_grid_enabled and config.value_grid_mode == "dynamic"
        leader_history, timing_plan = (), None
        fallback_width = max(0.0, float(config.max_bar_width))
        if expanding_axis:
            from itertools import accumulate
            from core.transition_timing import build_transition_timing_plan, sample_timed_sprites
            from core.opening_intro import opening_intro_frames
            leader_history = tuple(accumulate((_leader_value(s) for s in sprite_sets), max))
            timing_plan = build_transition_timing_plan(config, sprite_sets)
            if sprite_sets:
                # The chosen percentage belongs to the effective output timeline,
                # including its opening, but never to a partial-render window.
                intro = opening_intro_frames(config)
                target = round(full_width_point * (timing_plan.frame_count + intro - 1)) - intro
                reference_sprites = (sample_timed_sprites(
                    MotionEngine(config.animation), sprite_sets, timing_plan,
                    min(timing_plan.frame_count - 1, target))
                    if target >= 0 and timing_plan.steps_per_transition else sprite_sets[0])
                reference_value = max(MIN_BAR_DOMAIN, _leader_value(reference_sprites))
            widths = [structural_bar_width(s, fallback_width=fallback_width) for s in sprite_sets]
            fallback_width = min((w for w in widths if w > 0), default=fallback_width)
        from core.display_timeline import DisplayTimeline
        display_timeline = DisplayTimeline(config, sprite_sets, reference_value,
                                           project_max, fallback_width)
        return cls(
            origin_x=float(config.left_margin),
            domain_max=reference_value,
            fallback_width=fallback_width,
            project_max=project_max,
            start_bars_at_zero=start_bars_at_zero,
            full_width_point=full_width_point,
            initial_leader_occupancy=initial_leader_occupancy,
            legacy_mode=legacy_scale,
            frame_count=duration.frame_count,
            expanding_axis=expanding_axis,
            leader_history=leader_history,
            timing_plan=timing_plan,
            display_timeline=display_timeline,
        )

    def for_sprites(self, sprites, *, frame_index=0, timeline_progress=None):
        if timeline_progress is None:
            timeline_progress = normalized_effective_timeline_progress(
                frame_index,
                self.frame_count,
            )
        else:
            timeline_progress = _unit_interval(timeline_progress, default=0.0)
        current_leader_value = _leader_value(sprites)
        if self.legacy_mode:
            # Preserve ba2914a exactly: values remain divided by the fixed
            # project maximum and no progressive multiplier is applied.
            scale_domain = self.project_max
            width_multiplier = 1.0
            leader_occupancy = _safe_ratio(
                current_leader_value,
                self.project_max,
            )
        else:
            # Progressive mode separates the leader's temporal occupancy from
            # every category's value ratio against that same frame leader.
            scale_domain = (
                current_leader_value
                if current_leader_value > 0.0
                else self.domain_max
            )
            leader_occupancy = progressive_leader_occupancy(
                timeline_progress,
                self.full_width_point,
                start_bars_at_zero=self.start_bars_at_zero,
                initial_occupancy=self.initial_leader_occupancy,
            )
            width_multiplier = leader_occupancy
        width = structural_bar_width(sprites, fallback_width=self.fallback_width)
        if self.expanding_axis:
            frame = round(timeline_progress * max(0, self.frame_count - 1))
            index = (self.timing_plan.locate(frame)[0]
                     if self.timing_plan.steps_per_transition else 0)
            history = self.leader_history[index] if self.leader_history else 0.0
            record = max(MIN_BAR_DOMAIN, history, current_leader_value)
            # Before the reference, domain grows slower than values: both the
            # bar's occupancy and the grid's leftward compression can increase.
            # At the reference occupancy reaches 100%; thereafter follow records.
            scale_domain = max(record, sqrt(self.domain_max) * sqrt(record))
            width_multiplier = 1.0
            width = self.fallback_width
            leader_occupancy = current_leader_value / scale_domain
        display_ranks, display_ticks = (None, None)
        if self.display_timeline is not None:
            display_ranks, display_ticks = self.display_timeline.at(
                round(timeline_progress * max(0, self.frame_count - 1)))
        return BarValueScale(
            origin_x=self.origin_x,
            width=width,
            domain_max=scale_domain,
            timeline_progress=timeline_progress,
            growth_envelope=width_multiplier,
            leader_occupancy=leader_occupancy,
            tick_label_domain=self.project_max if self.expanding_axis else None,
            display_ranks=display_ranks,
            display_ticks=display_ticks,
        )


def normalized_effective_timeline_progress(frame_index, frame_count):
    try:
        frame_index = int(frame_index)
        frame_count = int(frame_count)
    except (TypeError, ValueError):
        return 0.0
    if frame_count <= 1:
        return 0.0
    return max(0.0, min(1.0, frame_index / (frame_count - 1)))


def progressive_bar_scale_active(config):
    point = _valid_full_width_point(
        getattr(config, "leader_full_width_point", 1.0)
    )
    point = point or 1.0
    return bool(getattr(config, "start_bars_at_zero", False)) or point < 1.0


def progressive_growth_envelope(progress, full_width_point, *, enabled):
    if not enabled:
        return 1.0
    progress = _unit_interval(progress, default=0.0)
    point = _valid_full_width_point(full_width_point)
    if point is None:
        point = 1.0
    x = max(0.0, min(1.0, progress / point))
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return x * x * (3.0 - (2.0 * x))


def progressive_leader_occupancy(
    progress,
    full_width_point,
    *,
    start_bars_at_zero,
    initial_occupancy,
):
    growth = progressive_growth_envelope(
        progress,
        full_width_point,
        enabled=True,
    )
    if start_bars_at_zero:
        return growth
    initial_occupancy = _unit_interval(initial_occupancy, default=0.0)
    return initial_occupancy + ((1.0 - initial_occupancy) * growth)


def structural_bar_width(sprites, *, fallback_width):
    """Read the structural race width carried through layout and motion."""

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
        return max(structural_widths)

    # Compatibility fallback for manually constructed or legacy sprites.
    widths = [
        max(0.0, float(sprite.width))
        for sprite in sprites
        if _visible_positive_value(sprite) is not None
    ]
    return max(widths) if widths else max(0.0, float(fallback_width))


def scale_bar_sprites(sprites, scale, config=None):
    scaled = [
        replace(
            sprite,
            x=scale.origin_x,
            width=scale.width_for_value(sprite.value),
        )
        for sprite in sprites
    ]
    if config is not None:
        from core.value_ranking import position_bars_by_value
        ranks = dict(scale.display_ranks) if scale.display_ranks is not None else None
        return position_bars_by_value(scaled, config, ranks)
    return scaled


def _visible_positive_value(sprite):
    value = _finite(getattr(sprite, "value", None), default=None)
    opacity = _finite(getattr(sprite, "opacity", 1.0), default=0.0)
    if value is None or value <= 0.0 or opacity <= 0.0:
        return None
    return value


def _leader_value(sprites):
    return max(
        (
            value
            for sprite in sprites
            if (value := _visible_positive_value(sprite)) is not None
        ),
        default=0.0,
    )


def _finite(value, *, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if isfinite(value) else default


def _valid_full_width_point(value):
    value = _finite(value, default=None)
    if value is None or value <= 0.0 or value > 1.0:
        return None
    return value


def _unit_interval(value, *, default):
    value = _finite(value, default=default)
    return max(0.0, min(1.0, value))


def _safe_ratio(numerator, denominator):
    numerator = _finite(numerator, default=0.0)
    denominator = _finite(denominator, default=0.0)
    if numerator <= 0.0 or denominator <= 0.0:
        return 0.0
    return max(0.0, min(1.0, numerator / denominator))


def _sprites_at_effective_progress(config, sprite_sets, progress):
    if not sprite_sets:
        return ()
    if len(sprite_sets) == 1:
        return sprite_sets[0]

    if config.animation.transition_duration_mode == "activity_weighted":
        from core.transition_timing import build_transition_timing_plan, sample_timed_sprites
        plan = build_transition_timing_plan(config, sprite_sets)
        frame = round(_unit_interval(progress, default=1.0) * (plan.frame_count - 1))
        return sample_timed_sprites(MotionEngine(config.animation), sprite_sets, plan, frame)

    transition_count = len(sprite_sets) - 1
    steps = max(1, int(config.steps_per_transition))
    duration = estimate_video_duration(
        period_count=len(sprite_sets),
        steps_per_transition=steps,
        fps=config.fps,
        continuous_motion=config.animation.continuous_motion,
    )
    frame_position = _unit_interval(progress, default=1.0) * max(
        0, duration.frame_count - 1
    )
    transition_index = min(
        transition_count - 1,
        max(0, int(frame_position // steps)),
    )
    local_frame = frame_position - (transition_index * steps)
    local_denominator = (
        steps
        if config.animation.continuous_motion
        else max(1, steps - 1)
    )
    local_progress = max(0.0, min(1.0, local_frame / local_denominator))
    if not config.animation.continuous_motion and steps == 1:
        # MotionEngine renders the sole non-continuous frame at raw_t=1.
        local_progress = 1.0
    motion = MotionEngine(animation_config=config.animation)
    start_sprites = sprite_sets[transition_index]
    end_sprites = sprite_sets[transition_index + 1]
    if not config.animation.continuous_motion:
        return motion.interpolate_sprites_at(
            start_sprites,
            end_sprites,
            local_progress,
        )

    previous_sprites = (
        sprite_sets[transition_index - 1]
        if transition_index > 0
        else start_sprites
    )
    next_sprites = (
        sprite_sets[transition_index + 2]
        if transition_index + 2 < len(sprite_sets)
        else end_sprites
    )
    return motion.interpolate_sprites_continuous_at(
        previous_sprites,
        start_sprites,
        end_sprites,
        next_sprites,
        local_progress,
    )
