from dataclasses import dataclass, field

from models.bar_sprite import BarSprite


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
