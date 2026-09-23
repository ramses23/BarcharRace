from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class VideoDurationEstimate:
    period_count: int
    transition_count: int
    frame_count: int
    fps: int
    duration_seconds: float


def estimate_video_duration(
    *,
    period_count,
    steps_per_transition,
    fps,
    continuous_motion=False,
    intro_frames=0,
    final_frame_hold_frames=0,
):
    periods = _non_negative_int(period_count)
    steps = max(1, _non_negative_int(steps_per_transition))
    frames_per_second = max(1, _non_negative_int(fps))
    transitions = max(0, periods - 1)
    frame_count = transitions * steps

    if continuous_motion and transitions > 0:
        frame_count += 1
    if transitions > 0:
        frame_count += max(0, int(intro_frames))
        frame_count += max(0, int(final_frame_hold_frames))

    return VideoDurationEstimate(
        period_count=periods,
        transition_count=transitions,
        frame_count=frame_count,
        fps=frames_per_second,
        duration_seconds=frame_count / frames_per_second,
    )


def final_frame_hold_frames(seconds, fps):
    """Extra copies; the race's existing last frame is the first held frame."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not isfinite(seconds) or not 0 <= seconds <= 60:
        raise ValueError("Final frame hold must be from 0 to 60 seconds.")
    return max(0, round(seconds * fps) - 1) if seconds else 0


def format_video_duration(seconds):
    total_tenths = max(0, round(float(seconds) * 10))
    hours, remaining_tenths = divmod(total_tenths, 36000)
    minutes, remaining_tenths = divmod(remaining_tenths, 600)
    whole_seconds, tenths = divmod(remaining_tenths, 10)

    if hours:
        return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{tenths}"

    return f"{minutes:02d}:{whole_seconds:02d}.{tenths}"


def _non_negative_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0

    return max(0, parsed)
