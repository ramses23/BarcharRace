from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


@lru_cache(maxsize=512)
def representative_logo_color(path):
    """Return a deterministic, useful RGB hex color for a logo, or None."""
    if not path:
        return None
    try:
        resolved = Path(path).resolve(strict=True)
        stamp = resolved.stat().st_mtime_ns
    except (OSError, ValueError):
        return None
    return _representative_logo_color_cached(str(resolved), stamp)


@lru_cache(maxsize=512)
def _representative_logo_color_cached(path, _stamp):
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGBA")
            image.thumbnail((128, 128), Image.Resampling.BILINEAR)
            pixels = np.asarray(image, dtype=np.uint8).reshape(-1, 4)
    except (OSError, ValueError):
        return None

    visible = pixels[pixels[:, 3] >= 32, :3]
    if not len(visible):
        return None

    rgb = visible.astype(np.float32) / 255.0
    maximum = rgb.max(axis=1)
    minimum = rgb.min(axis=1)
    saturation = np.divide(
        maximum - minimum,
        maximum,
        out=np.zeros_like(maximum),
        where=maximum > 0,
    )
    luminance = rgb @ np.asarray((0.2126, 0.7152, 0.0722), dtype=np.float32)

    # White padding is common around otherwise colorful marks. Keep neutral
    # pixels only when the logo itself is genuinely neutral.
    useful = (saturation >= 0.12) & (luminance >= 0.08) & (luminance <= 0.94)
    samples = visible[useful] if useful.any() else visible
    sample_saturation = saturation[useful] if useful.any() else saturation
    sample_luminance = luminance[useful] if useful.any() else luminance

    bins = (samples // 32).astype(np.int16)
    keys = bins[:, 0] * 64 + bins[:, 1] * 8 + bins[:, 2]
    unique, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    scores = np.zeros(len(unique), dtype=np.float64)
    for index in range(len(unique)):
        members = inverse == index
        chroma = float(sample_saturation[members].mean())
        midtone = 1.0 - min(1.0, abs(float(sample_luminance[members].mean()) - 0.52) * 1.5)
        scores[index] = float(counts[index]) * (0.65 + chroma) * (0.75 + 0.25 * midtone)
    chosen = inverse == int(np.argmax(scores))
    color = np.median(samples[chosen], axis=0).round().astype(np.uint8)
    return "#{:02X}{:02X}{:02X}".format(*color.tolist())
