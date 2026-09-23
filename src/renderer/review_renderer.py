"""Logo placeholders retain real asset availability and outer dimensions."""
import numpy as np
from PIL import Image, ImageDraw
from renderer.bar_renderer import BarRenderer


class DraftReviewRenderer(BarRenderer):
    def _prepare_logo_image(self, logo_path, logo_size=None):
        availability = getattr(self, "_review_logo_availability", None)
        if availability is None:
            availability = self._review_logo_availability = {}
        if logo_path not in availability:
            try:
                with Image.open(logo_path) as source:
                    source.verify()
                availability[logo_path] = True
            except (OSError, ValueError):
                availability[logo_path] = False
        if not availability[logo_path]:
            raise ValueError("Unavailable logo")
        size = max(1, int(round(self.config.logo_size if logo_size is None else logo_size)))
        image = Image.new("RGBA", (size, size), "#E3E7EC")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, size - 1, size - 1), outline="#526172", width=max(1, size // 30))
        draw.line((0, 0, size - 1, size - 1), fill="#526172", width=max(1, size // 50))
        return np.asarray(image)
