from dataclasses import dataclass
from math import isfinite


FULL_RESPONSE_RELATIVE_CHANGE = 0.25
DEFAULT_RESPONSE_SMOOTHING = 0.14
MAX_EFFECTIVE_SPEED = 12.0
MIN_EFFECTIVE_SPACING = 24.0
MAX_EFFECTIVE_SPACING = 2048.0


@dataclass(frozen=True)
class SpeedLineMotion:
    target_response: float
    smoothed_response: float
    effective_speed: float
    effective_spacing: float
    phase: float


def normalized_leader_change(current_bars, start_bars, end_bars):
    leader = _current_leader(current_bars)
    if leader is None:
        return 0.0

    start_value = _value_for_name(start_bars, leader.name)
    end_value = _value_for_name(end_bars, leader.name)
    scale = max(abs(start_value), abs(end_value), 1e-9)
    relative_change = abs(end_value - start_value) / scale
    return _clamp(relative_change / FULL_RESPONSE_RELATIVE_CHANGE, 0.0, 1.0)


def effective_speed_line_motion(
    *,
    base_speed,
    base_spacing,
    line_thickness,
    response,
    response_strength,
):
    response = _finite_clamp(response, 0.0, 1.0, default=0.0)
    strength = _finite_clamp(response_strength, 0.0, 2.0, default=1.0)
    base_speed = _finite_clamp(base_speed, 0.0, MAX_EFFECTIVE_SPEED, default=1.0)
    thickness = _finite_clamp(line_thickness, 1.0, 64.0, default=2.0)
    minimum_spacing = max(MIN_EFFECTIVE_SPACING, (thickness * 2.0) + 8.0)
    base_spacing = _finite_clamp(
        base_spacing,
        minimum_spacing,
        MAX_EFFECTIVE_SPACING,
        default=160.0,
    )
    speed_multiplier = 1.0 + (2.0 * response * strength)
    spacing_compression = 1.0 + (1.4 * response * strength)
    return (
        min(MAX_EFFECTIVE_SPEED, base_speed * speed_multiplier),
        max(minimum_spacing, base_spacing / spacing_compression),
    )


class SpeedLineMotionTracker:
    def __init__(
        self,
        *,
        fps,
        base_speed,
        base_spacing,
        line_thickness,
        response_mode,
        response_strength,
        smoothing=DEFAULT_RESPONSE_SMOOTHING,
    ):
        self.fps = max(1.0, float(fps))
        self.base_speed = base_speed
        self.base_spacing = base_spacing
        self.line_thickness = line_thickness
        self.response_mode = response_mode
        self.response_strength = response_strength
        self.smoothing = _finite_clamp(smoothing, 0.01, 1.0, default=0.14)
        self.response = 0.0
        self.phase = 0.0

    @classmethod
    def from_config(cls, config):
        return cls(
            fps=config.fps,
            base_speed=config.background_motion_speed,
            base_spacing=config.background_motion_line_spacing,
            line_thickness=config.background_motion_line_thickness,
            response_mode=config.background_motion_response,
            response_strength=config.background_motion_response_strength,
        )

    def next(self, target_response=0.0):
        target = (
            _finite_clamp(target_response, 0.0, 1.0, default=0.0)
            if self.response_mode == "leader_acceleration"
            else 0.0
        )
        self.response += (target - self.response) * self.smoothing
        speed, spacing = effective_speed_line_motion(
            base_speed=self.base_speed,
            base_spacing=self.base_spacing,
            line_thickness=self.line_thickness,
            response=self.response,
            response_strength=self.response_strength,
        )
        motion = SpeedLineMotion(
            target_response=target,
            smoothed_response=self.response,
            effective_speed=speed,
            effective_spacing=spacing,
            phase=self.phase,
        )
        velocity = -abs(speed)
        self.phase = (self.phase + (velocity / self.fps)) % 1.0
        return motion


def _current_leader(bars):
    candidates = [
        bar
        for bar in bars
        if _finite_value(getattr(bar, "value", None)) is not None
        and _visible_opacity(bar) > 0.0
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda bar: (
            -float(bar.value),
            str(bar.name).casefold(),
            str(bar.name),
        ),
    )


def _value_for_name(bars, name):
    for bar in bars:
        if bar.name == name:
            value = _finite_value(getattr(bar, "value", None))
            return 0.0 if value is None else value
    return 0.0


def _visible_opacity(bar):
    opacity = _finite_value(getattr(bar, "opacity", 1.0))
    return 0.0 if opacity is None else opacity


def _finite_value(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _finite_clamp(value, minimum, maximum, *, default):
    value = _finite_value(value)
    if value is None:
        value = default
    return _clamp(value, minimum, maximum)


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))
