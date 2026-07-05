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

    logo_path: str | None = None
