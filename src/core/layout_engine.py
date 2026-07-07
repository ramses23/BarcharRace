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

        for i, bar in enumerate(visible_bars):

            y_position = self.config.top_margin + i * (
                self.config.bar_height + self.config.bar_gap
            )
            width = self._bar_width(bar.value, max_value)

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
                    logo_path=self._resolve_logo(bar),
                )
            )

        return sprites

    def _visible_bars(self, sorted_bars):
        limit = len(sorted_bars)

        if self.config.max_visible_bars is not None:
            limit = min(limit, max(0, self.config.max_visible_bars))

        if self.config.auto_fit_bar_count:
            limit = min(limit, self.config.bar_capacity)

        return sorted_bars[:limit]

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
