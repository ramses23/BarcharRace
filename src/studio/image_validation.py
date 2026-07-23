from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError


class ImageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ImageFileInfo:
    path: Path
    format: str | None
    width: int
    height: int


def validate_image_file(path, *, field_name, original_value=None):
    """Validate that a path contains a decodable image without modifying it."""
    resolved = Path(path)
    context = _image_context(
        field_name=field_name,
        original_value=original_value,
        resolved=resolved,
    )

    if not resolved.exists():
        raise ImageValidationError(f"Image not found for {context}.")
    if not resolved.is_file():
        raise ImageValidationError(
            f"Image path is not a regular file for {context}."
        )

    try:
        with Image.open(resolved) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
        with Image.open(resolved) as image:
            image.load()
            decoded_width, decoded_height = image.size
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageValidationError(
            f"Image is corrupt or unsupported for {context}."
        ) from exc

    if (
        width <= 0
        or height <= 0
        or decoded_width <= 0
        or decoded_height <= 0
    ):
        raise ImageValidationError(
            f"Image has invalid dimensions for {context}: "
            f"{decoded_width}x{decoded_height}."
        )

    return ImageFileInfo(
        path=resolved,
        format=image_format,
        width=decoded_width,
        height=decoded_height,
    )


def _image_context(*, field_name, original_value, resolved):
    value = resolved if original_value is None else original_value
    return (
        f"{field_name}: value={str(value)!r}; "
        f"resolved path: {resolved}"
    )
