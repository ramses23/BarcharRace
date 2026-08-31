from dataclasses import dataclass, replace
from math import isfinite

from models.bar_value_scale import BarValueScale


MIN_BAR_DOMAIN = 1.0


@dataclass(frozen=True)
class BarValueScaleResolver:
    """Resolve a stable bar domain against per-frame structural race width."""

    origin_x: float
    domain_max: float
    fallback_width: float

    @classmethod
    def from_config(cls, config, sprite_sets):
        global_max = max(
            (
                value
                for sprites in sprite_sets
                for sprite in sprites
                if (value := _visible_positive_value(sprite)) is not None
            ),
            default=0.0,
        )
        return cls(
            origin_x=float(config.left_margin),
            domain_max=max(MIN_BAR_DOMAIN, global_max),
            fallback_width=max(0.0, float(config.max_bar_width)),
        )

    def for_sprites(self, sprites):
        return BarValueScale(
            origin_x=self.origin_x,
            width=structural_bar_width(
                sprites,
                fallback_width=self.fallback_width,
            ),
            domain_max=self.domain_max,
        )


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
