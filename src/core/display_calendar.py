import re
from dataclasses import dataclass
from datetime import date, datetime, time

from models.display_calendar import DisplayCalendarState, FlipModuleState


FLIP_CALENDAR_BASE_WIDTH = 360
FLIP_CALENDAR_BASE_HEIGHT = 236
MONTH_NAMES = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)
_ANNUAL_PATTERN = re.compile(r"^(\d{4})$")
_MONTHLY_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")
_DAILY_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


class DisplayCalendarError(ValueError):
    pass


@dataclass(frozen=True)
class FlipEventWindow:
    old_value: str
    new_value: str
    change_frame: int
    start_frame: int
    end_frame: int
    configured_duration_frames: int
    effective_duration_frames: int
    previous_change_frame: int | None
    next_change_frame: int | None
    phases: tuple[float, ...]

    def phase_at(self, frame_index):
        offset = int(frame_index) - self.start_frame
        if offset < 0 or offset >= len(self.phases):
            return None
        return self.phases[offset]


def flip_calendar_dimensions(scale):
    scale = max(0.4, min(2.0, float(scale)))
    return (
        int(round(FLIP_CALENDAR_BASE_WIDTH * scale)),
        int(round(FLIP_CALENDAR_BASE_HEIGHT * scale)),
    )


