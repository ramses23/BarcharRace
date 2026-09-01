import re
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
        settled_indexes = {
            index
            for index, value in enumerate(datetimes)
            if value in self.anchors
        }
        formatted = {
            "year": tuple(f"{value.year:04d}" for value in dates),
            "month": tuple(MONTH_NAMES[value.month - 1] for value in dates),
            "day": tuple(str(value.day) for value in dates),
        }
        modules = {
            name: self._module_states(values, settled_indexes)
            for name, values in formatted.items()
        }
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

    def _module_states(self, values, settled_indexes):
        duration = self.flip_duration_frames
        states = []
        for index, current in enumerate(values):
            previous = values[index - 1] if index > 0 else current
            if index in settled_indexes or index == len(values) - 1:
                states.append(FlipModuleState(current, current, 1.0))
                continue
            if previous != current:
                # A late-phase direct flip handles render frames that skip
                # multiple display dates without inserting extra frames.
                phase = max(0.55, min(0.9, 1.0 - (1.0 / duration)))
                states.append(FlipModuleState(previous, current, phase))
                continue

            next_change = None
            search_stop = min(len(values), index + duration + 1)
            for candidate in range(index + 1, search_stop):
                if values[candidate] != current:
                    next_change = candidate
                    break
            if next_change is None:
                states.append(FlipModuleState(current, current, 1.0))
                continue
            distance = next_change - index
            phase = 0.5 * ((duration - distance + 1) / (duration + 1))
            states.append(
                FlipModuleState(current, values[next_change], phase)
            )
        return tuple(states)
