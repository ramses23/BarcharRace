from config.chart_config import ChartConfig
from models.bar_sprite import BarSprite
from utils.asset_resolver import AssetResolver
from utils.color_palette import ColorPalette


class LayoutEngine:

    def __init__(self, config=None):
        self.config = config or ChartConfig()
        self.palette = ColorPalette(self.config.color_palette)
        self.logo_resolver = AssetResolver(
            self.config.logos_dir,
            self.config.logo_file_extensions,
        )

    def build(self, bars):

        if not bars:
            return []

        # ordenar SOLO para asignar ranking
        sorted_bars = sorted(bars, key=self._sort_key)
        visible_bars = self._visible_bars(sorted_bars)

        if not visible_bars:
            return []

        max_value = max(b.value for b in visible_bars)

        sprites = []

        bar_height, bar_gap, first_y = self._vertical_geometry(len(visible_bars))
        for i, bar in enumerate(visible_bars):

            y_position = first_y + i * (bar_height + bar_gap)
            width = self._bar_width(bar.value, max_value)

            sprites.append(
                BarSprite(
                    name=bar.name,
                    value=bar.value,
                    color=bar.color or self.palette.get(bar.name),

                    x=self.config.left_margin,
                    y=y_position,
                    width=width,
                    height=bar_height,
                    rank=i + 1,
                    logo_path=self._resolve_logo(bar),
                    secondary_logo_path=(
                        bar.secondary_logo_path
                        if self.config.logos_enabled
                        else None
                    ),
                )
            )

        return sprites

    def _visible_bars(self, sorted_bars):
        nonzero_bars = [bar for bar in sorted_bars if bar.value != 0]
        limit = len(nonzero_bars)

        if self.config.max_visible_bars is not None:
            limit = min(limit, max(0, self.config.max_visible_bars))

        if (
            self.config.auto_fit_bar_count
            and self.config.bar_vertical_layout_mode != "fill_available"
        ):
            limit = min(limit, self.config.bar_capacity)

        return nonzero_bars[:limit]

    def _vertical_geometry(self, count):
        if self.config.bar_vertical_layout_mode != "fill_available" or count <= 0:
            return self.config.bar_height, self.config.bar_gap, self.config.top_margin
        top = max(0, self.config.bar_vertical_top_padding)
        bottom_edge = self.config.height - max(0, self.config.bar_vertical_bottom_padding)
        if self.config.title_enabled:
            top = max(top, self.config.title_y + self._text_half_height(self.config.title_font_size) + 12)
        if self.config.subtitle_enabled:
            top = max(top, self.config.subtitle_y + self._text_half_height(self.config.subtitle_font_size) + 12)
        if self.config.source_label_enabled:
            bottom_edge = min(bottom_edge, self.config.source_y - self._text_half_height(self.config.source_font_size) - 12)
        available = max(count, bottom_edge - top)
        if count == 1:
            height = min(self.config.bar_height, available)
            return height, 0, top + (available / 2)
        ratio = max(0.0, self.config.bar_gap / max(1, self.config.bar_height))
        height = max(1.0, available / (count + ratio * (count - 1)))
        gap = max(0.0, height * ratio)
        used = height * count + gap * (count - 1)
        return height, gap, top + ((available - used) / 2) + (height / 2)

    def _text_half_height(self, point_size):
        return max(1.0, float(point_size) * self.config.dpi / 144.0)

    def _bar_width(self, value, max_value):
        if max_value <= 0:
            return 0

        return (value / max_value) * self.config.max_bar_width

    def _resolve_logo(self, bar):
        if not self.config.logos_enabled:
            return None

        return bar.logo_path or self.logo_resolver.resolve(bar.name)

    def _sort_key(self, bar):
        if (
            self.config.selection.aggregate_other
            and bar.name == self.config.selection.other_label
        ):
            return (1, 0)

        return (0, -bar.value)
