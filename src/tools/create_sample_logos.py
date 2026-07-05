from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


LOGO_SIZE = 128
OUTPUT_DIR = Path("logos")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    create_badge(
        OUTPUT_DIR / "USA.png",
        "USA",
        stripes=[
            ("horizontal", "#B22234", 0.00, 0.14),
            ("horizontal", "#FFFFFF", 0.14, 0.28),
            ("horizontal", "#B22234", 0.28, 0.42),
            ("horizontal", "#FFFFFF", 0.42, 0.56),
            ("horizontal", "#B22234", 0.56, 0.70),
            ("horizontal", "#FFFFFF", 0.70, 0.84),
            ("horizontal", "#B22234", 0.84, 1.00),
            ("rect", "#3C3B6E", 0.00, 0.00, 0.48, 0.48),
        ],
    )
    create_badge(
        OUTPUT_DIR / "Mexico.png",
        "MEX",
        stripes=[
            ("vertical", "#006847", 0.00, 0.33),
            ("vertical", "#FFFFFF", 0.33, 0.67),
            ("vertical", "#CE1126", 0.67, 1.00),
        ],
    )
    create_badge(
        OUTPUT_DIR / "Canada.png",
        "CAN",
        stripes=[
            ("vertical", "#D80621", 0.00, 0.28),
            ("vertical", "#FFFFFF", 0.28, 0.72),
            ("vertical", "#D80621", 0.72, 1.00),
        ],
    )


def create_badge(path, label, stripes):
    scale = 4
    size = LOGO_SIZE * scale
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    badge = Image.new("RGBA", (size, size), "#FFFFFF")
    draw = ImageDraw.Draw(badge)

    for stripe in stripes:
        kind = stripe[0]

        if kind == "horizontal":
            _, color, start, end = stripe
            draw.rectangle(
                (0, int(size * start), size, int(size * end)),
                fill=color,
            )
        elif kind == "vertical":
            _, color, start, end = stripe
            draw.rectangle(
                (int(size * start), 0, int(size * end), size),
                fill=color,
            )
        elif kind == "rect":
            _, color, left, top, right, bottom = stripe
            draw.rectangle(
                (
                    int(size * left),
                    int(size * top),
                    int(size * right),
                    int(size * bottom),
                ),
                fill=color,
            )

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    margin = int(size * 0.04)
    mask_draw.ellipse((margin, margin, size - margin, size - margin), fill=255)
    image.alpha_composite(badge)
    image.putalpha(mask)

    draw = ImageDraw.Draw(image)
    border_width = int(size * 0.035)
    draw.ellipse(
        (
            margin,
            margin,
            size - margin,
            size - margin,
        ),
        outline="#222222",
        width=border_width,
    )

    font = load_font(int(size * 0.25))
    text_box = draw.textbbox((0, 0), label, font=font)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    text_position = (
        (size - text_width) / 2,
        (size - text_height) / 2 - int(size * 0.02),
    )

    shadow_offset = int(size * 0.015)
    draw.text(
        (text_position[0] + shadow_offset, text_position[1] + shadow_offset),
        label,
        font=font,
        fill=(0, 0, 0, 95),
    )
    draw.text(text_position, label, font=font, fill="#FFFFFF")

    image = image.resize((LOGO_SIZE, LOGO_SIZE), Image.Resampling.LANCZOS)
    image.save(path)


def load_font(size):
    for font_name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            pass

    return ImageFont.load_default()


if __name__ == "__main__":
    main()
