from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class ValueScale:
    origin_x: float
    width: float
    domain_max: float

    @property
    def right_x(self):
        return self.origin_x + self.width

    def x_for_value(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        if not isfinite(value) or self.domain_max <= 0.0:
            value = 0.0
        value = max(0.0, min(self.domain_max, value))
        return self.origin_x + ((value / self.domain_max) * self.width)

    def width_for_value(self, value):
        return self.x_for_value(value) - self.origin_x


@dataclass(frozen=True)
class ValueAxisTick:
    value: float
    x: float
    label: str
    opacity: float = 1.0


@dataclass(frozen=True)
class ValueAxisState:
    scale: ValueScale
    ticks: tuple[ValueAxisTick, ...]
    tick_step: float
    line_top: float
    line_bottom: float
    label_y: float
