from dataclasses import dataclass, field

from models.bar_sprite import BarSprite
from models.fun_fact import ActiveFunFact


@dataclass(frozen=True)
class ShortOverlay:
    kind: str
    title: str
    subtitle: str = ""
    opacity: float = 1.0


@dataclass
class Scene:
    """
    Representa una escena completa lista para renderizar.
    """

    title: str
    subtitle: str = ""
    time_label: str = ""
    source_label: str = ""
    bars: list[BarSprite] = field(default_factory=list)
    fun_fact: ActiveFunFact | None = None
    short_overlay: ShortOverlay | None = None
    frame_index: int = 0
    background_motion_response: float = 0.0
    background_motion_line_positions: tuple[float, ...] | None = None
