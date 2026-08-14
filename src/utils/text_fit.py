from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont


def estimate_text_width(text, font_size, average_char_width=0.56):
    return len(str(text)) * font_size * average_char_width


def measure_text_width(text, font):
    text = str(text)

    if hasattr(font, "getbbox"):
        left, _, right, _ = font.getbbox(text)
        return float(right - left)

    probe = Image.new("L", (1, 1))
    left, _, right, _ = ImageDraw.Draw(probe).textbbox(
        (0, 0),
        text,
        font=font,
    )
    return float(right - left)


@lru_cache(maxsize=64)
def measurement_font(font_size, dpi, font_family, font_weight="normal"):
    from matplotlib import font_manager

    properties = font_manager.FontProperties(
        family=font_family,
        weight=font_weight,
    )
    path = font_manager.findfont(properties, fallback_to_default=True)
    pixel_size = max(1, int(round(float(font_size) * (float(dpi) / 72))))
    return ImageFont.truetype(path, pixel_size)


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
