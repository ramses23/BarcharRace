"""Local premultiplied-alpha affine resampling at the raster boundary."""

from dataclasses import dataclass
from math import ceil, floor

import numpy as np
from PIL import Image


def raster_extent(value):
    """Stable local size: ignore cancellation noise at integral dimensions."""
    return max(1, ceil(float(value) - 1e-9))


@dataclass(frozen=True)
class FloatImageCommand:
    image: object
    left: float
    top: float
    scale: float = 1.0
    scale_y: float | None = None

    # Preserve the existing three-item diagnostic/mirroring command interface.
    def __iter__(self):
        return iter((self.image, self.left, self.top))

    def __getitem__(self, index):
        return (self.image, self.left, self.top)[index]


def rasterize_image_command(command):
    """Return a bottom-up RGBA image and integer destination; no edge halos.

    Translation and optional local uniform scale are applied together. Working
    in premultiplied alpha prevents transparent RGB from bleeding into edges.
    Integer identity placements retain their exact historical pixels.
    """
    image, left, top = command
    scale = getattr(command, "scale", 1.0)
    scale_y = getattr(command, "scale_y", None)
    scale_y = scale if scale_y is None else scale_y
    x, y = floor(left), floor(top)
    dx, dy = left - x, top - y
    if dx == 0 and dy == 0 and scale == 1 and scale_y == 1:
        return image, x, y
    width = max(1, int(np.ceil(image.shape[1] * scale + dx))) + 2
    height = max(1, int(np.ceil(image.shape[0] * scale_y + dy))) + 2
    source = Image.fromarray(np.asarray(image)[::-1]).convert("RGBa")
    # Transparent guards make coverage continuous even across an integer
    # boundary; PIL otherwise clamps interpolation to an opaque edge pixel.
    padded = Image.new("RGBa", (source.width + 2, source.height + 2))
    padded.paste(source, (1, 1))
    shifted = padded.transform(
        (width, height), Image.Transform.AFFINE,
        (1 / scale, 0, 1 - (dx + 1) / scale,
         0, 1 / scale_y, 1 - (dy + 1) / scale_y),
        resample=Image.Resampling.BILINEAR,
    ).convert("RGBA")
    return np.array(np.asarray(shifted)[::-1], copy=True, order="C"), x - 1, y - 1
