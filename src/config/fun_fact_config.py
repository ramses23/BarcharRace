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
    editorial_background_texture: str = "none"
    editorial_background_texture_intensity: float = 0.25
    editorial_headline_size: int = 28
    editorial_headline_font_weight: str = "bold"
    editorial_headline_font_style: str = "normal"
    editorial_headline_color: str | None = None
    editorial_headline_opacity: float = 1.0
    editorial_body_size: int = 18
    editorial_body_font_weight: str = "normal"
    editorial_body_font_style: str = "normal"
    editorial_body_color: str | None = None
    editorial_body_opacity: float = 1.0
    editorial_credit_size: int = 12
    editorial_credit_font_weight: str = "normal"
    editorial_credit_font_style: str = "normal"
    editorial_credit_color: str | None = None
    editorial_credit_opacity: float = 1.0
    editorial_image_area_ratio: float = 0.42
    editorial_image_fit: str = "contain"
    editorial_text_image_gap: int = 18
    editorial_top_offset: int = 0
    editorial_reposition_time_label: bool = True
    editorial_orientation: str = "vertical"
    editorial_card_x: int | None = None
    editorial_card_y: int | None = None
    editorial_card_width: int | None = None
    editorial_card_height: int | None = None
    editorial_image_position: str = "right"
    editorial_collision_gap: int = 24
    editorial_layout_mode: str = "reserved"
    editorial_headline_alignment: str = "left"
    editorial_body_alignment: str = "left"
    editorial_placement_mode: str = "manual"
    editorial_keep_inside_safe_area: bool = False
    editorial_background_opacity: float = 1.0
    editorial_border_color: str | None = None
    editorial_border_opacity: float = 1.0
    editorial_border_width: int = 1
    editorial_corner_radius: int | None = None
    editorial_shadow_opacity: float = 0.0
    editorial_shadow_blur: int = 0
    editorial_shadow_offset: int = 0
    editorial_protect_top_n: int = 3
    editorial_bar_clearance: int = 16
