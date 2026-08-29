from dataclasses import dataclass
from math import ceil, floor, inf, isfinite


FULL_RESPONSE_RELATIVE_CHANGE = 0.25
DEFAULT_RESPONSE_SMOOTHING = 0.14
MAX_EFFECTIVE_SPEED = 12.0
MIN_EFFECTIVE_SPACING = 24.0
MAX_EFFECTIVE_SPACING = 2048.0
MIN_EMISSION_INTERVAL_FRAMES = 2.0
MAX_ACTIVE_SPEED_LINES = 128
MAX_EMISSION_FREQUENCY_MULTIPLIER = 4.0
MAX_EXIT_COMPRESSED_LINES = 3
MAX_EXIT_COMPRESSION_RATIO = 0.35
MAX_EXIT_COMPRESSION_ZONE_RATIO = 0.30
EXIT_COMPRESSION_ZONE_SPACINGS = 3.0


@dataclass(frozen=True)
class SpeedLineMotion:
    target_response: float
    smoothed_response: float
    effective_speed: float
    effective_spacing: float
    emission_interval_frames: float
    emission_frames: tuple[float, ...]
    line_positions: tuple[float, ...]


def normalized_leader_change(current_bars, start_bars, end_bars):
    return normalized_rank_change(
        current_bars,
        start_bars,
        end_bars,
        rank=1,
    )


def normalized_second_place_change(current_bars, start_bars, end_bars):
    return normalized_rank_change(
        current_bars,
        start_bars,
        end_bars,
        rank=2,
    )


def normalized_rank_change(current_bars, start_bars, end_bars, *, rank):
    ranked_bar = _current_ranked_bar(current_bars, rank=rank)
    if ranked_bar is None:
        return 0.0

    start_value = _value_for_name(start_bars, ranked_bar.name)
    end_value = _value_for_name(end_bars, ranked_bar.name)
    scale = max(abs(start_value), abs(end_value), 1e-9)
    relative_change = abs(end_value - start_value) / scale
    return _clamp(relative_change / FULL_RESPONSE_RELATIVE_CHANGE, 0.0, 1.0)


def normalized_motion_response(
    current_bars,
    start_bars,
    end_bars,
    *,
    response_mode,
):
    if response_mode == "leader_acceleration":
        return normalized_leader_change(
            current_bars,
            start_bars,
            end_bars,
        )
    if response_mode == "second_place_acceleration":
        return normalized_second_place_change(
            current_bars,
            start_bars,
            end_bars,
        )
    return 0.0


def effective_speed_line_motion(
    *,
    base_speed,
    base_spacing,
    line_thickness,
    response,
    response_strength,
):
    base_speed = _finite_clamp(base_speed, 0.0, MAX_EFFECTIVE_SPEED, default=1.0)
    thickness = _finite_clamp(line_thickness, 1.0, 64.0, default=2.0)
    minimum_spacing = max(MIN_EFFECTIVE_SPACING, (thickness * 2.0) + 8.0)
    base_spacing = _finite_clamp(
        base_spacing,
        minimum_spacing,
        MAX_EFFECTIVE_SPACING,
        default=160.0,
    )
    return base_speed, base_spacing


def speed_line_emission_interval(
    *,
    fps,
    canvas_width,
    base_speed,
    base_spacing,
    line_thickness,
    response,
    response_strength,
):
    speed, spacing = effective_speed_line_motion(
        base_speed=base_speed,
        base_spacing=base_spacing,
        line_thickness=line_thickness,
        response=response,
        response_strength=response_strength,
    )
    fps = max(1.0, _finite_value(fps) or 1.0)
    width = max(1.0, _finite_value(canvas_width) or 1.0)
    thickness = _finite_clamp(line_thickness, 1.0, 64.0, default=2.0)
    speed_pixels_per_frame = (speed * spacing) / fps
    if speed_pixels_per_frame <= 0.0:
        return inf

    response = _finite_clamp(response, 0.0, 1.0, default=0.0)
    strength = _finite_clamp(response_strength, 0.0, 2.0, default=1.0)
    density = _clamp(response * strength, 0.0, 1.0)
    frequency_multiplier = 1.0 + (
        (MAX_EMISSION_FREQUENCY_MULTIPLIER - 1.0) * density
    )
    requested_interval = (fps / speed) / frequency_multiplier
    crossing_frames = (width + thickness) / speed_pixels_per_frame
    bounded_interval = crossing_frames / max(1, MAX_ACTIVE_SPEED_LINES - 1)
    return max(
        MIN_EMISSION_INTERVAL_FRAMES,
        bounded_interval,
        requested_interval,
    )


