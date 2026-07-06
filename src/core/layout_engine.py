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
        sorted_bars = sorted(bars, key=lambda b: b.value, reverse=True)

        max_value = max(b.value for b in sorted_bars)

        sprites = []

        for i, bar in enumerate(sorted_bars):

            y_position = self.config.top_margin + i * (
                self.config.bar_height + self.config.bar_gap
            )
            width = (bar.value / max_value) * self.config.max_bar_width

            sprites.append(
                BarSprite(
                    name=bar.name,
                    value=bar.value,
                    color=bar.color or self.palette.get(bar.name),

                    x=self.config.left_margin,
                    y=y_position,
                    width=width,
                    height=self.config.bar_height,
                    rank=i + 1,
                    logo_path=self._resolve_logo(bar.name),
                )
            )

        return sprites

    def _resolve_logo(self, name):
        if not self.config.logos_enabled:
            return None

        return self.logo_resolver.resolve(name)
