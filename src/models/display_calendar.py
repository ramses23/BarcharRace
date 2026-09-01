from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class FlipModuleState:
    old_value: str
    new_value: str
    phase: float = 1.0

    @property
    def is_flipping(self):
        return self.old_value != self.new_value and self.phase < 1.0


@dataclass(frozen=True)
class DisplayCalendarState:
    """Display-only Gregorian time derived from real timeline checkpoints."""

    display_datetime: datetime
    display_date: date
    year: FlipModuleState
    month: FlipModuleState
    day: FlipModuleState
    frame_index: int
