from dataclasses import dataclass, replace
from math import isfinite

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
    frame_count: int

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
        legacy_scale = not start_bars_at_zero and full_width_point == 1.0
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
        duration = estimate_video_duration(
            period_count=len(sprite_sets),
            steps_per_transition=config.steps_per_transition,
            fps=config.fps,
            continuous_motion=config.animation.continuous_motion,
        )
        return cls(
            origin_x=float(config.left_margin),
            domain_max=reference_value,
            fallback_width=max(0.0, float(config.max_bar_width)),
            project_max=project_max,
            start_bars_at_zero=start_bars_at_zero,
            full_width_point=full_width_point,
            frame_count=duration.frame_count,
        )

    def for_sprites(self, sprites, *, frame_index=0, timeline_progress=None):
        if timeline_progress is None:
            timeline_progress = normalized_effective_timeline_progress(
                frame_index,
                self.frame_count,
            )
        else:
            timeline_progress = _unit_interval(timeline_progress, default=0.0)
        growth_envelope = progressive_growth_envelope(
            timeline_progress,
            self.full_width_point,
            enabled=self.start_bars_at_zero,
        )
        return BarValueScale(
            origin_x=self.origin_x,
            width=structural_bar_width(
                sprites,
                fallback_width=self.fallback_width,
            ),
            domain_max=self.domain_max,
            timeline_progress=timeline_progress,
            growth_envelope=growth_envelope,
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


def scale_bar_sprites(sprites, scale):
    return [
        replace(
            sprite,
            x=scale.origin_x,
            width=scale.width_for_value(sprite.value),
        )
        for sprite in sprites
    ]


def _visible_positive_value(sprite):
    value = _finite(getattr(sprite, "value", None), default=None)
    opacity = _finite(getattr(sprite, "opacity", 1.0), default=0.0)
    if value is None or value <= 0.0 or opacity <= 0.0:
        return None
    return value


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


def _sprites_at_effective_progress(config, sprite_sets, progress):
    if not sprite_sets:
        return ()
    if len(sprite_sets) == 1:
        return sprite_sets[0]

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
