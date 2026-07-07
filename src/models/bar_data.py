from dataclasses import dataclass


@dataclass
class BarData:
    """
    Representa los datos de una barra.
    No contiene informacion visual obligatoria.
    """

    name: str
    value: float
    color: str | None = None
    logo_path: str | None = None
