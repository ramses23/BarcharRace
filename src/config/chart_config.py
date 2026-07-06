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
    frame_filename_template: str = "frame_{frame_id:04d}.png"
    frame_file_pattern: str = "frame_*.png"
    ffmpeg_frame_pattern: str = "frame_%04d.png"

    title: str = "Bar Chart Studio"
    layout_preset: str = "youtube_1080p"
    theme: ThemeConfig = field(default_factory=ThemeConfig)
    typography_preset: str = "studio"

    title_font_size: int = 34
    subtitle_font_size: int = 20
    time_label_font_size: int = 120
    source_font_size: int = 16
    label_font_size: int = 20
    value_font_size: int = 20
    title_font_weight: str = "bold"
    subtitle_font_weight: str = "normal"
    time_label_font_weight: str = "bold"
    source_font_weight: str = "normal"
    title_max_width: int = 1280
    subtitle_max_width: int = 1280
    source_max_width: int = 980

    title_y: int = 95
    subtitle_y: int = 165
    time_label_x: int = 1580
    time_label_y: int = 910
    source_x: int = 320
    source_y: int = 1005

    rank_labels_enabled: bool = True
    rank_label_prefix: str = "#"
    rank_label_font_size: int = 18
    rank_label_gap: int = 320

    label_min_x: int = 40
    text_average_char_width: float = 0.56

    value_label_gap: int = 16
    value_label_edge_padding: int = 24
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
    def background_color(self):
        return self.theme.background_color

    @property
    def text_color(self):
        return self.theme.text_color

    @property
    def muted_text_color(self):
        return self.theme.muted_text_color

    @property
    def font_family(self):
        return self.theme.font_family

    @property
    def color_palette(self):
        return self.theme.bar_palette

    def frame_filename(self, frame_id):
        return self.frame_filename_template.format(frame_id=frame_id)
