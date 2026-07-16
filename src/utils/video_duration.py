from dataclasses import dataclass


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
):
    periods = _non_negative_int(period_count)
    steps = max(1, _non_negative_int(steps_per_transition))
    frames_per_second = max(1, _non_negative_int(fps))
    transitions = max(0, periods - 1)
    frame_count = transitions * steps

    if continuous_motion and transitions > 0:
        frame_count += 1

    return VideoDurationEstimate(
        period_count=periods,
        transition_count=transitions,
        frame_count=frame_count,
        fps=frames_per_second,
        duration_seconds=frame_count / frames_per_second,
    )


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
