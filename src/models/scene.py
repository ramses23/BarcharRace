from dataclasses import dataclass, field

from models.bar_sprite import BarSprite
from models.fun_fact import ActiveFunFact


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
    frame_index: int = 0