def constant_speed_line_positions(
    *,
    frame_index,
    fps,
    canvas_width,
    base_speed,
    base_spacing,
    line_thickness,
    response=0.0,
    response_strength=1.0,
):
    speed, spacing = effective_speed_line_motion(
        base_speed=base_speed,
        base_spacing=base_spacing,
        line_thickness=line_thickness,
        response=response,
        response_strength=response_strength,
    )
    fps = max(1.0, _finite_value(fps) or 1.0)
    width = max(1.0, _finite_value(canvas_width) or 1.0)
    thickness = _finite_clamp(line_thickness, 1.0, 64.0, default=2.0)
    speed_pixels_per_frame = (speed * spacing) / fps
    if speed_pixels_per_frame <= 0.0:
        return ()

    interval = speed_line_emission_interval(
        fps=fps,
        canvas_width=width,
        base_speed=speed,
        base_spacing=spacing,
        line_thickness=thickness,
        response=response,
        response_strength=response_strength,
    )
    current_frame = max(0.0, _finite_value(frame_index) or 0.0)
    crossing_frames = (width + thickness) / speed_pixels_per_frame
    first_index = max(0, ceil((current_frame - crossing_frames) / interval))
    last_index = floor(current_frame / interval)
    return tuple(
        speed_line_position(
            canvas_width=width,
            speed_pixels_per_frame=speed_pixels_per_frame,
            current_frame=current_frame,
            emission_frame=index * interval,
        )
        for index in range(first_index, last_index + 1)
    )


def speed_line_position(
    *,
    canvas_width,
    speed_pixels_per_frame,
    current_frame,
    emission_frame,
):
    width = max(1.0, _finite_value(canvas_width) or 1.0)
    speed = abs(_finite_value(speed_pixels_per_frame) or 0.0)
    age = max(
        0.0,
        (_finite_value(current_frame) or 0.0)
        - (_finite_value(emission_frame) or 0.0),
    )
    return width - (speed * age)


