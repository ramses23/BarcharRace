from dataclasses import dataclass


@dataclass
class BarSprite:
    """
    Representa una barra lista para dibujarse en pantalla.
    """

    name: str
    value: float
    color: str

    x: float
    y: float

    width: float
    height: float

    rank: float | None = None
    logo_path: str | None = None
    secondary_logo_path: str | None = None
    opacity: float = 1.0
    rank_motion_state: str = "stable"
    rank_motion_progress: float = 0.0
    rank_motion_target: float | None = None
