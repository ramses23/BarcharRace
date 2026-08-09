from dataclasses import dataclass


@dataclass(frozen=True)
class FunFactConfig:
    """Project-level configuration for timeline-bound editorial overlays."""

    enabled: bool = False
    source: str | None = None
    layout: str = "right_panel"
    panel_width: int | None = None
    panel_margin: int = 32
    panel_padding: int = 28
    fade_in: float = 0.20
    fade_out: float = 0.20
