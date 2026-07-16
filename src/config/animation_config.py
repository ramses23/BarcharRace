from dataclasses import dataclass

from utils.easing import get_easing_function, list_easings


@dataclass(frozen=True)
class AnimationConfig:
    easing: str = "smoothstep"
    enter_exit: bool = True
    value_smoothing: bool = True
    motion_mode: str = "transition_easing"

    def easing_function(self):
        return get_easing_function(self.easing)

    @property
    def continuous_motion(self):
        return self.motion_mode == "continuous"


__all__ = [
    "AnimationConfig",
    "list_easings",
]
