from dataclasses import dataclass, field

from config.animation_config import AnimationConfig
from config.bar_selection_config import BarSelectionConfig
from config.theme_config import ThemeConfig
from config.value_format_config import ValueFormatConfig


@dataclass(frozen=True)
class ChartConfig:
    width: int = 1920
    height: int = 1080
    dpi: int = 150

    left_margin: int = 320
    right_margin: int = 220
    top_margin: int = 260
    bottom_margin: int = 140

    bar_height: int = 54
    bar_gap: int = 18
    auto_fit_bar_count: bool = True
    max_visible_bars: int | None = None
    bar_shape: str = "rectangle"
    bar_border_enabled: bool = False
    bar_border_color: str = "#FFFFFF"
    bar_border_width: float = 1.5
    bar_appearance_mode: str = "simple"
    bar_fill_type: str = "gradient"
    bar_gradient_direction: str = "horizontal"
    bar_gradient_color_count: int = 3
    bar_fill_use_category_color: bool = True
    bar_fill_color_start: str = "#315F8A"
    bar_fill_color_center: str = "#7FAED6"
    bar_fill_color_end: str = "#4E79A7"
    bar_highlight_position: float = 0.5
    bar_edge_darkening: float = 0.0
    bar_texture_enabled: bool = False
    bar_texture_preset: str = "noise"
    bar_texture_custom_image: str | None = None
    bar_texture_intensity: float = 0.2
    bar_texture_scale: float = 1.0
    bar_texture_contrast: float = 1.0
    bar_texture_blend_mode: str = "overlay"
    bar_bevel_enabled: bool = False
    bar_bevel_size: float = 0.12
    bar_bevel_highlight_opacity: float = 0.25
    bar_inner_shadow_opacity: float = 0.0
    bar_inner_shadow_size: float = 0.12
    bar_top_highlight_opacity: float = 0.0
    bar_bottom_shade_opacity: float = 0.0
    bar_outer_glow_enabled: bool = False
    bar_glow_color: str = "#FFFFFF"
    bar_glow_opacity: float = 0.25
    bar_glow_blur: float = 8.0
    bar_inner_glow_opacity: float = 0.0
    bar_shine_enabled: bool = False
    bar_shine_position: float = 0.5
    bar_shine_width: float = 0.15
    bar_shine_opacity: float = 0.25
    bar_track_enabled: bool = False
    bar_track_color: str = "#000000"
    bar_track_opacity: float = 0.12
    bar_logo_position: str = "outside_left"
    bar_logo_shape: str = "adaptive"
    bar_logo_padding: float = 4.0
    bar_logo_border_enabled: bool = False
    bar_logo_border_color: str = "#FFFFFF"
    bar_logo_border_width: float = 1.5
    bar_logo_background_enabled: bool = False
    bar_logo_background_color: str = "#FFFFFF"
    bar_logo_background_opacity: float = 1.0
    bar_secondary_logo_enabled: bool = True
    bar_secondary_logo_layout: str = "badge"
    bar_secondary_logo_position: str = "inside_right"
    bar_secondary_logo_badge_corner: str = "bottom_right"
    bar_secondary_logo_shape: str = "circle"
    bar_secondary_logo_size: int = 24
    bar_secondary_logo_gap: float = 6.0
    bar_secondary_logo_padding: float = 2.0
    bar_secondary_logo_border_enabled: bool = True
    bar_secondary_logo_border_color: str = "#FFFFFF"
    bar_secondary_logo_border_width: float = 1.5
    bar_secondary_logo_background_enabled: bool = False
    bar_secondary_logo_background_color: str = "#FFFFFF"
    bar_secondary_logo_background_opacity: float = 1.0
    bar_label_position: str = "left"
    bar_label_alignment: str = "auto"
    bar_value_position: str = "auto"
    bar_value_use_theme_color: bool = True
    bar_value_color: str = "#FFFFFF"
    bar_value_border_enabled: bool = False
    bar_value_border_color: str = "#000000"
    bar_value_border_width: float = 1.0
    bar_value_shadow_enabled: bool = False
    bar_value_shadow_color: str = "#000000"
    bar_value_shadow_offset_x: int = 1
    bar_value_shadow_offset_y: int = 1
    bar_shadow_enabled: bool = True
    bar_shadow_color: str = "#000000"
    bar_shadow_alpha: float = 0.12
    bar_shadow_offset_x: int = 5
    bar_shadow_offset_y: int = 4
    bar_gradient_enabled: bool = True
    bar_gradient_lighten: float = 0.22

    fps: int = 30
    steps_per_transition: int = 30
    animation: AnimationConfig = field(default_factory=AnimationConfig)
    selection: BarSelectionConfig = field(default_factory=BarSelectionConfig)

    frames_dir: str = "output/frames"
    output_file: str = "output/video.mp4"
    frame_output_mode: str = "ffmpeg_stream"
    frame_filename_template: str = "frame_{frame_id:04d}.png"
    frame_file_pattern: str = "frame_*.png"
    ffmpeg_frame_pattern: str = "frame_%04d.png"
    png_compress_level: int = 1
    video_codec: str = "libx264"
    video_pixel_format: str = "yuv420p"
    video_crf: int | None = 18
    video_bitrate: str | None = None
    ffmpeg_preset: str | None = None

    title: str = "Bar Chart Studio"
    layout_preset: str = "youtube_1080p"
    theme: ThemeConfig = field(default_factory=ThemeConfig)
    background_mode: str = "color"
    background_color_override: str | None = None
    background_image_path: str | None = None
    background_image_fit: str = "cover"
    typography_preset: str = "studio"

    title_font_size: int = 34
    subtitle_font_size: int = 20
    time_label_font_size: int = 120
    source_font_size: int = 16
    label_font_size: int = 20
    value_font_size: int = 20
    title_font_family: str | None = None
    subtitle_font_family: str | None = None
    time_label_font_family: str | None = None
    source_font_family: str | None = None
    label_font_family: str | None = None
    value_font_family: str | None = None
    title_text_color: str | None = None
    subtitle_text_color: str | None = None
    label_text_color: str | None = None
    value_text_color: str | None = None
    time_label_text_color: str | None = None
    source_text_color: str | None = None
    rank_label_text_color: str | None = None
    title_font_weight: str = "bold"
    subtitle_font_weight: str = "normal"
    time_label_font_weight: str = "bold"
    source_font_weight: str = "normal"
    title_max_width: int = 1280
    subtitle_max_width: int = 1280
    source_max_width: int = 980

    title_x: int | None = None
    title_y: int = 95
    subtitle_x: int | None = None
    subtitle_y: int = 165
    time_label_x: int = 1580
    time_label_y: int = 910
    source_x: int = 320
    source_y: int = 1005

    rank_labels_enabled: bool = True
    rank_label_prefix: str = "#"
    rank_label_font_size: int = 18
    rank_label_font_family: str | None = None
    rank_label_gap: int = 320
    rank_label_min_x: int = 96
    rank_label_label_gap: int = 18

    label_min_x: int = 40
    text_average_char_width: float = 0.56

    value_label_gap: int = 16
    value_label_edge_padding: int = 24
    value_label_min_x: int | None = None
    value_label_inside_padding: int = 18
    value_label_inside_color: str | None = None

    logos_enabled: bool = True
    logos_dir: str = "logos"
    logo_size: int = 48
    logo_gap: int = 16
    logo_label_gap: int = 14
    logo_file_extensions: tuple[str, ...] = (
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    )

    value_format: ValueFormatConfig = field(default_factory=ValueFormatConfig)

    @property
    def figure_size(self):
        return (
            self.width / self.dpi,
            self.height / self.dpi,
        )

    @property
    def max_bar_width(self):
        return self.width - self.left_margin - self.right_margin

    @property
    def bar_capacity(self):
        step = self.bar_height + self.bar_gap

        if self.bar_height <= 0 or step <= 0:
            return 0

        last_safe_center_y = self.height - self.bottom_margin - (self.bar_height / 2)

        if last_safe_center_y < self.top_margin:
            return 0

        return int((last_safe_center_y - self.top_margin) // step) + 1

    @property
    def background_color(self):
        return self.background_color_override or self.theme.background_color

    @property
    def text_color(self):
        return self.theme.text_color

    @property
    def muted_text_color(self):
        return self.theme.muted_text_color

    @property
    def resolved_title_text_color(self):
        return self.title_text_color or self.text_color

    @property
    def resolved_subtitle_text_color(self):
        return self.subtitle_text_color or self.muted_text_color

    @property
    def resolved_label_text_color(self):
        return self.label_text_color or self.text_color

    @property
    def resolved_value_text_color(self):
        return self.value_text_color or self.muted_text_color

    @property
    def resolved_time_label_text_color(self):
        return self.time_label_text_color or self.muted_text_color

    @property
    def resolved_source_text_color(self):
        return self.source_text_color or self.muted_text_color

    @property
    def resolved_rank_label_text_color(self):
        return self.rank_label_text_color or self.muted_text_color

    @property
    def font_family(self):
        return self.theme.font_family

    @property
    def color_palette(self):
        return self.theme.bar_palette

    def frame_filename(self, frame_id):
        return self.frame_filename_template.format(frame_id=frame_id)
