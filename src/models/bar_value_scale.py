from dataclasses import dataclass, field
from math import isfinite


@dataclass(frozen=True)
class BarValueScale:
    """Stable value-to-width transform for bars within one race geometry."""

    origin_x: float
    width: float
    domain_max: float
    timeline_progress: float = 0.0
    growth_envelope: float = 1.0
    leader_occupancy: float = 1.0
    tick_label_domain: float | None = None
    display_ranks: tuple | None = None
    # Presentation metadata must not change equality of numeric bar geometry.
    display_ticks: tuple | None = field(default=None, compare=False)

    @property
    def right_x(self):
        return self.origin_x + self.width

    def x_for_value(self, value):
        return self.origin_x + self.width_for_value(value)

    def width_for_value(self, value):
        value = float(value)
        if not isfinite(value) or self.domain_max <= 0.0:
            return 0.0
        value = max(0.0, value)
        raw_width = (
            (value / self.domain_max)
            * self.width
            * self.growth_envelope
        )
        return min(self.width, max(0.0, raw_width))
