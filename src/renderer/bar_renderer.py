import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from config.chart_config import ChartConfig
from utils.text_fit import estimate_text_width, fit_text_to_width
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
        self._draw_time_label(ax, scene)
        self._draw_header(ax, scene)
        self._draw_bars(ax, scene.bars)
        self._draw_source_label(ax, scene)

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
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        ax.set_position((0, 0, 1, 1))
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
            self._fit_title(scene.title),
            ha="left",
            va="center",
            fontsize=self.config.title_font_size,
            fontfamily=self.config.font_family,
            fontweight=self.config.title_font_weight,
            color=self.config.text_color,
            zorder=5,
        )

        if scene.subtitle:
            ax.text(
                self.config.left_margin,
                self.config.subtitle_y,
                self._fit_subtitle(scene.subtitle),
                ha="left",
                va="center",
                fontsize=self.config.subtitle_font_size,
                fontfamily=self.config.font_family,
                fontweight=self.config.subtitle_font_weight,
                color=self.config.muted_text_color,
                zorder=5,
            )

    def _fit_title(self, title):
        return self._fit_text(
            title,
            max_width=self._available_text_width(
                self.config.left_margin,
                self.config.title_max_width,
            ),
            font_size=self.config.title_font_size,
        )

    def _fit_subtitle(self, subtitle):
        return self._fit_text(
            subtitle,
            max_width=self._available_text_width(
                self.config.left_margin,
                self.config.subtitle_max_width,
            ),
            font_size=self.config.subtitle_font_size,
        )

    def _draw_bars(self, ax, sprites):
        for sprite in sprites:
            opacity = self._opacity(sprite)

            if opacity <= 0:
                continue

            alpha = min(1.0, max(0.25, sprite.width / self.config.max_bar_width))
            rgba = mcolors.to_rgba(sprite.color, alpha * opacity)

            self._draw_bar_shadow(ax, sprite, opacity)

            self._draw_bar(ax, sprite, rgba)

            self._draw_rank_label(ax, sprite, opacity)
            self._draw_logo(ax, sprite, opacity)

            ax.text(
                self._label_x(sprite),
                sprite.y,
                self._fit_bar_label(sprite),
                ha="right",
                va="center",
                fontsize=self.config.label_font_size,
                fontfamily=self.config.font_family,
                color=self.config.text_color,
                alpha=opacity,
                zorder=4,
            )

            value_text = format_value(
                sprite.value,
                value_format=self.config.value_format,
            )
            value_layout = self._value_label_layout(sprite, value_text)

            ax.text(
                value_layout["x"],
                sprite.y,
                value_layout["text"],
                ha=value_layout["ha"],
                va="center",
                fontsize=self.config.value_font_size,
                fontfamily=self.config.font_family,
                color=value_layout["color"],
                alpha=opacity,
                zorder=4,
            )

    def _draw_bar(self, ax, sprite, rgba):
        if not self.config.bar_gradient_enabled:
            self._draw_solid_bar(ax, sprite, rgba)
            return

        ax.imshow(
            self._bar_gradient(rgba),
            extent=(
                sprite.x,
                sprite.x + sprite.width,
                sprite.y + (sprite.height / 2),
                sprite.y - (sprite.height / 2),
            ),
            aspect="auto",
            interpolation="bicubic",
            zorder=2,
        )

    def _draw_solid_bar(self, ax, sprite, rgba):
        ax.barh(
            sprite.y,
            sprite.width,
            height=sprite.height,
            left=sprite.x,
            color=rgba,
            edgecolor="none",
            zorder=2,
        )

    def _bar_gradient(self, rgba):
        lighten = max(0.0, min(1.0, self.config.bar_gradient_lighten))
        start = np.array(rgba)
        end = start.copy()
        end[:3] = start[:3] + ((1.0 - start[:3]) * lighten)

        return np.linspace(start, end, 64).reshape(1, 64, 4)

    def _draw_bar_shadow(self, ax, sprite, opacity):
        if not self.config.bar_shadow_enabled:
            return

        shadow_alpha = max(0.0, min(1.0, self.config.bar_shadow_alpha))

        if shadow_alpha <= 0:
            return

        ax.barh(
            sprite.y + self.config.bar_shadow_offset_y,
            sprite.width,
            height=sprite.height,
            left=sprite.x + self.config.bar_shadow_offset_x,
            color=mcolors.to_rgba(
                self.config.bar_shadow_color,
                shadow_alpha * opacity,
            ),
            edgecolor="none",
            zorder=1,
        )

    def _draw_rank_label(self, ax, sprite, opacity):
        if not self.config.rank_labels_enabled:
            return

        if sprite.rank is None:
            return

        ax.text(
            self._rank_label_x(),
            sprite.y,
            self._format_rank(sprite.rank),
            ha="right",
            va="center",
            fontsize=self.config.rank_label_font_size,
            fontfamily=self.config.font_family,
            fontweight="bold",
            color=self.config.muted_text_color,
            alpha=opacity,
            zorder=4,
        )

    def _rank_label_x(self):
        return max(
            self.config.rank_label_min_x,
            self.config.left_margin - self.config.rank_label_gap,
        )

    def _format_rank(self, rank):
        rounded_rank = max(1, round(rank))
        return f"{self.config.rank_label_prefix}{rounded_rank}"

    def _fit_bar_label(self, sprite):
        max_width = self._label_x(sprite) - self._bar_label_min_x(sprite)

        return fit_text_to_width(
            sprite.name,
            max_width=max_width,
            font_size=self._font_pixel_size(self.config.label_font_size),
            average_char_width=self.config.text_average_char_width,
        )

    def _bar_label_min_x(self, sprite):
        min_x = self.config.label_min_x

        if self.config.rank_labels_enabled and sprite.rank is not None:
            min_x = max(
                min_x,
                self._rank_label_x() + self.config.rank_label_label_gap,
            )

        return min_x

    def _value_label_layout(self, sprite, value_text):
        text = fit_text_to_width(
            value_text,
            max_width=self._value_label_max_width(),
            font_size=self._font_pixel_size(self.config.value_font_size),
            average_char_width=self.config.text_average_char_width,
        )
        text_width = self._value_label_text_width(text)
        max_right = self.config.width - self.config.value_label_edge_padding
        outside_x = sprite.x + sprite.width + self.config.value_label_gap

        if outside_x + text_width <= max_right:
            return {
                "text": text,
                "x": outside_x,
                "ha": "left",
                "color": self.config.muted_text_color,
            }

        inside_x = sprite.x + sprite.width - self.config.value_label_gap
        required_inside_width = text_width + (self.config.value_label_inside_padding * 2)

        if sprite.width >= required_inside_width:
            return {
                "text": text,
                "x": inside_x,
                "ha": "right",
                "color": self._value_label_inside_color(),
            }

        return {
            "text": text,
            "x": max_right,
            "ha": "right",
            "color": self.config.muted_text_color,
        }

    def _value_label_max_width(self):
        max_right = self.config.width - self.config.value_label_edge_padding
        return max(0, max_right - self._value_label_min_x())

    def _value_label_text_width(self, text):
        return estimate_text_width(
            text,
            self._font_pixel_size(self.config.value_font_size),
            self.config.text_average_char_width,
        )

    def _value_label_min_x(self):
        if self.config.value_label_min_x is not None:
            return self.config.value_label_min_x

        max_right = self.config.width - self.config.value_label_edge_padding

        if self.config.left_margin < max_right:
            return self.config.left_margin

        return self.config.label_min_x

    def _value_label_inside_color(self):
        return self.config.value_label_inside_color or self.config.background_color

    def _draw_logo(self, ax, sprite, opacity):
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
            alpha=opacity,
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
        cache_key = (logo_path, self.config.logo_size)

        if cache_key not in self.logo_cache:
            try:
                self.logo_cache[cache_key] = self._prepare_logo_image(logo_path)
            except (OSError, ValueError):
                self.logo_cache[cache_key] = None

        return self.logo_cache[cache_key]

    def _prepare_logo_image(self, logo_path):
        logo_size = max(1, int(self.config.logo_size))

        with Image.open(logo_path) as image:
            image = image.convert("RGBA")
            image.thumbnail(
                (logo_size, logo_size),
                Image.Resampling.LANCZOS,
            )
            canvas = Image.new("RGBA", (logo_size, logo_size), (255, 255, 255, 0))
            offset = (
                (logo_size - image.width) // 2,
                (logo_size - image.height) // 2,
            )
            canvas.alpha_composite(image, offset)

        return np.asarray(canvas)

    def _opacity(self, sprite):
        return min(1.0, max(0.0, sprite.opacity))

    def _draw_footer(self, ax, scene):
        self._draw_time_label(ax, scene)
        self._draw_source_label(ax, scene)

    def _draw_time_label(self, ax, scene):
        if scene.time_label:
            ax.text(
                self.config.time_label_x,
                self.config.time_label_y,
                scene.time_label,
                ha="right",
                va="center",
                fontsize=self.config.time_label_font_size,
                fontfamily=self.config.font_family,
                fontweight=self.config.time_label_font_weight,
                color=self.config.muted_text_color,
                alpha=0.22,
                zorder=0,
            )

    def _draw_source_label(self, ax, scene):
        if scene.source_label:
            ax.text(
                self.config.source_x,
                self.config.source_y,
                self._fit_source_label(scene.source_label),
                ha="left",
                va="center",
                fontsize=self.config.source_font_size,
                fontfamily=self.config.font_family,
                fontweight=self.config.source_font_weight,
                color=self.config.muted_text_color,
                zorder=5,
            )

    def _fit_source_label(self, source_label):
        return self._fit_text(
            source_label,
            max_width=self._available_text_width(
                self.config.source_x,
                self.config.source_max_width,
            ),
            font_size=self.config.source_font_size,
        )

    def _available_text_width(self, x, configured_max_width):
        right_edge = self.config.width - self.config.value_label_edge_padding
        available_width = right_edge - x

        return max(0, min(configured_max_width, available_width))

    def _fit_text(self, text, max_width, font_size):
        return fit_text_to_width(
            text,
            max_width=max_width,
            font_size=self._font_pixel_size(font_size),
            average_char_width=self.config.text_average_char_width,
        )

    def _font_pixel_size(self, font_size):
        return font_size * (self.config.dpi / 72)
