from collections import OrderedDict

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

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
        background = _with_opacity(
            _rgba(config.flip_calendar_card_background),
            config.flip_calendar_card_opacity,
        )
        border = _rgba(config.flip_calendar_border_color)
        text_color = _rgba(config.flip_calendar_text_color)
        shadow = (0, 0, 0, int(round(
            255 * max(0.0, min(1.0, config.flip_calendar_shadow_opacity))
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

        opacity = max(0.0, min(1.0, float(config.time_label_opacity)))
        canvas = canvas.resize((width, height), Image.Resampling.LANCZOS)
        if opacity < 0.999:
            alpha = np.asarray(canvas.getchannel("A"), dtype=np.float32)
            canvas.putalpha(Image.fromarray(np.uint8(alpha * opacity)))
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
        card_box = (left, top, card_right, card_bottom)
        draw.rounded_rectangle(
            card_box,
            radius=radius,
            fill=background,
            outline=border,
            width=border_width,
        )
        card_width = max(1, card_right - left)
        card_height = max(1, card_bottom - top)
        seam_y = top + (card_height // 2)
        scale_aa = card_height / (104.0 if label == "YEAR" else 115.0)
        value_size = max(
            18,
            int(round((48 if label == "YEAR" else 42) * scale_aa)),
        )
        label_size = max(9, int(round(10 * scale_aa)))
        value_font = ImageFont.truetype(font_path, value_size)
        label_font = ImageFont.truetype(font_path, label_size)
        old_layer = self._text_layer(
            module.old_value,
            card_width,
            card_height,
            value_font,
            text_color,
        )
        new_layer = self._text_layer(
            module.new_value,
            card_width,
            card_height,
            value_font,
            text_color,
        )
        phase = max(0.0, min(1.0, float(module.phase)))
        half = max(1, card_height // 2)
        top_mask = Image.new("L", (card_width, card_height), 0)
        ImageDraw.Draw(top_mask).rectangle((0, 0, card_width, half), fill=255)
        bottom_mask = Image.new("L", (card_width, card_height), 0)
        ImageDraw.Draw(bottom_mask).rectangle(
            (0, half, card_width, card_height), fill=255
        )
        module_layer = Image.new("RGBA", (card_width, card_height), (0, 0, 0, 0))
        if module.old_value == module.new_value or phase >= 0.999:
            module_layer.alpha_composite(new_layer)
        elif phase <= 0.5:
            module_layer.paste(old_layer, (0, 0), bottom_mask)
            fold = old_layer.crop((0, 0, card_width, half))
            fold_height = max(1, int(round(half * (1.0 - (phase * 2.0)))))
            fold = fold.resize((card_width, fold_height), Image.Resampling.BICUBIC)
            fold.putalpha(Image.eval(fold.getchannel("A"), lambda a: int(a * 0.82)))
            module_layer.alpha_composite(fold, (0, half - fold_height))
        else:
            module_layer.paste(new_layer, (0, 0), top_mask)
            fold = new_layer.crop((0, half, card_width, card_height))
            fold_height = max(1, int(round(half * ((phase - 0.5) * 2.0))))
            fold = fold.resize((card_width, fold_height), Image.Resampling.BICUBIC)
            module_layer.alpha_composite(fold, (0, half))
        canvas.alpha_composite(module_layer, (left, top))

        draw = ImageDraw.Draw(canvas)
        seam_color = _blend(border, (0, 0, 0, 255), 0.42)
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
                fill=_blend(border, (255, 255, 255, 255), 0.15),
            )
        draw.text(
            (left + max(8, int(round(10 * aa))), top + max(5, int(round(6 * aa)))),
            label,
            font=label_font,
            fill=_blend(
                text_color,
                (*background[:3], text_color[3]),
                0.45,
            ),
            anchor="la",
        )

    @staticmethod
    def _text_layer(value, width, height, font, color):
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(
            (width / 2, height / 2 + (height * 0.05)),
            str(value),
            font=font,
            fill=color,
            anchor="mm",
            stroke_width=1,
            stroke_fill=_blend(color, (0, 0, 0, 255), 0.32),
        )
        return layer


def _rgba(value):
    try:
        return ImageColor.getcolor(str(value).strip(), "RGBA")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid RGB color: {value!r}.") from exc


def _with_opacity(color, opacity):
    opacity = max(0.0, min(1.0, float(opacity)))
    return (*color[:3], int(round(color[3] * opacity)))


def _blend(first, second, amount):
    amount = max(0.0, min(1.0, float(amount)))
    return tuple(
        int(round((a * (1.0 - amount)) + (b * amount)))
        for a, b in zip(first, second)
    )
