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
                start_opacity = self._sprite_opacity(a, fallback=0.0 if b else 1.0)
                end_opacity = self._sprite_opacity(b, fallback=0.0 if a else 1.0)

                frame.append(
                    BarSprite(
                        name=name,
                        value=lerp(start_val, end_val, value_t),
                        color=color,
                        x=lerp(start_x, end_x, t),
                        y=lerp(start_y, end_y, t),
                        width=lerp(start_width, end_width, t),
                        height=lerp(start_height, end_height, t),
                        logo_path=logo_path,
                        opacity=lerp(start_opacity, end_opacity, t),
                    )
                )

            frames.append(frame)

        return frames

    def _sprite_opacity(self, sprite, fallback):
        if sprite is not None:
            return sprite.opacity

        if self.animation_config.enter_exit:
            return fallback

        return 1.0