def parse_calendar_anchor(value, *, granularity=None):
    """Parse only unambiguous Gregorian annual, monthly, or daily tokens."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)

    token = str(value).strip()
    match = _DAILY_PATTERN.fullmatch(token)
    inferred = "daily"
    if match is None:
        match = _MONTHLY_PATTERN.fullmatch(token)
        inferred = "monthly"
    if match is None:
        match = _ANNUAL_PATTERN.fullmatch(token)
        inferred = "annual"
    if match is None:
        raise DisplayCalendarError(
            "Flip Calendar requires unambiguous YYYY, YYYY-MM, or "
            f"YYYY-MM-DD timeline labels; received {token!r}."
        )
    if granularity is not None and granularity != inferred:
        raise DisplayCalendarError(
            f"Timeline token {token!r} does not match configured "
            f"time_granularity {granularity!r}."
        )

    try:
        if inferred == "annual":
            return datetime(int(match.group(1)), 1, 1)
        if inferred == "monthly":
            return datetime(int(match.group(1)), int(match.group(2)), 1)
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        )
    except ValueError as exc:
        raise DisplayCalendarError(
            f"Invalid Gregorian timeline date: {token!r}."
        ) from exc


class DisplayCalendarResolver:
    """
    Resolve display time without changing dataset resolution.

    Anchors are real checkpoints. Intermediate dates exist only as bounded,
    precomputed frame display states and never become dataset observations.
    """

    def __init__(
        self,
        anchors,
        *,
        periods,
        steps_per_transition,
        continuous_motion=False,
        flip_duration_frames=4,
    ):
        self.periods = tuple(periods)
        self.anchors = tuple(anchors)
        if len(self.periods) != len(self.anchors):
            raise DisplayCalendarError(
                "Display calendar periods and anchors must have equal length."
            )
        if not self.anchors:
            raise DisplayCalendarError(
                "Display calendar requires at least one real checkpoint."
            )
        if any(b <= a for a, b in zip(self.anchors, self.anchors[1:])):
            raise DisplayCalendarError(
                "Display calendar anchors must be strictly increasing."
            )
        self.steps_per_transition = max(1, int(steps_per_transition))
        self.continuous_motion = bool(continuous_motion)
        self.flip_duration_frames = max(1, min(
            12, int(flip_duration_frames)
        ))
        datetimes = self._build_frame_datetimes()
        self._event_windows = {}
        self._event_by_frame = {}
        self._states = self._build_states(datetimes)

    @classmethod
    def from_timeline(
        cls,
        timeline,
        periods,
        *,
        steps_per_transition,
        continuous_motion=False,
        flip_duration_frames=4,
    ):
        periods = tuple(periods)
        granularity = getattr(timeline.config, "time_granularity", None)
        anchors = tuple(
            parse_calendar_anchor(
                timeline.get_time_label(period),
                granularity=granularity,
            )
            for period in periods
        )
        return cls(
            anchors,
            periods=periods,
            steps_per_transition=steps_per_transition,
            continuous_motion=continuous_motion,
            flip_duration_frames=flip_duration_frames,
        )

    @property
    def frame_count(self):
        return len(self._states)

    def state_at(self, frame_index):
        frame_index = max(0, min(int(frame_index), len(self._states) - 1))
        return self._states[frame_index]

    def event_windows(self, module_name):
        return self._event_windows.get(str(module_name), ())

    def event_window_at(self, module_name, frame_index):
        windows = self._event_by_frame.get(str(module_name), ())
        if not windows:
            return None
        frame_index = max(0, min(int(frame_index), len(windows) - 1))
        return windows[frame_index]

    def _build_frame_datetimes(self):
        if len(self.anchors) == 1:
            return (self.anchors[0],)

        frames = []
        steps = self.steps_per_transition
        for index, (start, end) in enumerate(
            zip(self.anchors, self.anchors[1:])
        ):
            if self.continuous_motion:
                first_step = 0 if index == 0 else 1
                sample_steps = range(first_step, steps + 1)
                denominator = steps
            else:
                sample_steps = range(steps)
                denominator = max(1, steps - 1)
            span = end - start
            frames.extend(
                start + (span * (step / denominator))
                for step in sample_steps
            )
        return tuple(frames)

    def _build_states(self, datetimes):
        dates = tuple(value.date() for value in datetimes)
        formatted = {
            "year": tuple(f"{value.year:04d}" for value in dates),
            "month": tuple(MONTH_NAMES[value.month - 1] for value in dates),
            "day": tuple(str(value.day) for value in dates),
        }
        modules = {}
        for name, values in formatted.items():
            states, events, event_by_frame = self._module_states(values)
            modules[name] = states
            self._event_windows[name] = events
            self._event_by_frame[name] = event_by_frame
        return tuple(
            DisplayCalendarState(
                display_datetime=value,
                display_date=dates[index],
                year=modules["year"][index],
                month=modules["month"][index],
                day=modules["day"][index],
                frame_index=index,
            )
            for index, value in enumerate(datetimes)
        )

    def _module_states(self, values):
        values = tuple(values)
        frame_count = len(values)
        changes = tuple(
            index
            for index in range(1, frame_count)
            if values[index] != values[index - 1]
        )
        events = tuple(
            self._event_window(values, changes, ordinal)
            for ordinal in range(len(changes))
        )
        event_by_frame = [None] * frame_count
        states = [
            FlipModuleState(value, value, 1.0)
            for value in values
        ]
        for event in events:
            for frame_index in range(
                event.start_frame,
                event.end_frame + 1,
            ):
                phase = event.phase_at(frame_index)
                states[frame_index] = FlipModuleState(
                    event.old_value,
                    event.new_value,
                    phase,
                )
                event_by_frame[frame_index] = event
        return tuple(states), events, tuple(event_by_frame)

    def _event_window(self, values, changes, ordinal):
        change_frame = changes[ordinal]
        previous_change = changes[ordinal - 1] if ordinal > 0 else None
        next_change = (
            changes[ordinal + 1]
            if ordinal + 1 < len(changes)
            else None
        )
        left_limit = (
            1
            if previous_change is None
            else ((previous_change + change_frame) // 2) + 1
        )
        right_limit = (
            len(values) - 1
            if next_change is None
            else (change_frame + next_change) // 2
        )
        available = max(1, right_limit - left_limit + 1)
        effective_duration = min(self.flip_duration_frames, available)
        preferred_start = change_frame - (effective_duration // 2)
        latest_start = right_limit - effective_duration + 1
        start_frame = max(left_limit, min(preferred_start, latest_start))
        end_frame = start_frame + effective_duration - 1
        phases = _event_phases(
            effective_duration,
            configured_duration=self.flip_duration_frames,
            event_ordinal=ordinal,
            settle_at_end=end_frame == len(values) - 1,
        )
        return FlipEventWindow(
            old_value=values[change_frame - 1],
            new_value=values[change_frame],
            change_frame=change_frame,
            start_frame=start_frame,
            end_frame=end_frame,
            configured_duration_frames=self.flip_duration_frames,
            effective_duration_frames=effective_duration,
            previous_change_frame=previous_change,
            next_change_frame=next_change,
            phases=phases,
        )


def _event_phases(
    duration,
    *,
    configured_duration,
    event_ordinal,
    settle_at_end=False,
):
    duration = max(1, int(duration))
    if duration == 1:
        if configured_duration <= 1:
            return (1.0,)
        cycle_length = min(4, max(2, int(configured_duration)))
        cycle_offset = event_ordinal % cycle_length
        phase = 0.55 + (0.45 * (cycle_offset / (cycle_length - 1)))
        phases = (phase,)
    elif duration == 2:
        phases = (0.35, 0.78)
    elif duration == 3:
        phases = (0.20, 0.60, 0.88)
    else:
        denominator = duration - 1
        phases = tuple(index / denominator for index in range(duration))
    if settle_at_end:
        phases = (*phases[:-1], 1.0)
    return phases
