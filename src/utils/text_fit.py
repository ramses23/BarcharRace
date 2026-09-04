from functools import lru_cache
from math import ceil, floor

from PIL import Image, ImageDraw, ImageFont


_MEASUREMENT_FONT_PATH_OVERRIDES = {}


def estimate_text_width(text, font_size, average_char_width=0.56):
    return len(str(text)) * font_size * average_char_width


def measure_text_width(text, font):
    text = str(text)

    if hasattr(font, "getbbox"):
        left, _, right, _ = _cached_font_bbox(text, font)
        return float(right - left)

    probe = Image.new("L", (1, 1))
    left, _, right, _ = ImageDraw.Draw(probe).textbbox(
        (0, 0),
        text,
        font=font,
    )
    return float(right - left)


@lru_cache(maxsize=8192)
def _cached_font_bbox(text, font):
    return formatted_value_bbox(text, font)


_FORMATTED_VALUE_CHARACTERS = frozenset("0123456789,.-+ KMBT%")


def formatted_value_bbox(text, font, *, anchor=None, stroke_width=0):
    """Exact fast bbox for numeric value labels, with Pillow fallback.

    Formatted values use a small glyph alphabet.  Composing cached glyph
    advances, pair kerning and glyph boxes avoids invoking FreeType layout for
    every interpolated numeric string while retaining the same integer bbox.
    """
    text = str(text)
    if not text or not set(text).issubset(_FORMATTED_VALUE_CHARACTERS):
        return font.getbbox(text, anchor=anchor, stroke_width=stroke_width)
    left, top, right, bottom, pen = _cached_formatted_value_metrics(text, font)
    ascent, descent = font.getmetrics()
    if anchor:
        horizontal, vertical = anchor[0], anchor[1]
        if horizontal == "m":
            x_shift = -floor((pen / 2.0) + 0.5)
        elif horizontal == "r":
            x_shift = -floor(pen + 0.5)
        else:
            x_shift = 0
        if vertical == "m":
            y_shift = -floor((ascent + descent) / 2.0)
        elif vertical == "b":
            y_shift = -bottom
        elif vertical == "s":
            y_shift = -ascent
        elif vertical == "t":
            y_shift = -top
        else:
            y_shift = 0
        left += x_shift
        right += x_shift
        top += y_shift
        bottom += y_shift
    stroke_width = max(0, int(stroke_width))
    return (
        left - stroke_width,
        top - stroke_width,
        right + stroke_width,
        bottom + stroke_width,
    )


@lru_cache(maxsize=8192)
def _cached_formatted_value_metrics(text, font):
    glyphs, advances, kerning, ascent, descent = _formatted_font_metrics(font)
    pen = 0.0
    left = top = float("inf")
    right = bottom = float("-inf")
    for index, character in enumerate(text):
        glyph_left, glyph_top, glyph_right, glyph_bottom = glyphs[character]
        positioned_left = pen + glyph_left
        positioned_right = pen + glyph_right
        if positioned_left < left:
            left = positioned_left
        if glyph_top < top:
            top = glyph_top
        if positioned_right > right:
            right = positioned_right
        if glyph_bottom > bottom:
            bottom = glyph_bottom
        pen += advances[character]
        if index + 1 < len(text):
            pen += kerning[(character, text[index + 1])]
    left, top, right, bottom = (
        floor(left), floor(top), ceil(right), ceil(bottom),
    )
    return left, top, right, bottom, pen


@lru_cache(maxsize=64)
def _formatted_font_metrics(font):
    characters = tuple(sorted(_FORMATTED_VALUE_CHARACTERS))
    glyphs = {character: font.getbbox(character) for character in characters}
    advances = {
        character: font.getlength(character) for character in characters
    }
    kerning = {
        (first, second): (
            font.getlength(first + second)
            - advances[first]
            - advances[second]
        )
        for first in characters
        for second in characters
    }
    ascent, descent = font.getmetrics()
    return glyphs, advances, kerning, ascent, descent


def text_metric_cache_info():
    return _cached_font_bbox.cache_info()


def clear_text_metric_cache():
    _cached_font_bbox.cache_clear()


@lru_cache(maxsize=64)
def measurement_font(
    font_size, dpi, font_family, font_weight="normal", font_style="normal"
):
    key = (font_size, dpi, font_family, font_weight, font_style)
    override = _MEASUREMENT_FONT_PATH_OVERRIDES.get(key)
    pixel_size = max(1, int(round(float(font_size) * (float(dpi) / 72))))
    if override:
        return ImageFont.truetype(override, pixel_size)
    from matplotlib import font_manager

    properties = font_manager.FontProperties(
        family=font_family,
        weight=font_weight,
        style=font_style,
    )
    path = font_manager.findfont(properties, fallback_to_default=True)
    return ImageFont.truetype(path, pixel_size)


def install_measurement_font_path_overrides(overrides):
    """Install trusted parent-resolved font paths in an isolated worker."""
    _MEASUREMENT_FONT_PATH_OVERRIDES.update(dict(overrides or {}))
    measurement_font.cache_clear()


def fit_text_to_width(
    text,
    max_width,
    font_size=None,
    average_char_width=0.56,
    *,
    font=None,
    measure_text=None,
):
    text = str(text)

    if max_width <= 0:
        return ""

    if measure_text is None:
        if font is not None:
            measure_text = lambda value: measure_text_width(value, font)
        elif font_size is not None:
            measure_text = lambda value: estimate_text_width(
                value,
                font_size,
                average_char_width,
            )
        else:
            raise ValueError(
                "Provide a Pillow font, a measurement function, or font_size."
            )

    if measure_text(text) <= max_width:
        return text

    ellipsis = "..."

    if measure_text(ellipsis) > max_width:
        return ""

    best = ellipsis
    low = 1
    high = len(text)

    while low <= high:
        middle = (low + high) // 2
        candidate = text[:middle].rstrip() + ellipsis

        if measure_text(candidate) <= max_width:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1

    return best
