from collections import OrderedDict
import math

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFont

from core.display_calendar import flip_calendar_dimensions


class FlipCalendarRenderer:
    """Stateless split-flap geometry with a small bounded raster cache."""

    def __init__(self, cache_limit=96):
        self._cache = OrderedDict()
        self._cache_limit = max(1, int(cache_limit))

    def clear(self):
        self._cache.clear()

    def command(self, state, config, *, font_path):
        if state is None or not config.time_label_enabled:
            return None
        key = (
            state,
            round(float(config.flip_calendar_scale), 3),
            config.flip_calendar_card_background,
            round(float(config.flip_calendar_card_opacity), 3),
            config.flip_calendar_text_color,
            config.flip_calendar_border_color,
            round(float(config.flip_calendar_shadow_opacity), 3),
            round(float(config.flip_calendar_corner_radius), 3),
            round(float(config.time_label_opacity), 3),
            str(font_path),
        )
        image = self._cache.pop(key, None)
        if image is None:
            image = self._render(state, config, font_path=font_path)
            self._cache[key] = image
            while len(self._cache) > self._cache_limit:
                self._cache.popitem(last=False)
        else:
            self._cache[key] = image

        width, height = image.shape[1], image.shape[0]
        return (
            image,
            int(round(config.time_label_x - width)),
            int(round(config.time_label_y - (height / 2))),
        )

    def _render(self, state, config, *, font_path):
        width, height = flip_calendar_dimensions(config.flip_calendar_scale)
        aa = 2
        canvas = Image.new("RGBA", (width * aa, height * aa), (0, 0, 0, 0))
        scale = width / 360.0
        gap = max(4, int(round(12 * scale * aa)))
        shadow_offset = max(2, int(round(5 * scale * aa)))
        year_height = int(round(104 * scale * aa))
        bottom_top = year_height + gap
        bottom_height = canvas.height - bottom_top
        month_width = int(round((canvas.width - gap) * 0.58))
        day_left = month_width + gap
        radius = int(round(config.flip_calendar_corner_radius * scale * aa))
        border_width = max(1, int(round(1.2 * scale * aa)))
        card_opacity = _clamped_opacity(config.flip_calendar_card_opacity)
        text_opacity = _clamped_opacity(config.time_label_opacity)
        background = _with_opacity(
            _rgba(config.flip_calendar_card_background),
            card_opacity,
        )
        border = _with_opacity(
            _rgba(config.flip_calendar_border_color),
            card_opacity,
        )
        text_color = _with_opacity(
            _rgba(config.flip_calendar_text_color),
            text_opacity,
        )
        shadow = (0, 0, 0, int(round(
            255
            * _clamped_opacity(config.flip_calendar_shadow_opacity)
            * card_opacity
        )))
        specs = (
            ("YEAR", state.year, (0, 0, canvas.width, year_height)),
            ("MONTH", state.month, (0, bottom_top, month_width, canvas.height)),
            ("DAY", state.day, (day_left, bottom_top, canvas.width, canvas.height)),
        )
        for label, module, box in specs:
            self._draw_module(
                canvas,
                label,
                module,
                box,
                font_path=font_path,
                background=background,
                border=border,
                text_color=text_color,
                shadow=shadow,
                shadow_offset=shadow_offset,
                radius=radius,
                border_width=border_width,
                aa=aa,
            )

        canvas = canvas.resize((width, height), Image.Resampling.LANCZOS)
        return np.array(
            np.asarray(canvas)[::-1],
            dtype=np.uint8,
            copy=True,
            order="C",
        )

    def _draw_module(
        self,
        canvas,
        label,
        module,
        box,
        *,
        font_path,
        background,
        border,
        text_color,
        shadow,
        shadow_offset,
        radius,
        border_width,
        aa,
    ):
        left, top, right, bottom = box
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle(
            (
                left + shadow_offset,
                top + shadow_offset,
                right,
                bottom,
            ),
            radius=radius,
            fill=shadow,
        )
        card_right = right - shadow_offset
        card_bottom = bottom - shadow_offset
        card_width = max(1, card_right - left)
        card_height = max(1, card_bottom - top)
        half = max(1, card_height // 2)
        seam_y = top + half
        scale_aa = card_height / (104.0 if label == "YEAR" else 115.0)
        value_size = max(
            18,
            int(round((48 if label == "YEAR" else 42) * scale_aa)),
        )
        label_size = max(9, int(round(10 * scale_aa)))
        value_font = ImageFont.truetype(font_path, value_size)
        label_font = ImageFont.truetype(font_path, label_size)
        structure_layer = self._structure_layer(
            card_width,
            card_height,
            background,
            border,
            radius,
            border_width,
        )
        old_text_layer = self._text_layer(
            label,
            module.old_value,
            card_width,
            card_height,
            value_font,
            label_font,
            text_color,
            background,
            aa,
        )
        new_text_layer = self._text_layer(
            label,
            module.new_value,
            card_width,
            card_height,
            value_font,
            label_font,
            text_color,
            background,
            aa,
        )
        phase = max(0.0, min(1.0, float(module.phase)))
        module_layer = Image.new("RGBA", (card_width, card_height), (0, 0, 0, 0))
        if module.old_value == module.new_value or phase >= 0.999:
            module_layer.alpha_composite(structure_layer)
            module_layer.alpha_composite(new_text_layer)
        elif phase <= 0.5:
            _, fold_height, fold_top, depth = flap_projection(phase, half)
            self._composite_surface_section(
                module_layer,
                structure_layer,
                new_text_layer,
                crop=(0, 0, card_width, half - fold_height),
                destination_y=0,
                brightness=0.78,
            )
            self._composite_surface_section(
                module_layer,
                structure_layer,
                old_text_layer,
                crop=(0, half, card_width, card_height),
                destination_y=half,
            )
            self._draw_fold_shadow(
                module_layer,
                y=fold_top,
                depth=depth,
                shadow=shadow,
                aa=aa,
            )
            self._composite_surface_section(
                module_layer,
                structure_layer,
                old_text_layer,
                crop=(0, 0, card_width, half),
                destination_y=fold_top,
                destination_height=fold_height,
                brightness=1.0 - (0.48 * depth),
            )
        else:
            _, fold_height, fold_top, depth = flap_projection(phase, half)
            self._composite_surface_section(
                module_layer,
                structure_layer,
                new_text_layer,
                crop=(0, 0, card_width, half),
                destination_y=0,
            )
            self._composite_surface_section(
                module_layer,
                structure_layer,
                old_text_layer,
                crop=(0, half + fold_height, card_width, card_height),
                destination_y=half + fold_height,
                brightness=0.78,
            )
            self._draw_fold_shadow(
                module_layer,
                y=half + fold_height,
                depth=depth,
                shadow=shadow,
                aa=aa,
            )
            self._composite_surface_section(
                module_layer,
                structure_layer,
                new_text_layer,
                crop=(0, half, card_width, card_height),
                destination_y=fold_top,
                destination_height=fold_height,
                brightness=1.0 - (0.48 * depth),
            )
        canvas.alpha_composite(module_layer, (left, top))

        draw = ImageDraw.Draw(canvas)
        seam_color = _blend(
            border,
            (0, 0, 0, border[3]),
            0.42,
        )
        draw.line(
            (left + border_width, seam_y, card_right - border_width, seam_y),
            fill=seam_color,
            width=max(1, border_width),
        )
        hinge_radius = max(2, int(round(2.2 * aa)))
        for hinge_x in (left + border_width * 2, card_right - border_width * 2):
            draw.ellipse(
                (
                    hinge_x - hinge_radius,
                    seam_y - hinge_radius,
                    hinge_x + hinge_radius,
                    seam_y + hinge_radius,
                ),
                fill=_blend(
                    border,
                    (255, 255, 255, border[3]),
                    0.15,
                ),
            )

    @staticmethod
    def _structure_layer(
        width,
        height,
        background,
        border,
        radius,
        border_width,
    ):
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            (0, 0, width - 1, height - 1),
            radius=radius,
            fill=background,
            outline=border,
            width=border_width,
        )
        return layer

    @staticmethod
    def _text_layer(
        label,
        value,
        width,
        height,
        value_font,
        label_font,
        color,
        background,
        aa,
    ):
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw.text(
            (width / 2, height / 2 + (height * 0.05)),
            str(value),
            font=value_font,
            fill=color,
            anchor="mm",
            stroke_width=1,
            stroke_fill=_blend(color, (0, 0, 0, color[3]), 0.32),
        )
        draw.text(
            (max(8, int(round(10 * aa))), max(5, int(round(6 * aa)))),
            label,
            font=label_font,
            fill=_blend(
                color,
                (*background[:3], color[3]),
                0.45,
            ),
            anchor="la",
        )
        return layer

    @staticmethod
    def _composite_surface_section(
        destination,
        structure,
        text,
        *,
        crop,
        destination_y,
        destination_height=None,
        brightness=1.0,
    ):
        left, top, right, bottom = crop
        if right <= left or bottom <= top:
            return
        structure_section = structure.crop(crop)
        text_section = text.crop(crop)
        if destination_height is not None:
            destination_height = max(1, int(destination_height))
            size = (structure_section.width, destination_height)
            structure_section = structure_section.resize(
                size,
                Image.Resampling.BICUBIC,
            )
            text_section = text_section.resize(size, Image.Resampling.BICUBIC)
        brightness = max(0.0, min(1.0, float(brightness)))
        if brightness < 0.999:
            structure_section = ImageEnhance.Brightness(
                structure_section
            ).enhance(brightness)
            text_section = ImageEnhance.Brightness(text_section).enhance(
                brightness
            )
        destination.alpha_composite(
            structure_section,
            (left, int(destination_y)),
        )
        destination.alpha_composite(text_section, (left, int(destination_y)))

    @staticmethod
    def _draw_fold_shadow(destination, *, y, depth, shadow, aa):
        if shadow[3] <= 0 or depth <= 0:
            return
        band = max(1, int(round((2.0 + (5.0 * depth)) * aa)))
        alpha = int(round(shadow[3] * depth))
        top = max(0, min(destination.height - 1, int(y) - (band // 2)))
        bottom = max(top, min(destination.height - 1, top + band))
        overlay = Image.new("RGBA", destination.size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle(
            (0, top, destination.width - 1, bottom),
            fill=(0, 0, 0, alpha),
        )
        destination.alpha_composite(overlay)


def flap_projection(phase, half_height):
    """Return moving piece, visible height, top edge, and edge-on depth."""
    phase = max(0.0, min(1.0, float(phase)))
    half_height = max(1, int(half_height))
    if phase <= 0.5:
        progress = phase * 2.0
        angle = progress * (math.pi / 2.0)
        visible_height = max(1, int(round(half_height * math.cos(angle))))
        return (
            "old_top",
            visible_height,
            half_height - visible_height,
            math.sin(angle),
        )
    progress = (phase - 0.5) * 2.0
    angle = progress * (math.pi / 2.0)
    visible_height = max(1, int(round(half_height * math.sin(angle))))
    return (
        "new_bottom",
        visible_height,
        half_height,
        math.cos(angle),
    )


def _rgba(value):
    try:
        return ImageColor.getcolor(str(value).strip(), "RGBA")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid RGB color: {value!r}.") from exc


def _with_opacity(color, opacity):
    opacity = _clamped_opacity(opacity)
    return (*color[:3], int(round(color[3] * opacity)))


def _clamped_opacity(value):
    return max(0.0, min(1.0, float(value)))


def _blend(first, second, amount):
    amount = max(0.0, min(1.0, float(amount)))
    return tuple(
        int(round((a * (1.0 - amount)) + (b * amount)))
        for a, b in zip(first, second)
    )
