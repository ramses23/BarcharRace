from dataclasses import dataclass

from utils.easing import get_easing_function, list_easings

MIN_RANK_MOVEMENT_DURATION = 0.10
MAX_RANK_MOVEMENT_DURATION = 1.00


@dataclass(frozen=True)
class AnimationConfig:
    easing: str = "smoothstep"
    enter_exit: bool = True
    value_smoothing: bool = True
    motion_mode: str = "transition_easing"
    rank_movement_duration: float = 1.0
    transition_duration_mode: str = "uniform"
    minimum_transition_duration_seconds: float = 1.0

    def __post_init__(self):
        if self.transition_duration_mode not in ("uniform", "activity_weighted"):
            raise ValueError("Transition duration mode must be 'uniform' or 'activity_weighted'.")
        value = self.minimum_transition_duration_seconds
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0.5 <= value <= 2.0:
            raise ValueError("Minimum transition duration must be from 0.5 to 2.0 seconds.")

    def easing_function(self):
        return get_easing_function(self.easing)

    @property
    def continuous_motion(self):
        return self.motion_mode == "continuous"


__all__ = [
    "AnimationConfig",
    "list_easings",
]
