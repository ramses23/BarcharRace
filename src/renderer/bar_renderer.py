import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt

from config.chart_config import ChartConfig
from utils.value_formatter import format_value


class BarRenderer:

    def __init__(self, output_dir="output", config=None):
        self.output_dir = output_dir
        self.config = config or ChartConfig()
        self.logo_cache = {}
        os.makedirs(self.output_dir, exist_ok=True)

    def render(self, scene, filename="frame.png"):
        fig, ax = plt.subplots(
            figsize=self.config.figure_size,
            dpi=self.config.dpi,
        )

        self._setup_canvas(fig, ax)
        self._draw_header(ax, scene)
        self._draw_bars(ax, scene.bars)
        self._draw_footer(ax, scene)

        path = os.path.join(self.output_dir, filename)
        plt.savefig(
            path,
            dpi=self.config.dpi,
            facecolor=fig.get_facecolor(),
            bbox_inches=None,
            pad_inches=0,
        )
        plt.close(fig)

        return path

    def _setup_canvas(self, fig, ax):
        fig.patch.set_facecolor(self.config.background_color)
        ax.set_facecolor(self.config.background_color)
        ax.clear()
        ax.set_xlim(0, self.config.width)
        ax.set_ylim(0, self.config.height)
        ax.invert_yaxis()
        ax.axis("off")

    def _draw_header(self, ax, scene):
        ax.text(
            self.config.left_margin,
            self.config.title_y,
            scene.title,
            ha="left",
            va="center",
            fontsize=self.config.title_font_size,
            fontfamily=self.config.font_family,
            fontweight="bold",
            color=self.config.text_color,
        )

        if scene.subtitle:
            ax.text(
                self.config.left_margin,
                self.config.subtitle_y,
                scene.subtitle,
                ha="left",
                va="center",
                fontsize=self.config.subtitle_font_size,
                fontfamily=self.config.font_family,
                color=self.config.muted_text_color,
            )

    def _draw_bars(self, ax, sprites):
        for sprite in sprites:
            alpha = min(1.0, max(0.25, sprite.width / self.config.max_bar_width))
            rgba = mcolors.to_rgba(sprite.color, alpha)

            ax.barh(
                sprite.y,
                sprite.width,
                height=sprite.height,
                left=sprite.x,
                color=rgba,
                edgecolor="none",
            )

            self._draw_logo(ax, sprite)

            ax.text(
                self._label_x(sprite),
                sprite.y,
                sprite.name,
                ha="right",
                va="center",
                fontsize=self.config.label_font_size,
                fontfamily=self.config.font_family,
                color=self.config.text_color,
            )

            ax.text(
                sprite.x + sprite.width + 16,
                sprite.y,
                format_value(
                    sprite.value,
                    value_format=self.config.value_format,
                ),
                ha="left",
                va="center",
                fontsize=self.config.value_font_size,
                fontfamily=self.config.font_family,
                color=self.config.muted_text_color,
            )

    def _draw_logo(self, ax, sprite):
        if not sprite.logo_path:
            return

        image = self._load_logo(sprite.logo_path)

        if image is None:
            return

        logo_right = sprite.x - self.config.logo_gap
        logo_left = logo_right - self.config.logo_size
        half_size = self.config.logo_size / 2

        ax.imshow(
            image,
            extent=(
                logo_left,
                logo_right,
                sprite.y + half_size,
                sprite.y - half_size,
            ),
            zorder=3,
        )

    def _label_x(self, sprite):
        if not sprite.logo_path:
            return sprite.x - 16

        return (
            sprite.x
            - self.config.logo_gap
            - self.config.logo_size
            - self.config.logo_label_gap
        )

    def _load_logo(self, logo_path):
        if logo_path not in self.logo_cache:
            try:
                self.logo_cache[logo_path] = plt.imread(logo_path)
            except (OSError, ValueError):
                self.logo_cache[logo_path] = None

        return self.logo_cache[logo_path]

    def _draw_footer(self, ax, scene):
        if scene.time_label:
            ax.text(
                self.config.time_label_x,
                self.config.time_label_y,
                scene.time_label,
                ha="right",
                va="center",
                fontsize=self.config.time_label_font_size,
                fontfamily=self.config.font_family,
                fontweight="bold",
                color=self.config.muted_text_color,
                alpha=0.22,
            )

        if scene.source_label:
            ax.text(
                self.config.source_x,
                self.config.source_y,
                scene.source_label,
                ha="left",
                va="center",
                fontsize=self.config.source_font_size,
                fontfamily=self.config.font_family,
                color=self.config.muted_text_color,
            )
