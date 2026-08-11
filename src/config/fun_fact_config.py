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
    editorial_background_mode: str = "card"
    editorial_background_color: str | None = None
    editorial_headline_size: int = 28
    editorial_body_size: int = 18
    editorial_credit_size: int = 12
    editorial_image_area_ratio: float = 0.42
    editorial_image_fit: str = "contain"
    editorial_text_image_gap: int = 18
    editorial_top_offset: int = 0
    editorial_reposition_time_label: bool = True
