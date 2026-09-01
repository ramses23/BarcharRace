from math import isfinite

from config.animation_config import AnimationConfig
from core.rank_motion import (
    RANK_MOTION_STABLE,
    classify_rank_motion,
    rank_motion_sort_key,
)
from utils.interpolation import lerp
from models.bar_sprite import BarSprite


class MotionEngine:

    def __init__(self, animation_config=None):
        self.animation_config = animation_config or AnimationConfig()

    def interpolate_sprites(self, start_sprites, end_sprites, steps=30):
        start_map = {sprite.name: sprite for sprite in start_sprites}
        end_map = {sprite.name: sprite for sprite in end_sprites}
        easing = self.animation_config.easing_function()

        names = sorted(set(start_map) | set(end_map))

        frames = []

        for step in range(steps):
            raw_t = step / (steps - 1) if steps > 1 else 1
            t = easing(raw_t)
            rank_raw_t, rank_t = self._rank_progress(raw_t, easing)
            value_t = t if self.animation_config.value_smoothing else raw_t

            frame = []

            for name in names:
                a = start_map.get(name)
                b = end_map.get(name)

                start_val = a.value if a else 0
                end_val = b.value if b else 0
                color = (a.color if a else (b.color if b else "#999"))

                start_x = a.x if a else (b.x if b else 0)
                end_x = b.x if b else (a.x if a else 0)

                start_y = a.y if a else (b.y if b else 0)
                end_y = b.y if b else (a.y if a else 0)

                start_width = a.width if a else 0
                end_width = b.width if b else 0
                start_available_width = self._sprite_bar_available_width(a)
                end_available_width = self._sprite_bar_available_width(b)
                if start_available_width is None:
                    start_available_width = end_available_width
                if end_available_width is None:
                    end_available_width = start_available_width

                start_height = a.height if a else (b.height if b else 40)
                end_height = b.height if b else (a.height if a else 40)
                logo_path = a.logo_path if a else (b.logo_path if b else None)
                secondary_logo_path = (
                    a.secondary_logo_path
                    if a
                    else (b.secondary_logo_path if b else None)
                )
                start_rank, end_rank = self._rank_bounds(a, b)
                start_opacity = self._sprite_opacity(a, fallback=0.0 if b else 1.0)
                end_opacity = self._sprite_opacity(b, fallback=0.0 if a else 1.0)
                rank = (
                    lerp(start_rank, end_rank, rank_t)
                    if start_rank is not None and end_rank is not None
                    else None
                )
                rank_motion_state = self._active_rank_motion_state(
                    start_rank,
                    end_rank,
                    rank_raw_t,
                    start_present=a is not None,
                    end_present=b is not None,
                )

                frame.append(
                    BarSprite(
                        name=name,
                        value=lerp(start_val, end_val, value_t),
                        color=color,
                        x=lerp(start_x, end_x, t),
                        y=lerp(start_y, end_y, rank_t),
                        width=lerp(start_width, end_width, t),
                        height=lerp(start_height, end_height, t),
                        rank=rank,
                        logo_path=logo_path,
                        secondary_logo_path=secondary_logo_path,
                        opacity=lerp(start_opacity, end_opacity, t),
                        rank_motion_state=rank_motion_state,
                        rank_motion_progress=rank_raw_t,
                        rank_motion_target=(
                            None
                            if rank_motion_state == RANK_MOTION_STABLE
                            else end_rank
                        ),
                        bar_available_width=(
                            None
                            if start_available_width is None
                            else lerp(start_available_width, end_available_width, t)
                        ),
                    )
                )

            frame.sort(key=rank_motion_sort_key)
            frames.append(frame)

        return frames

    def interpolate_sprites_continuous(
        self,
        previous_sprites,
        start_sprites,
        end_sprites,
        next_sprites,
        steps=30,
        include_start=True,
    ):
        previous_map = {sprite.name: sprite for sprite in previous_sprites}
        start_map = {sprite.name: sprite for sprite in start_sprites}
        end_map = {sprite.name: sprite for sprite in end_sprites}
        next_map = {sprite.name: sprite for sprite in next_sprites}
        names = sorted(set(start_map) | set(end_map))
        first_step = 0 if include_start else 1
        sample_steps = range(first_step, max(1, steps) + 1)
        frames = []

        for step in sample_steps:
            raw_t = step / max(1, steps)
            frame = []

            for name in names:
                start = start_map.get(name)
                end = end_map.get(name)

                if start is not None and end is not None:
                    sprite = self._continuous_sprite(
                        previous_map.get(name) or start,
                        start,
                        end,
                        next_map.get(name) or end,
                        raw_t,
                    )
                else:
                    sprite = self._transition_sprite(name, start, end, raw_t)

                frame.append(sprite)

            frame.sort(key=rank_motion_sort_key)
            frames.append(frame)

        return frames

    def interpolate_sprites_at(self, start_sprites, end_sprites, progress):
        """Sample transition easing at one normalized transition position."""

        start_map = {sprite.name: sprite for sprite in start_sprites}
        end_map = {sprite.name: sprite for sprite in end_sprites}
        raw_t = self._clamped_progress(progress)
        frame = [
            self._transition_sprite(
                name,
                start_map.get(name),
                end_map.get(name),
                raw_t,
            )
            for name in sorted(set(start_map) | set(end_map))
        ]
        frame.sort(key=rank_motion_sort_key)
        return frame

    def interpolate_sprites_continuous_at(
        self,
        previous_sprites,
        start_sprites,
        end_sprites,
        next_sprites,
        progress,
    ):
        """Sample continuous motion at one normalized transition position."""

        previous_map = {sprite.name: sprite for sprite in previous_sprites}
        start_map = {sprite.name: sprite for sprite in start_sprites}
        end_map = {sprite.name: sprite for sprite in end_sprites}
        next_map = {sprite.name: sprite for sprite in next_sprites}
        raw_t = self._clamped_progress(progress)
        frame = []
        for name in sorted(set(start_map) | set(end_map)):
            start = start_map.get(name)
            end = end_map.get(name)
            if start is not None and end is not None:
                sprite = self._continuous_sprite(
                    previous_map.get(name) or start,
                    start,
                    end,
                    next_map.get(name) or end,
                    raw_t,
                )
            else:
                sprite = self._transition_sprite(name, start, end, raw_t)
            frame.append(sprite)
        frame.sort(key=rank_motion_sort_key)
        return frame

    def _continuous_sprite(self, previous, start, end, next_sprite, t):
        value_t = t if not self.animation_config.value_smoothing else None
        easing = self.animation_config.easing_function()
        rank_raw_t, rank_t = self._rank_progress(t, easing)
        start_rank, end_rank = self._rank_bounds(start, end)
        rank = (
            lerp(start_rank, end_rank, rank_t)
            if start_rank is not None and end_rank is not None
            else None
        )
        rank_motion_state = self._active_rank_motion_state(
            start_rank,
            end_rank,
            rank_raw_t,
        )

        return BarSprite(
            name=start.name,
            value=(
                lerp(start.value, end.value, value_t)
                if value_t is not None
                else self._monotone_cubic_value(
                    previous.value,
                    start.value,
                    end.value,
                    next_sprite.value,
                    t,
                )
            ),
            color=start.color,
            x=self._bounded_catmull_rom(
                previous.x, start.x, end.x, next_sprite.x, t
            ),
            # Ranking is a period-to-period contract. Interpolating Y from
            # neighboring periods with Catmull-Rom can flatten the beginning
            # or end of a swap and leave two rows visually attached. Use the
            # configured motion easing directly between the two row centers.
            y=lerp(start.y, end.y, rank_t),
            width=max(0.0, self._bounded_catmull_rom(
                previous.width,
                start.width,
                end.width,
                next_sprite.width,
                t,
            )),
            height=max(0.0, self._bounded_catmull_rom(
                previous.height,
                start.height,
                end.height,
                next_sprite.height,
                t,
            )),
            rank=rank,
            logo_path=start.logo_path or end.logo_path,
            secondary_logo_path=(
                start.secondary_logo_path or end.secondary_logo_path
            ),
            opacity=min(1.0, max(0.0, self._bounded_catmull_rom(
                previous.opacity,
                start.opacity,
                end.opacity,
                next_sprite.opacity,
                t,
            ))),
            rank_motion_state=rank_motion_state,
            rank_motion_progress=rank_raw_t,
            rank_motion_target=(
                None
                if rank_motion_state == RANK_MOTION_STABLE
                else end_rank
            ),
            bar_available_width=self._continuous_optional(
                self._sprite_bar_available_width(previous),
                self._sprite_bar_available_width(start),
                self._sprite_bar_available_width(end),
                self._sprite_bar_available_width(next_sprite),
                t,
            ),
        )

    def _transition_sprite(self, name, start, end, raw_t):
        easing = self.animation_config.easing_function()
        t = easing(raw_t)
        rank_raw_t, rank_t = self._rank_progress(raw_t, easing)
        value_t = t if self.animation_config.value_smoothing else raw_t
        start_val = start.value if start else 0
        end_val = end.value if end else 0
        color = start.color if start else end.color
        start_x = start.x if start else end.x
        end_x = end.x if end else start.x
        start_y = start.y if start else end.y
        end_y = end.y if end else start.y
        start_width = start.width if start else 0
        end_width = end.width if end else 0
        start_available_width = self._sprite_bar_available_width(start)
        end_available_width = self._sprite_bar_available_width(end)
        if start_available_width is None:
            start_available_width = end_available_width
        if end_available_width is None:
            end_available_width = start_available_width
        start_height = start.height if start else end.height
        end_height = end.height if end else start.height
        start_rank, end_rank = self._rank_bounds(start, end)
        start_opacity = self._sprite_opacity(start, fallback=0.0 if end else 1.0)
        end_opacity = self._sprite_opacity(end, fallback=0.0 if start else 1.0)
        rank_motion_state = self._active_rank_motion_state(
            start_rank,
            end_rank,
            rank_raw_t,
            start_present=start is not None,
            end_present=end is not None,
        )

        return BarSprite(
            name=name,
            value=lerp(start_val, end_val, value_t),
            color=color,
            x=lerp(start_x, end_x, t),
            y=lerp(start_y, end_y, rank_t),
            width=lerp(start_width, end_width, t),
            height=lerp(start_height, end_height, t),
            rank=(
                lerp(start_rank, end_rank, rank_t)
                if start_rank is not None and end_rank is not None
                else None
            ),
            logo_path=start.logo_path if start else end.logo_path,
            secondary_logo_path=(
                start.secondary_logo_path
                if start
                else end.secondary_logo_path
            ),
            opacity=lerp(start_opacity, end_opacity, t),
            rank_motion_state=rank_motion_state,
            rank_motion_progress=rank_raw_t,
            rank_motion_target=(
                None
                if rank_motion_state == RANK_MOTION_STABLE
                else end_rank
            ),
            bar_available_width=(
                None
                if start_available_width is None
                else lerp(start_available_width, end_available_width, t)
            ),
        )

    def _continuous_optional(self, p0, p1, p2, p3, t):
        if p1 is None and p2 is None:
            return None

        p1 = p2 if p1 is None else p1
        p2 = p1 if p2 is None else p2
        p0 = p1 if p0 is None else p0
        p3 = p2 if p3 is None else p3
        return self._bounded_catmull_rom(p0, p1, p2, p3, t)

    def _bounded_catmull_rom(self, p0, p1, p2, p3, t):
        value = 0.5 * (
            (2 * p1)
            + (-p0 + p2) * t
            + (2 * p0 - 5 * p1 + 4 * p2 - p3) * (t * t)
            + (-p0 + 3 * p1 - 3 * p2 + p3) * (t * t * t)
        )
        return min(max(p1, p2), max(min(p1, p2), value))

    def _monotone_cubic_value(self, p0, p1, p2, p3, t):
        """Interpolate p1 -> p2 with an equal-step PCHIP Hermite segment."""
        if t <= 0.0:
            return p1
        if t >= 1.0:
            return p2
        if p1 == p2:
            return p1

        points = tuple(float(value) for value in (p0, p1, p2, p3))
        if not all(isfinite(value) for value in points):
            return lerp(p1, p2, t)

        # Normalize before taking differences so very large finite values do
        # not overflow. PCHIP tangent ratios are invariant under this scale.
        scale = max(1.0, *(abs(value) for value in points))
        q0, q1, q2, q3 = (value / scale for value in points)
        d0 = q1 - q0
        d1 = q2 - q1
        d2 = q3 - q2
        if d1 == 0.0:
            return lerp(p1, p2, t)

        # For equal period spacing, PCHIP uses the harmonic mean of adjacent
        # secants. A sign change makes the shared-node tangent zero, which
        # preserves local extrema without an after-the-fact value clamp.
        m1 = self._pchip_tangent(d0, d1)
        m2 = self._pchip_tangent(d1, d2)
        alpha = m1 / d1
        beta = m2 / d1

        t2 = t * t
        t3 = t2 * t
        h10 = t3 - (2.0 * t2) + t
        h01 = (-2.0 * t3) + (3.0 * t2)
        h11 = t3 - t2
        progress = h01 + (h10 * alpha) + (h11 * beta)

        # Monotone PCHIP keeps progress in [0, 1]. Prefer the delta form to
        # retain tiny changes next to large baselines; use weighted endpoints
        # only when subtracting opposite extreme values would overflow.
        segment_delta = p2 - p1
        if isfinite(segment_delta):
            return p1 + (segment_delta * progress)
        return (p1 * (1.0 - progress)) + (p2 * progress)

    def _pchip_tangent(self, left_secant, right_secant):
        same_direction = (
            (left_secant > 0.0 and right_secant > 0.0)
            or (left_secant < 0.0 and right_secant < 0.0)
        )
        if not same_direction:
            return 0.0

        return (
            2.0 * left_secant * right_secant
            / (left_secant + right_secant)
        )

    def _rank_bounds(self, start_sprite, end_sprite):
        start_rank = self._sprite_rank(start_sprite)
        end_rank = self._sprite_rank(end_sprite)

        if start_rank is None and end_rank is None:
            return None, None

        if start_rank is None:
            start_rank = end_rank

        if end_rank is None:
            end_rank = start_rank

        return start_rank, end_rank

    def _sprite_rank(self, sprite):
        if sprite is None:
            return None

        return sprite.rank

    def _sprite_opacity(self, sprite, fallback):
        if sprite is not None:
            return sprite.opacity

        if self.animation_config.enter_exit:
            return fallback

        return 1.0

    def _sprite_bar_available_width(self, sprite):
        if sprite is None:
            return None
        return sprite.bar_available_width

    def _rank_progress(self, raw_t, easing):
        try:
            duration = float(self.animation_config.rank_movement_duration)
        except (TypeError, ValueError):
            duration = 1.0
        if not isfinite(duration):
            duration = 1.0
        duration = max(0.4, min(1.0, duration))
        rank_raw_t = max(0.0, min(1.0, float(raw_t) / duration))
        return rank_raw_t, easing(rank_raw_t)

    @staticmethod
    def _active_rank_motion_state(
        start_rank,
        end_rank,
        rank_raw_t,
        *,
        start_present=True,
        end_present=True,
    ):
        state = classify_rank_motion(
            start_rank,
            end_rank,
            start_present=start_present,
            end_present=end_present,
        )
        if rank_raw_t >= 1.0:
            return RANK_MOTION_STABLE
        return state

    @staticmethod
    def _clamped_progress(progress):
        try:
            progress = float(progress)
        except (TypeError, ValueError):
            return 0.0
        if not isfinite(progress):
            return 0.0
        return max(0.0, min(1.0, progress))
