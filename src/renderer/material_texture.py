import numpy as np
from PIL import Image


def procedural_texture_pattern(
    width,
    height,
    *,
    preset,
    scale=1.0,
    contrast=1.0,
    seed=1729,
):
    """Return a deterministic 0..1 texture shared by bars and editorial cards."""
    width = max(1, int(width))
    height = max(1, int(height))
    scale = max(0.1, float(scale))
    rng = np.random.default_rng(seed)

    if preset == "brushed_metal":
        source_height = max(2, round(height / scale))
        row_noise = np.asarray(
            Image.fromarray(np.uint8(rng.random((source_height, 1)) * 255)).resize(
                (1, height), Image.Resampling.BILINEAR,
            ),
            dtype=np.float32,
        ) / 255
        fine = rng.random((height, width)) * 0.18
        pattern = (row_noise * 0.82) + fine
    elif preset == "grunge":
        small_width = max(4, round(18 * scale))
        small_height = max(3, round(7 * scale))
        coarse = rng.random((small_height, small_width))
        pattern = np.asarray(
            Image.fromarray(np.uint8(coarse * 255)).resize(
                (width, height), Image.Resampling.BILINEAR,
            ),
            dtype=np.float32,
        ) / 255
        pattern = (pattern * 0.78) + (rng.random((height, width)) * 0.22)
    elif preset == "paper":
        pattern = rng.normal(0.5, 0.09, (height, width))
        fiber_step = max(3, round(10 / scale))
        pattern[::fiber_step, :] += 0.12
    elif preset == "carbon":
        cell = max(2, round(8 / scale))
        rows, columns = np.indices((height, width))
        pattern = (((rows // cell) + (columns // cell)) % 2) * 0.42 + 0.29
        pattern += ((rows + columns) % max(2, cell)) / max(2, cell) * 0.12
    elif preset == "dots":
        cell = max(5, round(14 / scale))
        radius = max(1.0, cell * 0.16)
        rows, columns = np.indices((height, width))
        dx = (columns % cell) - (cell / 2)
        dy = (rows % cell) - (cell / 2)
        pattern = np.where((dx * dx) + (dy * dy) <= radius * radius, 0.28, 0.56)
    elif preset == "diagonal":
        cell = max(5, round(16 / scale))
        rows, columns = np.indices((height, width))
        line = ((rows + columns) % cell) < max(1, round(cell * 0.12))
        pattern = np.where(line, 0.3, 0.56)
    else:
        source_width = max(2, round(width / scale))
        source_height = max(2, round(height / scale))
        noise = rng.random((source_height, source_width))
        pattern = np.asarray(
            Image.fromarray(np.uint8(noise * 255)).resize(
                (width, height), Image.Resampling.NEAREST,
            ),
            dtype=np.float32,
        ) / 255

    contrast = max(0.0, float(contrast))
    return np.clip(0.5 + ((pattern - 0.5) * contrast), 0.0, 1.0)


def blend_texture(fill, texture, *, mode="overlay", intensity=1.0):
    """Blend a texture into RGB material while retaining the configured color."""
    fill = np.asarray(fill, dtype=np.float32)
    texture = np.asarray(texture, dtype=np.float32)
    if texture.ndim == 2:
        texture = texture[..., None]
    if texture.shape[-1] == 1:
        texture = np.repeat(texture, 3, axis=2)

    if mode == "multiply":
        blended = fill * texture
    elif mode == "screen":
        blended = 1.0 - ((1.0 - fill) * (1.0 - texture))
    elif mode == "soft_light":
        blended = ((1.0 - (2.0 * texture)) * (fill ** 2)) + (
            2.0 * texture * fill
        )
    else:
        blended = np.where(
            fill <= 0.5,
            2.0 * fill * texture,
            1.0 - (2.0 * (1.0 - fill) * (1.0 - texture)),
        )

    intensity = max(0.0, min(1.0, float(intensity)))
    return np.clip(fill + ((blended - fill) * intensity), 0.0, 1.0)
