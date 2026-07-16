from dataclasses import dataclass

import numpy as np
from matplotlib.artist import Artist
from matplotlib.patches import PathPatch


@dataclass
class BarArtists:
    track: object
    shadow: PathPatch
    glow: tuple
    bar: object
    fill_clip: object
    fill_image: object
    border: PathPatch
    rank_label: object
    logo_background: PathPatch
    logo_clip: PathPatch
    logo: object
    logo_border: PathPatch
    name_label: object
    value_label: object

    def all(self):
        return tuple(
            artist
            for artist in (
                self.track,
                self.shadow,
                *self.glow,
                self.bar,
                self.fill_clip,
                self.fill_image,
                self.border,
                self.rank_label,
                self.logo_background,
                self.logo_clip,
                self.logo,
                self.logo_border,
                self.name_label,
                self.value_label,
            )
            if artist is not None
        )


@dataclass(frozen=True)
class TextSprite:
    image: np.ndarray
    anchor_x: float
    anchor_y: float


class StaticImageArtist(Artist):

    def __init__(self, image, *, left, top, canvas_height):
        super().__init__()
        self.image = np.array(
            np.asarray(image)[::-1],
            dtype=np.uint8,
            copy=True,
            order="C",
        )
        self.left = int(left)
        self.top = int(top)
        self.canvas_height = int(canvas_height)

    def get_extent(self):
        return (
            self.left,
            self.left + self.image.shape[1],
            self.top + self.image.shape[0],
            self.top,
        )

    def draw(self, renderer):
        if not self.get_visible():
            return

        graphics_context = renderer.new_gc()

        try:
            renderer.draw_image(
                graphics_context,
                self.left,
                self.canvas_height - self.top - self.image.shape[0],
                self.image,
            )
        finally:
            graphics_context.restore()

        self.stale = False


class ImageCommandsArtist(Artist):

    def __init__(self, canvas_height):
        super().__init__()
        self.canvas_height = canvas_height
        self.commands = ()

    def set_commands(self, commands):
        self.commands = tuple(commands)
        self.set_visible(bool(self.commands))
        self.stale = True

    def draw(self, renderer):
        if not self.get_visible():
            return

        graphics_context = renderer.new_gc()

        try:
            for image, left, top in self.commands:
                renderer.draw_image(
                    graphics_context,
                    int(left),
                    int(self.canvas_height - top - image.shape[0]),
                    image,
                )
        finally:
            graphics_context.restore()

        self.stale = False
