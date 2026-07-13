from config.animation_config import AnimationConfig
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

                start_height = a.height if a else (b.height if b else 40)
                end_height = b.height if b else (a.height if a else 40)
                logo_path = a.logo_path if a else (b.logo_path if b else None)
                start_rank, end_rank = self._rank_bounds(a, b)
                start_opacity = self._sprite_opacity(a, fallback=0.0 if b else 1.0)
                end_opacity = self._sprite_opacity(b, fallback=0.0 if a else 1.0)
                rank = (
                    lerp(start_rank, end_rank, t)
                    if start_rank is not None and end_rank is not None
                    else None
                )

                frame.append(
                    BarSprite(
                        name=name,
                        value=lerp(start_val, end_val, value_t),
                        color=color,
                        x=lerp(start_x, end_x, t),
                        y=lerp(start_y, end_y, t),
                        width=lerp(start_width, end_width, t),
                        height=lerp(start_height, end_height, t),
                        rank=rank,
                        logo_path=logo_path,
                        opacity=lerp(start_opacity, end_opacity, t),
                    )
                )

            frame.sort(key=lambda sprite: (sprite.y, sprite.name))
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

            frame.sort(key=lambda sprite: (sprite.y, sprite.name))
            frames.append(frame)

        return frames

    def _continuous_sprite(self, previous, start, end, next_sprite, t):
        value_t = t if not self.animation_config.value_smoothing else None
        rank = self._continuous_optional(
            previous.rank,
            start.rank,
            end.rank,
            next_sprite.rank,
            t,
        )

        return BarSprite(
            name=start.name,
            value=(
                lerp(start.value, end.value, value_t)
                if value_t is not None
                else self._bounded_catmull_rom(
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
            y=self._bounded_catmull_rom(
                previous.y, start.y, end.y, next_sprite.y, t
            ),
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
            opacity=min(1.0, max(0.0, self._bounded_catmull_rom(
                previous.opacity,
                start.opacity,
                end.opacity,
                next_sprite.opacity,
                t,
            ))),
        )

    def _transition_sprite(self, name, start, end, raw_t):
        easing = self.animation_config.easing_function()
        t = easing(raw_t)
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
        start_height = start.height if start else end.height
        end_height = end.height if end else start.height
        start_rank, end_rank = self._rank_bounds(start, end)
        start_opacity = self._sprite_opacity(start, fallback=0.0 if end else 1.0)
        end_opacity = self._sprite_opacity(end, fallback=0.0 if start else 1.0)

        return BarSprite(
            name=name,
            value=lerp(start_val, end_val, value_t),
            color=color,
            x=lerp(start_x, end_x, t),
            y=lerp(start_y, end_y, t),
            width=lerp(start_width, end_width, t),
            height=lerp(start_height, end_height, t),
            rank=(
                lerp(start_rank, end_rank, t)
                if start_rank is not None and end_rank is not None
                else None
            ),
            logo_path=start.logo_path if start else end.logo_path,
            opacity=lerp(start_opacity, end_opacity, t),
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