def left_edge_exit_compressed_positions(
    line_positions,
    *,
    canvas_width,
    base_spacing,
    enabled,
    strength,
):
    positions = tuple(float(position) for position in line_positions)
    if not enabled or not positions:
        return positions

    width = max(1.0, _finite_value(canvas_width) or 1.0)
    spacing = _finite_clamp(
        base_spacing,
        MIN_EFFECTIVE_SPACING,
        MAX_EFFECTIVE_SPACING,
        default=160.0,
    )
    zone_width = min(
        width * MAX_EXIT_COMPRESSION_ZONE_RATIO,
        spacing * EXIT_COMPRESSION_ZONE_SPACINGS,
    )
    if zone_width <= 0.0:
        return positions

    compression_ratio = MAX_EXIT_COMPRESSION_RATIO * _finite_clamp(
        strength,
        0.0,
        1.0,
        default=0.5,
    )
    if compression_ratio <= 0.0:
        return positions

    eligible = sorted(
        (
            (index, position)
            for index, position in enumerate(positions)
            if 0.0 <= position < zone_width
        ),
        key=lambda item: item[1],
    )[:MAX_EXIT_COMPRESSED_LINES]
    compressed = list(positions)
    for index, position in eligible:
        normalized_position = position / zone_width
        shift = (
            compression_ratio
            * position
            * (1.0 - normalized_position)
        )
        compressed[index] = position - shift
    return tuple(compressed)


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
        canvas_width=1920,
    ):
        self.fps = max(1.0, float(fps))
        self.base_speed, self.base_spacing = effective_speed_line_motion(
            base_speed=base_speed,
            base_spacing=base_spacing,
            line_thickness=line_thickness,
            response=0.0,
            response_strength=response_strength,
        )
        self.line_thickness = _finite_clamp(
            line_thickness,
            1.0,
            64.0,
            default=2.0,
        )
        self.canvas_width = max(
            1.0,
            _finite_value(canvas_width) or 1920.0,
        )
        self.response_mode = response_mode
        self.response_strength = response_strength
        self.smoothing = _finite_clamp(smoothing, 0.01, 1.0, default=0.14)
        self.response = 0.0
        self.frame_index = 0
        self.emission_progress = 0.0
        self.speed_pixels_per_frame = (
            self.base_speed * self.base_spacing
        ) / self.fps
        self.emission_frames = self._initial_emission_frames()

    @classmethod
    def from_config(cls, config):
        return cls(
            fps=config.fps,
            base_speed=config.background_motion_speed,
            base_spacing=config.background_motion_line_spacing,
            line_thickness=config.background_motion_line_thickness,
            response_mode=config.background_motion_response,
            response_strength=config.background_motion_response_strength,
            canvas_width=config.width,
        )

    def next(self, target_response=0.0):
        target = (
            _finite_clamp(target_response, 0.0, 1.0, default=0.0)
            if self.response_mode in (
                "leader_acceleration",
                "second_place_acceleration",
            )
            else 0.0
        )
        self.response += (target - self.response) * self.smoothing
        interval = speed_line_emission_interval(
            fps=self.fps,
            canvas_width=self.canvas_width,
            base_speed=self.base_speed,
            base_spacing=self.base_spacing,
            line_thickness=self.line_thickness,
            response=self.response,
            response_strength=self.response_strength,
        )
        active_emissions, line_positions = self._active_lines()
        motion = SpeedLineMotion(
            target_response=target,
            smoothed_response=self.response,
            effective_speed=self.base_speed,
            effective_spacing=self.base_spacing,
            emission_interval_frames=interval,
            emission_frames=active_emissions,
            line_positions=line_positions,
        )
        self._advance_emission_clock(interval)
        self.frame_index += 1
        return motion

    def _initial_emission_frames(self):
        if self.speed_pixels_per_frame <= 0.0:
            return []
        return [0.0]

    def _active_lines(self):
        active_emissions = []
        line_positions = []
        for emission_frame in self.emission_frames:
            if emission_frame > self.frame_index:
                continue
            position = speed_line_position(
                canvas_width=self.canvas_width,
                speed_pixels_per_frame=self.speed_pixels_per_frame,
                current_frame=self.frame_index,
                emission_frame=emission_frame,
            )
            if position < -self.line_thickness:
                continue
            active_emissions.append(emission_frame)
            line_positions.append(position)
        self.emission_frames = active_emissions
        return tuple(active_emissions), tuple(line_positions)

    def _advance_emission_clock(self, interval):
        if not isfinite(interval) or interval <= 0.0:
            return
        rate = 1.0 / interval
        next_progress = self.emission_progress + rate
        if next_progress >= 1.0:
            offset = (1.0 - self.emission_progress) / rate
            self.emission_frames.append(self.frame_index + offset)
            next_progress -= 1.0
        self.emission_progress = max(0.0, min(next_progress, 1.0))


def _current_ranked_bar(bars, *, rank):
    if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
        return None
    candidates = [
        bar
        for bar in bars
        if _finite_value(getattr(bar, "value", None)) is not None
        and _visible_opacity(bar) > 0.0
    ]
    if len(candidates) < rank:
        return None
    ranked = sorted(
        candidates,
        key=lambda bar: (
            -float(bar.value),
            str(bar.name).casefold(),
            str(bar.name),
        ),
    )
    return ranked[rank - 1]


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
