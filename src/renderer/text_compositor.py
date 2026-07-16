import numpy as np
from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

from renderer.artists import TextSprite
from utils.value_formatter import format_value


class TextCompositorMixin:

    def _update_text_composites(self, scene):
        background_commands = []
        bar_commands = []
        foreground_commands = []

        if scene.time_label:
            command = self._text_command(
                scene.time_label,
                self.config.time_label_x,
                self.config.time_label_y,
                ha="right",
                va="center",
                font_size=self.config.time_label_font_size,
                font_family=self.config.time_label_font_family,
                font_weight=self.config.time_label_font_weight,
                color=self.config.resolved_time_label_text_color,
                opacity=0.22,
            )
            if command is not None:
                background_commands.append(command)

        header_specs = (
            (
                self._fit_title(scene.title),
                self._title_x(),
                self.config.title_y,
                self.config.title_font_size,
                self.config.title_font_family,
                self.config.title_font_weight,
                self.config.resolved_title_text_color,
            ),
            (
                self._fit_subtitle(scene.subtitle) if scene.subtitle else "",
                self._subtitle_x(),
                self.config.subtitle_y,
                self.config.subtitle_font_size,
                self.config.subtitle_font_family,
                self.config.subtitle_font_weight,
                self.config.resolved_subtitle_text_color,
            ),
            (
                self._fit_source_label(scene.source_label) if scene.source_label else "",
                self.config.source_x,
                self.config.source_y,
                self.config.source_font_size,
                self.config.source_font_family,
                self.config.source_font_weight,
                self.config.resolved_source_text_color,
            ),
        )
        for text, x, y, font_size, font_family, font_weight, color in header_specs:
            command = self._text_command(
                text,
                x,
                y,
                ha="left",
                va="center",
                font_size=font_size,
                font_family=font_family,
                font_weight=font_weight,
                color=color,
            )
            if command is not None:
                foreground_commands.append(command)

        for sprite in scene.bars:
            opacity = self._opacity(sprite)
            if opacity <= 0:
                continue

            if self.config.rank_labels_enabled and sprite.rank is not None:
                command = self._text_command(
                    self._format_rank(sprite.rank),
                    self._rank_label_x(),
                    sprite.y,
                    ha="right",
                    va="center",
                    font_size=self.config.rank_label_font_size,
                    font_family=self.config.rank_label_font_family,
                    font_weight="bold",
                    color=self.config.resolved_rank_label_text_color,
                    opacity=opacity,
                )
                if command is not None:
                    bar_commands.append(command)

            name_layout = self._bar_label_layout(sprite)
            command = self._text_command(
                name_layout["text"],
                name_layout["x"],
                name_layout["y"],
                ha=name_layout["ha"],
                va=name_layout["va"],
                font_size=self.config.label_font_size,
                font_family=self.config.label_font_family,
                font_weight="normal",
                color=name_layout["color"],
                opacity=opacity,
            )
            if command is not None:
                bar_commands.append(command)

            value_text = format_value(
                sprite.value,
                value_format=self.config.value_format,
            )
            value_layout = self._value_label_layout(sprite, value_text)
            command = self._text_command(
                value_layout["text"],
                value_layout["x"],
                value_layout.get("y", sprite.y),
                ha=value_layout["ha"],
                va=value_layout.get("va", "center"),
                font_size=self.config.value_font_size,
                font_family=self.config.value_font_family,
                font_weight="normal",
                color=value_layout["color"],
                opacity=opacity,
                stroke_width=(
                    self.config.bar_value_border_width
                    if self.config.bar_value_border_enabled
                    else 0
                ),
                stroke_color=self.config.bar_value_border_color,
                shadow_offset=(
                    self.config.bar_value_shadow_offset_x,
                    self.config.bar_value_shadow_offset_y,
                )
                if self.config.bar_value_shadow_enabled
                else None,
                shadow_color=self.config.bar_value_shadow_color,
                shadow_opacity=0.72,
            )
            if command is not None:
                bar_commands.append(command)

        self._text_background_artist.set_commands(background_commands)
        self._text_bar_artist.set_commands(bar_commands)
        self._text_foreground_artist.set_commands(foreground_commands)

    def _text_command(
        self,
        text,
        x,
        y,
        *,
        ha,
        va,
        font_size,
        font_family,
        font_weight,
        color,
        opacity=1.0,
        stroke_width=0.0,
        stroke_color="#000000",
        shadow_offset=None,
        shadow_color="#000000",
        shadow_opacity=0.0,
    ):
        if not text or opacity <= 0:
            return None

        sprite = self._cached_text_sprite(
            str(text),
            ha=ha,
            va=va,
            font_size=font_size,
            font_family=font_family,
            font_weight=font_weight,
            color=color,
            stroke_width=stroke_width,
            stroke_color=stroke_color,
            shadow_offset=shadow_offset,
            shadow_color=shadow_color,
            shadow_opacity=shadow_opacity,
        )
        image = sprite.image
        opacity = min(1.0, max(0.0, float(opacity)))

        if opacity < 0.999:
            image = image.copy(order="C")
            image[:, :, 3] = np.uint8(
                np.asarray(image[:, :, 3], dtype=np.float32) * opacity
            )

        return (
            image,
            int(round(x - sprite.anchor_x)),
            int(round(y - sprite.anchor_y)),
        )

    def _cached_text_sprite(
        self,
        text,
        *,
        ha,
        va,
        font_size,
        font_family,
        font_weight,
        color,
        stroke_width,
        stroke_color,
        shadow_offset,
        shadow_color,
        shadow_opacity,
    ):
        family = self._font_family(font_family)
        font_path = self._text_font_path(family, font_weight)
        pixel_size = max(1, int(round(self._font_pixel_size(font_size))))
        stroke_pixels = max(
            0,
            int(round(float(stroke_width) * (self.config.dpi / 72))),
        )
        shadow_pixels = None
        if shadow_offset is not None and shadow_opacity > 0:
            shadow_pixels = tuple(
                int(round(float(value) * (self.config.dpi / 72)))
                for value in shadow_offset
            )
        color_rgba = self._rgba8(color)
        stroke_rgba = self._rgba8(stroke_color)
        shadow_rgba = self._rgba8(shadow_color, alpha=shadow_opacity)
        cache_key = (
            text,
            font_path,
            pixel_size,
            str(font_weight).lower(),
            ha,
            va,
            color_rgba,
            stroke_pixels,
            stroke_rgba,
            shadow_pixels,
            shadow_rgba,
        )
        cached = self._lru_get(self._text_sprite_cache, cache_key)
        if cached is not None:
            return cached

        font = self._text_font(font_path, pixel_size)
        sprite = self._rasterize_text(
            text,
            font=font,
            ha=ha,
            va=va,
            color=color_rgba,
            stroke_width=stroke_pixels,
            stroke_color=stroke_rgba,
            shadow_offset=shadow_pixels,
            shadow_color=shadow_rgba,
        )
        self._lru_put(self._text_sprite_cache, cache_key, sprite, limit=2048)
        return sprite

    @staticmethod
    def _rasterize_text(
        text,
        *,
        font,
        ha,
        va,
        color,
        stroke_width,
        stroke_color,
        shadow_offset,
        shadow_color,
    ):
        horizontal_anchor = {
            "left": "l",
            "center": "m",
            "right": "r",
        }.get(ha, "l")
        vertical_anchor = {
            "top": "t",
            "center": "m",
            "bottom": "b",
            "baseline": "s",
        }.get(va, "m")
        anchor = horizontal_anchor + vertical_anchor
        probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        probe_draw = ImageDraw.Draw(probe)
        main_bbox = probe_draw.textbbox(
            (0, 0),
            text,
            font=font,
            anchor=anchor,
            stroke_width=stroke_width,
        )
        left, top, right, bottom = main_bbox

        if shadow_offset is not None and shadow_color[3] > 0:
            shadow_bbox = probe_draw.textbbox(
                shadow_offset,
                text,
                font=font,
                anchor=anchor,
            )
            left = min(left, shadow_bbox[0])
            top = min(top, shadow_bbox[1])
            right = max(right, shadow_bbox[2])
            bottom = max(bottom, shadow_bbox[3])

        padding = 1
        left = int(np.floor(left)) - padding
        top = int(np.floor(top)) - padding
        right = int(np.ceil(right)) + padding
        bottom = int(np.ceil(bottom)) + padding
        width = max(1, right - left)
        height = max(1, bottom - top)
        anchor_x = float(-left)
        anchor_y = float(-top)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        if shadow_offset is not None and shadow_color[3] > 0:
            shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(shadow_layer).text(
                (anchor_x + shadow_offset[0], anchor_y + shadow_offset[1]),
                text,
                font=font,
                anchor=anchor,
                fill=shadow_color,
            )
            canvas = Image.alpha_composite(canvas, shadow_layer)

        text_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)
        draw.text(
            (anchor_x, anchor_y),
            text,
            font=font,
            anchor=anchor,
            fill=color,
            stroke_width=stroke_width,
            stroke_fill=stroke_color if stroke_width > 0 else None,
        )
        canvas = Image.alpha_composite(canvas, text_layer)
        image = np.array(
            np.asarray(canvas)[::-1],
            dtype=np.uint8,
            copy=True,
            order="C",
        )
        return TextSprite(image=image, anchor_x=anchor_x, anchor_y=anchor_y)

    def _text_font_path(self, family, weight):
        cache_key = (str(family), str(weight).lower())
        cached = self._text_font_path_cache.get(cache_key)
        if cached is not None:
            return cached

        properties = font_manager.FontProperties(
            family=family,
            weight=weight,
        )
        path = font_manager.findfont(properties, fallback_to_default=True)
        self._text_font_path_cache[cache_key] = path
        return path

    def _text_font(self, font_path, pixel_size):
        cache_key = (font_path, int(pixel_size))
        cached = self._lru_get(self._text_font_cache, cache_key)
        if cached is not None:
            return cached

        font = ImageFont.truetype(font_path, pixel_size)
        self._lru_put(self._text_font_cache, cache_key, font, limit=64)
        return font
