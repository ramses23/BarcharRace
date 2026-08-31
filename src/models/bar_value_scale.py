from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class BarValueScale:
    """Stable value-to-width transform for bars within one race geometry."""

    origin_x: float
    width: float
    domain_max: float

    @property
    def right_x(self):
        return self.origin_x + self.width

    def x_for_value(self, value):
        return self.origin_x + self.width_for_value(value)

    def width_for_value(self, value):
        value = float(value)
        if not isfinite(value) or self.domain_max <= 0.0:
            return 0.0
        value = max(0.0, min(self.domain_max, value))
        return (value / self.domain_max) * self.width
