from dataclasses import dataclass

import numpy as np
from matplotlib.artist import Artist
from matplotlib.patches import PathPatch
from matplotlib.collections import PolyCollection
from matplotlib.backends.backend_agg import RendererAgg
from matplotlib.transforms import Affine2D
from renderer.subpixel import FloatImageCommand, raster_extent, rasterize_image_command


class SubpixelGradientCollection(PolyCollection):
    """Rasterize adjacent strips locally, then move their union continuously.

    AA on individual strips creates seams. A local transparent surface keeps
    their shared edges opaque while filtering only the final coverage mask.
    """

    def draw(self, renderer):
        if not self.get_visible() or not self.get_paths():
            return
        transform = self.get_transform()
        vertices = transform.transform(np.concatenate([p.vertices for p in self.get_paths()]))
        low, high = vertices.min(axis=0), vertices.max(axis=0)
        width, height = high - low
        if width <= 0 or height <= 0:
            return
        cols, rows = raster_extent(width), raster_extent(height)
        local = RendererAgg(cols + 2, rows + 2, renderer.dpi)
        local_transform = (transform + Affine2D().translate(-low[0], -low[1])
                           .scale(cols / width, rows / height).translate(1, 1))
        # The original axes clip is in global pixels, not in this local buffer.
        clip_box, clip_path, clip_on = self.get_clip_box(), self.get_clip_path(), self.get_clip_on()
        colors = self.get_facecolors().copy()
        opacity = 1.0
        if len(colors) and np.allclose(colors[:, 3], colors[0, 3]):
            opacity = float(colors[0, 3])
            opaque_colors = colors.copy()
            opaque_colors[:, 3] = 1.0
            self.set_facecolors(opaque_colors)
        try:
            self.set_transform(local_transform)
            self.set_clip_on(False)
            super().draw(local)
        finally:
            self.set_transform(transform)
            self.set_clip_box(clip_box)
            self.set_clip_path(clip_path)
            self.set_clip_on(clip_on)
            self.set_facecolors(colors)
        sx, sy = width / cols, height / rows
        pixels = np.array(local.buffer_rgba(), copy=True)[::-1]
        pixels[:, :, 3] = np.rint(pixels[:, :, 3] * opacity).astype(np.uint8)
        command = FloatImageCommand(pixels,
            low[0] - sx, renderer.height - high[1] - sy, sx, sy)
        pixels, left, top = rasterize_image_command(command)
        gc = renderer.new_gc()
        try:
            self._set_gc_clip(gc)
            renderer.draw_image(gc, left, int(renderer.height - top - pixels.shape[0]), pixels)
        finally:
            gc.restore()
        self.stale = False


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


@dataclass
class BarVisualGroupArtists:
    bar: BarArtists
    gradient: object = None
    advanced_shadow: object = None
    advanced_glow: object = None
    advanced_body: object = None
    logos: object = None
    text: object = None

    def depth_artists(self):
        return tuple(
            artist
            for artist in (
                self.advanced_glow,
                self.advanced_shadow,
                self.bar.shadow,
                self.bar.bar,
                self.gradient,
                self.advanced_body,
                self.bar.border,
                self.logos,
                self.text,
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
            for command in self.commands:
                image, left, top = rasterize_image_command(command)
                renderer.draw_image(
                    graphics_context,
                    int(left),
                    int(self.canvas_height - top - image.shape[0]),
                    image,
                )
        finally:
            graphics_context.restore()

        self.stale = False
