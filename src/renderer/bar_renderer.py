import os
from dataclasses import dataclass, replace
from pathlib import Path as FilePath
from time import perf_counter

import matplotlib

matplotlib.use("Agg")

import matplotlib.colors as mcolors
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib.path import Path
from matplotlib.patches import PathPatch
from PIL import Image, ImageOps

from config.chart_config import ChartConfig
from utils.text_fit import estimate_text_width, fit_text_to_width
from utils.value_formatter import format_value


@dataclass
class _BarArtists:
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
        return tuple(artist for artist in (
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
        ) if artist is not None)


class BarRenderer:

    def __init__(self, output_dir="output", config=None):
        self.output_dir = output_dir
        self.config = config or ChartConfig()
        self.logo_cache = {}
        self._figure = None
        self._axis = None
        self._scene_artists_initialized = False
        self._title_artist = None
        self._subtitle_artist = None
        self._time_label_artist = None
        self._source_artist = None
        self._background_image_artist = None
        self._background_image_cache = None
        self._gradient_artist = None
        self._bar_artists = []
        self._advanced_fill_cache = {}
        self.draw_seconds = 0.0
        self.save_seconds = 0.0
        os.makedirs(self.output_dir, exist_ok=True)

    def render(self, scene, filename="frame.png"):
        fig = self._draw_scene(scene)

        path = os.path.join(self.output_dir, filename)
        save_started_at = perf_counter()
        fig.savefig(path, **self._savefig_kwargs(fig, path))
        self.save_seconds += perf_counter() - save_started_at

        return path

    def render_rgba(self, scene):
        fig = self._draw_scene(scene, draw_canvas=True)
        extract_started_at = perf_counter()
        rgba = bytes(fig.canvas.buffer_rgba())
        self.save_seconds += perf_counter() - extract_started_at
        return rgba

    def _draw_scene(self, scene, draw_canvas=False):
        fig, ax = self._figure_axis()
        draw_started_at = perf_counter()

        if not self._scene_artists_initialized:
            self._setup_canvas(fig, ax)
            self._initialize_scene_artists(ax)

        self._update_scene_artists(ax, scene)

        if draw_canvas:
            fig.canvas.draw()

        self.draw_seconds += perf_counter() - draw_started_at
        return fig

    def close(self):
        if self._figure is not None:
            plt.close(self._figure)
            self._figure = None
            self._axis = None
            self._scene_artists_initialized = False
            self._title_artist = None
            self._subtitle_artist = None
            self._time_label_artist = None
            self._source_artist = None
            self._background_image_artist = None
            self._background_image_cache = None
            self._gradient_artist = None
            self._bar_artists = []
            self._advanced_fill_cache = {}

    def _initialize_scene_artists(self, ax):
        self._initialize_background_artist(ax)
        self._title_artist = ax.text(
            self._title_x(),
            self.config.title_y,
            "",
            ha="left",
            va="center",
            fontsize=self.config.title_font_size,
            fontfamily=self._font_family(self.config.title_font_family),
            fontweight=self.config.title_font_weight,
            color=self.config.resolved_title_text_color,
            zorder=5,
        )
        self._subtitle_artist = ax.text(
            self._subtitle_x(),
            self.config.subtitle_y,
            "",
            ha="left",
            va="center",
            fontsize=self.config.subtitle_font_size,
            fontfamily=self._font_family(self.config.subtitle_font_family),
            fontweight=self.config.subtitle_font_weight,
            color=self.config.resolved_subtitle_text_color,
            zorder=5,
        )
        self._time_label_artist = ax.text(
            self.config.time_label_x,
            self.config.time_label_y,
            "",
            ha="right",
            va="center",
            fontsize=self.config.time_label_font_size,
            fontfamily=self._font_family(self.config.time_label_font_family),
            fontweight=self.config.time_label_font_weight,
            color=self.config.resolved_time_label_text_color,
            alpha=0.22,
            zorder=0,
        )
        self._source_artist = ax.text(
            self.config.source_x,
            self.config.source_y,
            "",
            ha="left",
            va="center",
            fontsize=self.config.source_font_size,
            fontfamily=self._font_family(self.config.source_font_family),
            fontweight=self.config.source_font_weight,
            color=self.config.resolved_source_text_color,
            zorder=5,
        )
        if self._uses_simple_gradient():
            self._gradient_artist = PolyCollection(
                [],
                closed=True,
                edgecolors="none",
                antialiaseds=False,
                zorder=2,
            )
            ax.add_collection(self._gradient_artist)
        self._scene_artists_initialized = True

    def _initialize_background_artist(self, ax):
        self._background_image_artist = None

        if (
            self.config.background_mode != "image"
            or not self.config.background_image_path
        ):
            return

        image = self._load_background_image()

        if image is None:
            return

        self._background_image_artist = ax.imshow(
            image,
            extent=(0, self.config.width, self.config.height, 0),
            aspect="auto",
            interpolation="bilinear",
            zorder=-10,
        )

    def _load_background_image(self):
        if self._background_image_cache is not None:
            return self._background_image_cache

        try:
            self._background_image_cache = self._prepare_background_image(
                self.config.background_image_path,
            )
        except (OSError, ValueError):
            self._background_image_cache = None

        return self._background_image_cache

    def _prepare_background_image(self, image_path):
        size = (max(1, self.config.width), max(1, self.config.height))

        with Image.open(image_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGBA")

            if self.config.background_image_fit == "contain":
                image = ImageOps.contain(
                    image,
                    size,
                    method=Image.Resampling.LANCZOS,
                )
                background_rgba = tuple(
                    round(channel * 255)
                    for channel in mcolors.to_rgba(self.config.background_color)
                )
                canvas = Image.new("RGBA", size, background_rgba)
                offset = (
                    (size[0] - image.width) // 2,
                    (size[1] - image.height) // 2,
                )
                canvas.alpha_composite(image, offset)
                image = canvas
            elif self.config.background_image_fit == "stretch":
                image = image.resize(size, Image.Resampling.LANCZOS)
            else:
                image = ImageOps.fit(
                    image,
                    size,
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )

        return np.asarray(image)

    def _update_scene_artists(self, ax, scene):
        self._set_text_artist(
            self._title_artist,
            self._fit_title(scene.title),
            visible=True,
        )
        self._set_text_artist(
            self._subtitle_artist,
            self._fit_subtitle(scene.subtitle) if scene.subtitle else "",
            visible=bool(scene.subtitle),
        )
        self._set_text_artist(
            self._time_label_artist,
            scene.time_label or "",
            visible=bool(scene.time_label),
        )
        self._set_text_artist(
            self._source_artist,
            self._fit_source_label(scene.source_label) if scene.source_label else "",
            visible=bool(scene.source_label),
        )

        self._ensure_bar_artist_capacity(ax, len(scene.bars))

        for artists, sprite in zip(self._bar_artists, scene.bars):
            self._update_bar_artists(artists, sprite)

        if self._uses_simple_gradient():
            self._update_gradient_artist(scene.bars)

        for artists in self._bar_artists[len(scene.bars):]:
            self._set_bar_artists_visible(artists, False)

    def _set_text_artist(self, artist, text, visible):
        artist.set_text(text)
        artist.set_visible(visible)

    def _uses_advanced_appearance(self):
        return self.config.bar_appearance_mode == "advanced"

    def _uses_simple_gradient(self):
        return (
            not self._uses_advanced_appearance()
            and self.config.bar_gradient_enabled
        )

    def _ensure_bar_artist_capacity(self, ax, count):
        while len(self._bar_artists) < count:
            self._bar_artists.append(self._create_bar_artists(ax))

    def _create_bar_artists(self, ax):
        empty_path = Path(np.empty((0, 2)))
        track = None
        glow = ()
        fill_clip = None
        fill_image = None

        if self._uses_advanced_appearance():
            track = PathPatch(empty_path, edgecolor="none", zorder=0.8)
            ax.add_patch(track)

        shadow = PathPatch(empty_path, edgecolor="none", zorder=1)
        ax.add_patch(shadow)

        if self._uses_advanced_appearance():
            bar = None
            glow = tuple(
                PathPatch(
                    empty_path,
                    facecolor="none",
                    edgecolor="none",
                    zorder=1.5 + (index * 0.01),
                )
                for index in range(3)
            )
            for glow_artist in glow:
                ax.add_patch(glow_artist)

            fill_clip = PathPatch(
                empty_path,
                facecolor="none",
                edgecolor="none",
                zorder=2,
            )
            ax.add_patch(fill_clip)
            fill_image = ax.imshow(
                np.zeros((2, 2, 4), dtype=np.float32),
                extent=(0, 0, 0, 0),
                aspect="auto",
                interpolation="bilinear",
                zorder=2,
            )
            fill_image.set_clip_path(fill_clip)
        elif self.config.bar_gradient_enabled:
            bar = None
        else:
            bar = PathPatch(empty_path, edgecolor="none", zorder=2)
            ax.add_patch(bar)

        border = PathPatch(
            empty_path,
            facecolor="none",
            edgecolor="none",
            zorder=2.5,
        )
        ax.add_patch(border)

        rank_label = ax.text(
            self._rank_label_x(),
            0,
            "",
            ha="right",
            va="center",
            fontsize=self.config.rank_label_font_size,
            fontfamily=self._font_family(self.config.rank_label_font_family),
            fontweight="bold",
            color=self.config.resolved_rank_label_text_color,
            zorder=4,
        )
        logo_background = PathPatch(
            empty_path,
            facecolor="none",
            edgecolor="none",
            zorder=2.9,
        )
        ax.add_patch(logo_background)
        logo_clip = PathPatch(
            empty_path,
            facecolor="none",
            edgecolor="none",
            zorder=3,
        )
        ax.add_patch(logo_clip)
        logo = ax.imshow(
            np.zeros((1, 1, 4), dtype=np.uint8),
            extent=(0, 0, 0, 0),
            zorder=3,
        )
        logo.set_clip_path(logo_clip)
        logo_border = PathPatch(
            empty_path,
            facecolor="none",
            edgecolor="none",
            zorder=3.2,
        )
        ax.add_patch(logo_border)
        name_label = ax.text(
            0,
            0,
            "",
            ha="right",
            va="center",
            fontsize=self.config.label_font_size,
            fontfamily=self._font_family(self.config.label_font_family),
            color=self.config.resolved_label_text_color,
            zorder=4,
        )
        value_label = ax.text(
            0,
            0,
            "",
            va="center",
            fontsize=self.config.value_font_size,
            fontfamily=self._font_family(self.config.value_font_family),
            zorder=4,
        )
        value_label.set_path_effects(self._value_path_effects())
        artists = _BarArtists(
            track=track,
            shadow=shadow,
            glow=glow,
            bar=bar,
            fill_clip=fill_clip,
            fill_image=fill_image,
            border=border,
            rank_label=rank_label,
            logo_background=logo_background,
            logo_clip=logo_clip,
            logo=logo,
            logo_border=logo_border,
            name_label=name_label,
            value_label=value_label,
        )
        self._set_bar_artists_visible(artists, False)
        return artists

    def _update_bar_artists(self, artists, sprite):
        opacity = self._opacity(sprite)

        if opacity <= 0:
            self._set_bar_artists_visible(artists, False)
            return

        alpha = min(1.0, max(0.25, sprite.width / self.config.max_bar_width))
        rgba = mcolors.to_rgba(sprite.color, alpha * opacity)
        bar_path = None

        if (
            self._uses_advanced_appearance()
            or not self.config.bar_gradient_enabled
            or self.config.bar_border_enabled
        ):
            bar_path = self._bar_shape_path(sprite)

        self._update_track_artist(artists.track, sprite, opacity)
        self._update_shadow_artist(artists.shadow, sprite, opacity)
        self._update_glow_artists(artists.glow, bar_path, opacity)
        self._update_advanced_fill_artists(
            artists.fill_clip,
            artists.fill_image,
            sprite,
            bar_path,
            alpha * opacity,
        )
        self._update_bar_artist(artists.bar, bar_path, rgba)
        self._update_border_artist(artists.border, bar_path, opacity)
        self._update_rank_artist(artists.rank_label, sprite, opacity)
        self._update_logo_artists(artists, sprite, opacity)

        name_layout = self._bar_label_layout(sprite)
        artists.name_label.set_position((name_layout["x"], name_layout["y"]))
        artists.name_label.set_horizontalalignment(name_layout["ha"])
        artists.name_label.set_verticalalignment(name_layout["va"])
        artists.name_label.set_color(name_layout["color"])
        artists.name_label.set_text(name_layout["text"])
        artists.name_label.set_alpha(opacity)
        artists.name_label.set_visible(True)

        value_text = format_value(sprite.value, value_format=self.config.value_format)
        value_layout = self._value_label_layout(sprite, value_text)
        artists.value_label.set_position((
            value_layout["x"],
            value_layout.get("y", sprite.y),
        ))
        artists.value_label.set_text(value_layout["text"])
        artists.value_label.set_horizontalalignment(value_layout["ha"])
        artists.value_label.set_verticalalignment(value_layout.get("va", "center"))
        artists.value_label.set_color(value_layout["color"])
        artists.value_label.set_alpha(opacity)
        artists.value_label.set_visible(True)

    def _update_shadow_artist(self, artist, sprite, opacity):
        shadow_alpha = max(0.0, min(1.0, self.config.bar_shadow_alpha))
        visible = self.config.bar_shadow_enabled and shadow_alpha > 0
        artist.set_visible(visible)

        if not visible:
            return

        artist.set_path(self._bar_shape_path(
            sprite,
            offset_x=self.config.bar_shadow_offset_x,
            offset_y=self.config.bar_shadow_offset_y,
        ))
        artist.set_facecolor(mcolors.to_rgba(
            self.config.bar_shadow_color,
            shadow_alpha * opacity,
        ))

    def _update_track_artist(self, artist, sprite, opacity):
        if artist is None:
            return

        visible = self.config.bar_track_enabled and self.config.bar_track_opacity > 0
        artist.set_visible(visible)

        if not visible:
            return

        track_sprite = replace(sprite, width=self.config.max_bar_width)
        artist.set_path(self._bar_shape_path(track_sprite))
        artist.set_facecolor(mcolors.to_rgba(
            self.config.bar_track_color,
            self.config.bar_track_opacity * opacity,
        ))

    def _update_glow_artists(self, artists, bar_path, opacity):
        if not artists:
            return

        visible = (
            self.config.bar_outer_glow_enabled
            and self.config.bar_glow_opacity > 0
            and self.config.bar_glow_blur > 0
        )

        for index, artist in enumerate(artists):
            artist.set_visible(visible)

            if not visible:
                continue

            spread = self.config.bar_glow_blur * ((index + 1) / len(artists))
            alpha = (
                self.config.bar_glow_opacity
                * opacity
                * (0.52 - (index * 0.13))
            )
            artist.set_path(bar_path)
            artist.set_linewidth(max(1.0, spread))
            artist.set_edgecolor(mcolors.to_rgba(
                self.config.bar_glow_color,
                max(0.0, alpha),
            ))

    def _update_advanced_fill_artists(
        self,
        clip_artist,
        image_artist,
        sprite,
        bar_path,
        opacity,
    ):
        if not self._uses_advanced_appearance():
            return

        clip_artist.set_path(bar_path)
        clip_artist.set_visible(True)
        image_artist.set_data(self._advanced_fill_image(sprite.color))
        image_artist.set_extent((
            sprite.x,
            sprite.x + sprite.width,
            sprite.y + (sprite.height / 2),
            sprite.y - (sprite.height / 2),
        ))
        image_artist.set_alpha(opacity)
        image_artist.set_visible(True)

    def _advanced_fill_image(self, category_color):
        cache_key = str(category_color).lower()
        cached = self._advanced_fill_cache.get(cache_key)

        if cached is not None:
            return cached

        height = 64
        width = 256
        x = np.linspace(0.0, 1.0, width)[None, :]
        y = np.linspace(0.0, 1.0, height)[:, None]
        fill = self._advanced_base_fill(category_color, x, y)
        texture_enabled = (
            self.config.bar_texture_enabled
            or self.config.bar_fill_type == "texture"
        )

        if texture_enabled and self.config.bar_texture_intensity > 0:
            texture = self._texture_pattern(width, height)
            fill = self._blend_texture(fill, texture)

        fill = self._apply_advanced_depth(fill, x, y)
        rgba = np.ones((height, width, 4), dtype=np.float32)
        rgba[:, :, :3] = np.clip(fill, 0.0, 1.0)
        self._advanced_fill_cache[cache_key] = rgba
        return rgba

    def _advanced_base_fill(self, category_color, x, y):
        start, center, end = self._advanced_fill_colors(category_color)

        if self.config.bar_fill_type in ("solid", "texture"):
            solid_color = (
                np.array(mcolors.to_rgb(category_color), dtype=np.float32)
                if self.config.bar_fill_use_category_color
                else start
            )
            fill = np.broadcast_to(
                solid_color,
                (y.shape[0], x.shape[1], 3),
            ).copy()
        else:
            if self.config.bar_gradient_direction == "vertical":
                progress = np.broadcast_to(y, (y.shape[0], x.shape[1]))
            elif self.config.bar_gradient_direction == "diagonal":
                progress = (x + y) / 2
            else:
                progress = np.broadcast_to(x, (y.shape[0], x.shape[1]))

            if self.config.bar_gradient_color_count == 2:
                fill = start + ((end - start) * progress[..., None])
            else:
                highlight = min(0.98, max(0.02, self.config.bar_highlight_position))
                before = np.clip(progress / highlight, 0.0, 1.0)[..., None]
                after = np.clip(
                    (progress - highlight) / (1.0 - highlight),
                    0.0,
                    1.0,
                )[..., None]
                first_half = start + ((center - start) * before)
                second_half = center + ((end - center) * after)
                fill = np.where(
                    (progress <= highlight)[..., None],
                    first_half,
                    second_half,
                )

        darkening = max(0.0, min(1.0, self.config.bar_edge_darkening))

        if darkening > 0:
            edge_mask = np.abs((x * 2) - 1) ** 2.4
            fill *= 1.0 - (darkening * edge_mask[..., None])

        return fill

    def _advanced_fill_colors(self, category_color):
        if not self.config.bar_fill_use_category_color:
            return tuple(
                np.array(mcolors.to_rgb(color), dtype=np.float32)
                for color in (
                    self.config.bar_fill_color_start,
                    self.config.bar_fill_color_center,
                    self.config.bar_fill_color_end,
                )
            )

        base = np.array(mcolors.to_rgb(category_color), dtype=np.float32)
        start = base * 0.76
        center = base + ((1.0 - base) * 0.3)
        return start, center, base

    def _texture_pattern(self, width, height):
        custom = self._custom_texture(width, height)

        if custom is not None:
            return custom

        scale = max(0.1, float(self.config.bar_texture_scale))
        seed = 1729
        rng = np.random.default_rng(seed)
        preset = self.config.bar_texture_preset

        if preset == "brushed_metal":
            source_height = max(2, round(height / scale))
            row_noise = np.asarray(
                Image.fromarray(np.uint8(rng.random((source_height, 1)) * 255)).resize(
                    (1, height),
                    Image.Resampling.BILINEAR,
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
                    (width, height),
                    Image.Resampling.BILINEAR,
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
        else:
            source_width = max(2, round(width / scale))
            source_height = max(2, round(height / scale))
            noise = rng.random((source_height, source_width))
            pattern = np.asarray(
                Image.fromarray(np.uint8(noise * 255)).resize(
                    (width, height),
                    Image.Resampling.NEAREST,
                ),
                dtype=np.float32,
            ) / 255

        contrast = max(0.0, float(self.config.bar_texture_contrast))
        return np.clip(0.5 + ((pattern - 0.5) * contrast), 0.0, 1.0)

    def _custom_texture(self, width, height):
        if self.config.bar_texture_preset != "custom_image":
            return None

        path_value = self.config.bar_texture_custom_image

        if not path_value:
            return None

        path = FilePath(path_value)

        try:
            with Image.open(path) as image:
                scale = max(0.1, float(self.config.bar_texture_scale))
                tile_width = max(1, round(width / scale))
                tile_height = max(1, round(height / scale))
                image = image.convert("RGB").resize(
                    (tile_width, tile_height),
                    Image.Resampling.BILINEAR,
                )
                tile = np.asarray(image, dtype=np.float32) / 255
                repeats_y = int(np.ceil(height / tile_height))
                repeats_x = int(np.ceil(width / tile_width))
                texture = np.tile(tile, (repeats_y, repeats_x, 1))[:height, :width]
        except (OSError, ValueError):
            return None

        contrast = max(0.0, float(self.config.bar_texture_contrast))
        return np.clip(0.5 + ((texture - 0.5) * contrast), 0.0, 1.0)

    def _blend_texture(self, fill, texture):
        if texture.ndim == 2:
            texture = texture[..., None]

        if texture.shape[-1] == 1:
            texture = np.repeat(texture, 3, axis=2)

        mode = self.config.bar_texture_blend_mode

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

        intensity = max(0.0, min(1.0, self.config.bar_texture_intensity))
        return fill + ((blended - fill) * intensity)

    def _apply_advanced_depth(self, fill, x, y):
        distance = np.minimum.reduce((
            np.broadcast_to(x, (y.shape[0], x.shape[1])),
            np.broadcast_to(1.0 - x, (y.shape[0], x.shape[1])),
            np.broadcast_to(y, (y.shape[0], x.shape[1])),
            np.broadcast_to(1.0 - y, (y.shape[0], x.shape[1])),
        ))

        if self.config.bar_bevel_enabled:
            size = max(0.01, self.config.bar_bevel_size)
            top = np.clip(1.0 - (y / size), 0.0, 1.0)
            left = np.clip(1.0 - (x / size), 0.0, 1.0)
            bottom = np.clip(1.0 - ((1.0 - y) / size), 0.0, 1.0)
            right = np.clip(1.0 - ((1.0 - x) / size), 0.0, 1.0)
            light = np.maximum(top, left) * self.config.bar_bevel_highlight_opacity
            shade = np.maximum(bottom, right) * self.config.bar_bevel_highlight_opacity * 0.72
            fill = fill + ((1.0 - fill) * light[..., None])
            fill *= 1.0 - shade[..., None]

        if self.config.bar_inner_shadow_opacity > 0:
            size = max(0.01, self.config.bar_inner_shadow_size)
            mask = np.clip(1.0 - (distance / size), 0.0, 1.0)
            fill *= 1.0 - (
                mask[..., None] * self.config.bar_inner_shadow_opacity
            )

        if self.config.bar_inner_glow_opacity > 0:
            mask = np.clip(1.0 - (distance / 0.14), 0.0, 1.0)
            amount = mask[..., None] * self.config.bar_inner_glow_opacity
            fill = fill + ((1.0 - fill) * amount)

        if self.config.bar_top_highlight_opacity > 0:
            mask = np.exp(-((y - 0.08) ** 2) / 0.0025)
            amount = mask[..., None] * self.config.bar_top_highlight_opacity
            fill = fill + ((1.0 - fill) * amount)

        if self.config.bar_bottom_shade_opacity > 0:
            mask = np.clip((y - 0.55) / 0.45, 0.0, 1.0)
            fill *= 1.0 - (
                mask[..., None] * self.config.bar_bottom_shade_opacity
            )

        if self.config.bar_shine_enabled and self.config.bar_shine_opacity > 0:
            coordinate = x + ((y - 0.5) * 0.18)
            width = max(0.01, self.config.bar_shine_width)
            mask = np.exp(-(
                (coordinate - self.config.bar_shine_position) ** 2
            ) / (2.0 * (width ** 2)))
            amount = mask[..., None] * self.config.bar_shine_opacity
            fill = fill + ((1.0 - fill) * amount)

        return np.clip(fill, 0.0, 1.0)

    def _update_bar_artist(self, artist, bar_path, rgba):
        if self._uses_advanced_appearance() or self.config.bar_gradient_enabled:
            return

        artist.set_path(bar_path)
        artist.set_facecolor(rgba)
        artist.set_visible(True)

    def _update_border_artist(self, artist, bar_path, opacity):
        width = max(0.0, float(self.config.bar_border_width))
        visible = self.config.bar_border_enabled and width > 0
        artist.set_visible(visible)

        if not visible:
            return

        artist.set_path(bar_path)
        artist.set_edgecolor(mcolors.to_rgba(
            self.config.bar_border_color,
            opacity,
        ))
        artist.set_linewidth(width)

    def _update_gradient_artist(self, sprites):
        vertices = []
        facecolors = []
        segment_count = 64

        for sprite in sprites:
            opacity = self._opacity(sprite)

            if opacity <= 0:
                continue

            alpha = min(1.0, max(0.25, sprite.width / self.config.max_bar_width))
            rgba = mcolors.to_rgba(sprite.color, alpha * opacity)
            gradient = self._bar_gradient(rgba)[0]
            edges = self._bar_gradient_edges(sprite, segment_count)

            for index in range(len(edges) - 1):
                left = edges[index]
                right = edges[index + 1]
                left_top, left_bottom = self._bar_vertical_bounds(sprite, left)
                right_top, right_bottom = self._bar_vertical_bounds(sprite, right)
                vertices.append((
                    (left, left_top),
                    (right, right_top),
                    (right, right_bottom),
                    (left, left_bottom),
                ))
                midpoint = (left + right) / 2
                progress = (midpoint - sprite.x) / max(1.0, sprite.width)
                facecolors.append(
                    gradient[0] + ((gradient[-1] - gradient[0]) * progress)
                )

        self._gradient_artist.set_verts(vertices, closed=True)
        self._gradient_artist.set_facecolors(facecolors)
        self._gradient_artist.set_visible(bool(vertices))

    def _bar_gradient_edges(self, sprite, segment_count):
        left = sprite.x
        right = sprite.x + sprite.width
        edges = np.linspace(left, right, segment_count + 1)

        if self.config.bar_shape in ("rounded", "capsule"):
            radius = self._bar_corner_radius(sprite.width, sprite.height)
            straight_edges = edges[
                (edges > left + radius) & (edges < right - radius)
            ]
            curved_edges = np.concatenate((
                np.linspace(left, left + radius, 17),
                np.linspace(right - radius, right, 17),
            ))
            edges = np.concatenate((straight_edges, curved_edges))
        elif self.config.bar_shape == "lollipop":
            center_x, radius, _ = self._lollipop_geometry(
                sprite.x,
                sprite.y,
                sprite.width,
                sprite.height,
            )
            circle_edges = np.linspace(center_x - radius, center_x + radius, 33)
            if self._lollipop_has_left_socket(sprite):
                left_circle_edges = np.linspace(
                    sprite.x,
                    sprite.x + (radius * 2),
                    33,
                )
                stem_edges = edges[
                    (edges > sprite.x + (radius * 2))
                    & (edges < center_x - radius)
                ]
                edges = np.concatenate((
                    left_circle_edges,
                    stem_edges,
                    circle_edges,
                ))
            else:
                stem_edges = edges[edges < center_x - radius]
                edges = np.concatenate((stem_edges, circle_edges))

        return np.unique(edges)

    def _bar_shape_path(self, sprite, offset_x=0, offset_y=0):
        left = sprite.x + offset_x
        center_y = sprite.y + offset_y
        width = max(0.0, sprite.width)
        height = max(0.0, sprite.height)

        if width <= 0 or height <= 0:
            return Path(np.empty((0, 2)))

        if self.config.bar_shape == "lollipop":
            vertices = self._lollipop_vertices(
                left,
                center_y,
                width,
                height,
                include_left_socket=self._lollipop_has_left_socket(sprite),
            )
        else:
            radius = self._bar_corner_radius(width, height)
            vertices = self._rounded_rectangle_vertices(
                left,
                center_y - (height / 2),
                width,
                height,
                radius,
            )

        closed_vertices = [*vertices, vertices[0]]
        codes = [Path.MOVETO, *([Path.LINETO] * (len(vertices) - 1)), Path.CLOSEPOLY]
        return Path(closed_vertices, codes)

    def _bar_corner_radius(self, width, height):
        if self.config.bar_shape == "rounded":
            return min(width / 2, height * 0.2)

        if self.config.bar_shape == "capsule":
            return min(width / 2, height / 2)

        return 0.0

    def _rounded_rectangle_vertices(self, left, top, width, height, radius):
        right = left + width
        bottom = top + height

        if radius <= 0:
            return [
                (left, top),
                (right, top),
                (right, bottom),
                (left, bottom),
            ]

        vertices = []
        corners = (
            (right - radius, top + radius, -90, 0),
            (right - radius, bottom - radius, 0, 90),
            (left + radius, bottom - radius, 90, 180),
            (left + radius, top + radius, 180, 270),
        )

        for center_x, center_y, start_angle, end_angle in corners:
            for angle in np.linspace(start_angle, end_angle, 7):
                radians = np.deg2rad(angle)
                vertices.append((
                    center_x + (radius * np.cos(radians)),
                    center_y + (radius * np.sin(radians)),
                ))

        return vertices

    def _lollipop_geometry(self, left, center_y, width, height):
        radius = min(height / 2, width / 2)
        center_x = left + width - radius
        stem_half_height = min(radius * 0.42, max(1.0, height * 0.11))
        return center_x, radius, stem_half_height

    def _lollipop_vertices(
        self,
        left,
        center_y,
        width,
        height,
        *,
        include_left_socket=None,
    ):
        center_x, radius, stem_half_height = self._lollipop_geometry(
            left,
            center_y,
            width,
            height,
        )

        if radius <= stem_half_height:
            return self._rounded_rectangle_vertices(
                left,
                center_y - radius,
                width,
                radius * 2,
                radius,
            )

        if include_left_socket is None:
            include_left_socket = self._lollipop_has_left_socket()

        if include_left_socket:
            right = left + width
            left_circle_edges = np.linspace(left, left + (radius * 2), 25)
            right_circle_edges = np.linspace(right - (radius * 2), right, 25)
            stem_edges = np.linspace(left, right, 33)
            edges = np.unique(np.concatenate((
                left_circle_edges,
                stem_edges,
                right_circle_edges,
            )))
            half_heights = [
                self._lollipop_half_height(
                    x,
                    left,
                    center_x,
                    radius,
                    stem_half_height,
                    include_left_socket=True,
                )
                for x in edges
            ]
            top = [
                (x, center_y - half_height)
                for x, half_height in zip(edges, half_heights)
            ]
            bottom = [
                (x, center_y + half_height)
                for x, half_height in reversed(tuple(zip(edges, half_heights)))
            ]
            return [*top, *bottom]

        angle = np.arcsin(stem_half_height / radius)
        intersection_x = center_x - np.sqrt(
            max(0.0, (radius ** 2) - (stem_half_height ** 2))
        )
        vertices = [
            (left, center_y - stem_half_height),
            (intersection_x, center_y - stem_half_height),
        ]

        arc_angles = np.concatenate((
            np.linspace(np.pi + angle, 1.5 * np.pi, 7, endpoint=False),
            np.linspace(1.5 * np.pi, 2 * np.pi, 7, endpoint=False),
            np.linspace(2 * np.pi, 2.5 * np.pi, 7, endpoint=False),
            np.linspace(2.5 * np.pi, (3 * np.pi) - angle, 7),
        ))

        for radians in arc_angles:
            vertices.append((
                center_x + (radius * np.cos(radians)),
                center_y + (radius * np.sin(radians)),
            ))

        vertices.extend((
            (intersection_x, center_y + stem_half_height),
            (left, center_y + stem_half_height),
        ))
        return vertices

    def _lollipop_has_left_socket(self, sprite=None):
        return (
            self._logo_position() == "inside_left"
            and (sprite is None or bool(sprite.logo_path))
        )

    def _lollipop_half_height(
        self,
        x,
        left,
        right_center_x,
        radius,
        stem_half_height,
        *,
        include_left_socket,
    ):
        right_circle_half_height = np.sqrt(max(
            0.0,
            (radius ** 2) - ((x - right_center_x) ** 2),
        ))
        stem_start_x = left + radius if include_left_socket else left
        stem_height = (
            stem_half_height
            if stem_start_x <= x <= right_center_x
            else 0.0
        )
        half_height = max(stem_height, right_circle_half_height)

        if include_left_socket:
            left_center_x = left + radius
            left_circle_half_height = np.sqrt(max(
                0.0,
                (radius ** 2) - ((x - left_center_x) ** 2),
            ))
            half_height = max(half_height, left_circle_half_height)

        return half_height

    def _bar_vertical_bounds(self, sprite, x):
        top = sprite.y - (sprite.height / 2)
        bottom = sprite.y + (sprite.height / 2)

        if self.config.bar_shape == "lollipop":
            center_x, radius, stem_half_height = self._lollipop_geometry(
                sprite.x,
                sprite.y,
                sprite.width,
                sprite.height,
            )
            half_height = self._lollipop_half_height(
                x,
                sprite.x,
                center_x,
                radius,
                stem_half_height,
                include_left_socket=self._lollipop_has_left_socket(sprite),
            )
            return sprite.y - half_height, sprite.y + half_height

        radius = self._bar_corner_radius(sprite.width, sprite.height)

        if radius <= 0:
            return top, bottom

        local_x = min(sprite.width, max(0.0, x - sprite.x))

        if local_x < radius:
            distance = radius - local_x
        elif local_x > sprite.width - radius:
            distance = local_x - (sprite.width - radius)
        else:
            return top, bottom

        inset = radius - np.sqrt(max(0.0, (radius ** 2) - (distance ** 2)))
        return top + inset, bottom - inset

    def _update_rank_artist(self, artist, sprite, opacity):
        visible = self.config.rank_labels_enabled and sprite.rank is not None
        artist.set_visible(visible)

        if not visible:
            return

        artist.set_position((self._rank_label_x(), sprite.y))
        artist.set_text(self._format_rank(sprite.rank))
        artist.set_alpha(opacity)

    def _update_logo_artists(self, artists, sprite, opacity):
        if not sprite.logo_path or self._logo_position() == "hidden":
            self._set_logo_artists_visible(artists, False)
            return

        image = self._load_logo(sprite.logo_path)
        layout = self._logo_layout(sprite)

        if image is None or layout is None:
            self._set_logo_artists_visible(artists, False)
            return

        logo_path = self._logo_shape_path(sprite, layout)
        artists.logo_clip.set_path(logo_path)
        artists.logo_clip.set_visible(True)

        artists.logo.set_data(image)
        artists.logo.set_extent((
            layout["left"],
            layout["right"],
            layout["bottom"],
            layout["top"],
        ))
        artists.logo.set_alpha(opacity)
        artists.logo.set_visible(True)

        background_opacity = max(
            0.0,
            min(1.0, float(self.config.bar_logo_background_opacity)),
        )
        background_visible = (
            self.config.bar_logo_background_enabled
            and background_opacity > 0
        )
        artists.logo_background.set_visible(background_visible)

        if background_visible:
            artists.logo_background.set_path(logo_path)
            artists.logo_background.set_facecolor(mcolors.to_rgba(
                self.config.bar_logo_background_color,
                background_opacity * opacity,
            ))

        border_width = max(0.0, float(self.config.bar_logo_border_width))
        border_visible = (
            self.config.bar_logo_border_enabled
            and border_width > 0
        )
        artists.logo_border.set_visible(border_visible)

        if border_visible:
            artists.logo_border.set_path(logo_path)
            artists.logo_border.set_edgecolor(mcolors.to_rgba(
                self.config.bar_logo_border_color,
                opacity,
            ))
            artists.logo_border.set_linewidth(border_width)

    def _set_logo_artists_visible(self, artists, visible):
        artists.logo_background.set_visible(visible)
        artists.logo_clip.set_visible(visible)
        artists.logo.set_visible(visible)
        artists.logo_border.set_visible(visible)

    def _logo_position(self):
        return {
            "outside": "outside_left",
            "inside": "inside_left",
        }.get(self.config.bar_logo_position, self.config.bar_logo_position)

    def _logo_layout(self, sprite):
        position = self._logo_position()

        if position == "hidden":
            return None

        if position == "outside_left":
            size = max(1.0, float(self.config.logo_size))
            right = sprite.x - self.config.logo_gap
            left = right - size
        else:
            padding = max(0.0, float(self.config.bar_logo_padding))
            available_width = max(0.0, sprite.width - (padding * 2))
            available_height = max(0.0, sprite.height - (padding * 2))

            if available_width <= 0 or available_height <= 0:
                return None

            size = min(
                float(self.config.logo_size),
                available_width,
                available_height,
            )

            if self.config.bar_shape == "lollipop":
                center_x, radius, _ = self._lollipop_geometry(
                    sprite.x,
                    sprite.y,
                    sprite.width,
                    sprite.height,
                )
                size = min(size, max(0.0, (radius * 2) - (padding * 2)))

                if size <= 0:
                    return None

                if position == "inside_left":
                    center_x = sprite.x + radius

                left = center_x - (size / 2)
                right = center_x + (size / 2)
            elif position == "inside_right":
                right = sprite.x + sprite.width - padding
                left = right - size
            else:
                left = sprite.x + padding
                right = left + size

        half_size = size / 2
        return {
            "left": left,
            "right": right,
            "top": sprite.y - half_size,
            "bottom": sprite.y + half_size,
            "size": size,
        }

    def _logo_shape_path(self, sprite, layout):
        shape = self.config.bar_logo_shape

        if shape == "adaptive":
            if self._logo_position() == "outside_left":
                shape = "square"
            elif self.config.bar_shape in ("capsule", "lollipop"):
                shape = "circle"
            elif self.config.bar_shape == "rounded":
                shape = "rounded"
            else:
                shape = "square"

        size = layout["size"]

        if shape == "circle":
            radius = size / 2
        elif shape == "rounded":
            radius = size * 0.2
        else:
            radius = 0.0

        vertices = self._rounded_rectangle_vertices(
            layout["left"],
            layout["top"],
            size,
            size,
            radius,
        )
        closed_vertices = [*vertices, vertices[0]]
        codes = [
            Path.MOVETO,
            *([Path.LINETO] * (len(vertices) - 1)),
            Path.CLOSEPOLY,
        ]
        return Path(closed_vertices, codes)

    def _value_path_effects(self):
        effects = []

        if self.config.bar_value_shadow_enabled:
            effects.append(path_effects.SimpleLineShadow(
                offset=(
                    self.config.bar_value_shadow_offset_x,
                    -self.config.bar_value_shadow_offset_y,
                ),
                shadow_color=self.config.bar_value_shadow_color,
                alpha=0.72,
            ))

        if (
            self.config.bar_value_border_enabled
            and self.config.bar_value_border_width > 0
        ):
            effects.append(path_effects.Stroke(
                linewidth=self.config.bar_value_border_width,
                foreground=self.config.bar_value_border_color,
            ))

        if effects:
            effects.append(path_effects.Normal())

        return effects

    def _set_bar_artists_visible(self, artists, visible):
        for artist in artists.all():
            artist.set_visible(visible)

    def _savefig_kwargs(self, fig, path):
        kwargs = {
            "dpi": self.config.dpi,
            "facecolor": fig.get_facecolor(),
            "bbox_inches": None,
            "pad_inches": 0,
        }

        if str(path).lower().endswith(".png"):
            kwargs["pil_kwargs"] = {
                "compress_level": self._png_compress_level(),
            }

        return kwargs

    def _png_compress_level(self):
        try:
            level = int(self.config.png_compress_level)
        except (TypeError, ValueError):
            return 1

        return min(9, max(0, level))

    def _figure_axis(self):
        if self._figure is None or self._axis is None:
            self._figure, self._axis = plt.subplots(
                figsize=self.config.figure_size,
                dpi=self.config.dpi,
            )

        return self._figure, self._axis

    def _setup_canvas(self, fig, ax):
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        ax.clear()
        ax.set_position((0, 0, 1, 1))
        fig.patch.set_facecolor(self.config.background_color)
        ax.set_facecolor(self.config.background_color)
        ax.set_xlim(0, self.config.width)
        ax.set_ylim(0, self.config.height)
        ax.invert_yaxis()
        ax.axis("off")

    def _draw_header(self, ax, scene):
        ax.text(
            self._title_x(),
            self.config.title_y,
            self._fit_title(scene.title),
            ha="left",
            va="center",
            fontsize=self.config.title_font_size,
            fontfamily=self._font_family(self.config.title_font_family),
            fontweight=self.config.title_font_weight,
            color=self.config.resolved_title_text_color,
            zorder=5,
        )

        if scene.subtitle:
            ax.text(
                self._subtitle_x(),
                self.config.subtitle_y,
                self._fit_subtitle(scene.subtitle),
                ha="left",
                va="center",
                fontsize=self.config.subtitle_font_size,
                fontfamily=self._font_family(self.config.subtitle_font_family),
                fontweight=self.config.subtitle_font_weight,
                color=self.config.resolved_subtitle_text_color,
                zorder=5,
            )

    def _fit_title(self, title):
        return self._fit_text(
            title,
            max_width=self._available_text_width(
                self._title_x(),
                self.config.title_max_width,
            ),
            font_size=self.config.title_font_size,
        )

    def _fit_subtitle(self, subtitle):
        return self._fit_text(
            subtitle,
            max_width=self._available_text_width(
                self._subtitle_x(),
                self.config.subtitle_max_width,
            ),
            font_size=self.config.subtitle_font_size,
        )

    def _title_x(self):
        if self.config.title_x is not None:
            return self.config.title_x

        return self.config.left_margin

    def _subtitle_x(self):
        if self.config.subtitle_x is not None:
            return self.config.subtitle_x

        return self.config.left_margin

    def _draw_bars(self, ax, sprites):
        for sprite in sprites:
            opacity = self._opacity(sprite)

            if opacity <= 0:
                continue

            alpha = min(1.0, max(0.25, sprite.width / self.config.max_bar_width))
            rgba = mcolors.to_rgba(sprite.color, alpha * opacity)

            self._draw_bar_shadow(ax, sprite, opacity)

            self._draw_bar(ax, sprite, rgba)

            self._draw_rank_label(ax, sprite, opacity)
            self._draw_logo(ax, sprite, opacity)

            name_layout = self._bar_label_layout(sprite)
            ax.text(
                name_layout["x"],
                name_layout["y"],
                name_layout["text"],
                ha=name_layout["ha"],
                va=name_layout["va"],
                fontsize=self.config.label_font_size,
                fontfamily=self._font_family(self.config.label_font_family),
                color=name_layout["color"],
                alpha=opacity,
                zorder=4,
            )

            value_text = format_value(
                sprite.value,
                value_format=self.config.value_format,
            )
            value_layout = self._value_label_layout(sprite, value_text)

            ax.text(
                value_layout["x"],
                sprite.y,
                value_layout["text"],
                ha=value_layout["ha"],
                va="center",
                fontsize=self.config.value_font_size,
                fontfamily=self._font_family(self.config.value_font_family),
                color=value_layout["color"],
                alpha=opacity,
                zorder=4,
            )

    def _draw_bar(self, ax, sprite, rgba):
        if not self.config.bar_gradient_enabled:
            self._draw_solid_bar(ax, sprite, rgba)
            return

        ax.imshow(
            self._bar_gradient(rgba),
            extent=(
                sprite.x,
                sprite.x + sprite.width,
                sprite.y + (sprite.height / 2),
                sprite.y - (sprite.height / 2),
            ),
            aspect="auto",
            interpolation="bicubic",
            zorder=2,
        )

    def _draw_solid_bar(self, ax, sprite, rgba):
        ax.barh(
            sprite.y,
            sprite.width,
            height=sprite.height,
            left=sprite.x,
            color=rgba,
            edgecolor="none",
            zorder=2,
        )

    def _bar_gradient(self, rgba):
        lighten = max(0.0, min(1.0, self.config.bar_gradient_lighten))
        start = np.array(rgba)
        end = start.copy()
        end[:3] = start[:3] + ((1.0 - start[:3]) * lighten)

        return np.linspace(start, end, 64).reshape(1, 64, 4)

    def _draw_bar_shadow(self, ax, sprite, opacity):
        if not self.config.bar_shadow_enabled:
            return

        shadow_alpha = max(0.0, min(1.0, self.config.bar_shadow_alpha))

        if shadow_alpha <= 0:
            return

        ax.barh(
            sprite.y + self.config.bar_shadow_offset_y,
            sprite.width,
            height=sprite.height,
            left=sprite.x + self.config.bar_shadow_offset_x,
            color=mcolors.to_rgba(
                self.config.bar_shadow_color,
                shadow_alpha * opacity,
            ),
            edgecolor="none",
            zorder=1,
        )

    def _draw_rank_label(self, ax, sprite, opacity):
        if not self.config.rank_labels_enabled:
            return

        if sprite.rank is None:
            return

        ax.text(
            self._rank_label_x(),
            sprite.y,
            self._format_rank(sprite.rank),
            ha="right",
            va="center",
            fontsize=self.config.rank_label_font_size,
            fontfamily=self._font_family(self.config.rank_label_font_family),
            fontweight="bold",
            color=self.config.resolved_rank_label_text_color,
            alpha=opacity,
            zorder=4,
        )

    def _rank_label_x(self):
        return max(
            self.config.rank_label_min_x,
            self.config.left_margin - self.config.rank_label_gap,
        )

    def _format_rank(self, rank):
        rounded_rank = max(1, round(rank))
        return f"{self.config.rank_label_prefix}{rounded_rank}"

    def _fit_bar_label(self, sprite):
        max_width = self._label_x(sprite) - self._bar_label_min_x(sprite)

        return fit_text_to_width(
            sprite.name,
            max_width=max_width,
            font_size=self._font_pixel_size(self.config.label_font_size),
            average_char_width=self.config.text_average_char_width,
        )

    def _bar_label_layout(self, sprite):
        position = (
            self.config.bar_label_position
            if self._uses_advanced_appearance()
            else "left"
        )

        if position == "inside":
            padding = 18
            x = sprite.x + padding
            right_limit = sprite.x + sprite.width - padding

            if sprite.logo_path:
                logo_layout = self._logo_layout(sprite)

                if logo_layout and self._logo_position() == "inside_left":
                    x = max(
                        x,
                        logo_layout["right"] + self.config.logo_label_gap,
                    )
                elif logo_layout and self._logo_position() == "inside_right":
                    right_limit = min(
                        right_limit,
                        logo_layout["left"] - self.config.logo_label_gap,
                    )

            max_width = max(0.0, right_limit - x)
            alignment, anchor_x = self._bar_label_alignment_anchor(
                x,
                right_limit,
                default="left",
            )
            return {
                "text": fit_text_to_width(
                    sprite.name,
                    max_width=max_width,
                    font_size=self._font_pixel_size(self.config.label_font_size),
                    average_char_width=self.config.text_average_char_width,
                ),
                "x": anchor_x,
                "y": sprite.y,
                "ha": alignment,
                "va": "center",
                "color": self._label_inside_color(),
            }

        if position == "above":
            alignment, anchor_x = self._bar_label_alignment_anchor(
                sprite.x,
                sprite.x + sprite.width,
                default="left",
            )
            return {
                "text": fit_text_to_width(
                    sprite.name,
                    max_width=max(0.0, sprite.width),
                    font_size=self._font_pixel_size(self.config.label_font_size),
                    average_char_width=self.config.text_average_char_width,
                ),
                "x": anchor_x,
                "y": sprite.y - (sprite.height / 2) - 7,
                "ha": alignment,
                "va": "bottom",
                "color": self.config.resolved_label_text_color,
            }

        if position == "outside":
            left = sprite.x + sprite.width + self.config.value_label_gap
            right = self.config.width - self.config.value_label_edge_padding
            stacked = self.config.bar_value_position in ("auto", "outside")
            alignment, anchor_x = self._bar_label_alignment_anchor(
                left,
                right,
                default="left",
            )
            return {
                "text": fit_text_to_width(
                    sprite.name,
                    max_width=max(0.0, right - left),
                    font_size=self._font_pixel_size(self.config.label_font_size),
                    average_char_width=self.config.text_average_char_width,
                ),
                "x": anchor_x,
                "y": sprite.y - ((sprite.height * 0.2) if stacked else 0),
                "ha": alignment,
                "va": "center",
                "color": self.config.resolved_label_text_color,
            }

        left = self._bar_label_min_x(sprite)
        right = self._label_x(sprite)
        alignment, anchor_x = self._bar_label_alignment_anchor(
            left,
            right,
            default="right",
        )
        return {
            "text": self._fit_bar_label(sprite),
            "x": anchor_x,
            "y": sprite.y,
            "ha": alignment,
            "va": "center",
            "color": self.config.resolved_label_text_color,
        }

    def _bar_label_alignment_anchor(self, left, right, *, default):
        alignment = self.config.bar_label_alignment

        if alignment == "auto":
            alignment = default

        right = max(left, right)

        if alignment == "center":
            return alignment, left + ((right - left) / 2)

        if alignment == "right":
            return alignment, right

        return "left", left

    def _bar_label_min_x(self, sprite):
        min_x = self.config.label_min_x

        if self.config.rank_labels_enabled and sprite.rank is not None:
            min_x = max(
                min_x,
                self._rank_label_x() + self.config.rank_label_label_gap,
            )

        return min_x

    def _value_label_layout(self, sprite, value_text):
        text = fit_text_to_width(
            value_text,
            max_width=self._value_label_max_width(),
            font_size=self._font_pixel_size(self.config.value_font_size),
            average_char_width=self.config.text_average_char_width,
        )
        text_width = self._value_label_text_width(text)
        max_right = self.config.width - self.config.value_label_edge_padding
        outside_x = sprite.x + sprite.width + self.config.value_label_gap

        if self._uses_advanced_appearance():
            position = self.config.bar_value_position
            custom_color = (
                self.config.value_text_color
                if self.config.bar_value_use_theme_color
                else self.config.bar_value_color
            )

            if position == "inside":
                inside_x = sprite.x + sprite.width - self.config.value_label_gap

                if sprite.logo_path and self._logo_position() == "inside_right":
                    logo_layout = self._logo_layout(sprite)

                    if logo_layout:
                        inside_x = min(
                            inside_x,
                            logo_layout["left"] - self.config.logo_label_gap,
                        )

                return {
                    "text": text,
                    "x": inside_x,
                    "y": sprite.y,
                    "ha": "right",
                    "va": "center",
                    "color": custom_color or self._value_label_inside_color(),
                }

            if position == "above":
                return {
                    "text": text,
                    "x": min(max_right, sprite.x + sprite.width),
                    "y": sprite.y - (sprite.height / 2) - 7,
                    "ha": "right",
                    "va": "bottom",
                    "color": custom_color or self.config.resolved_value_text_color,
                }

            if position == "outside":
                fits = outside_x + text_width <= max_right
                stacked = self.config.bar_label_position == "outside"
                return {
                    "text": text,
                    "x": outside_x if fits else max_right,
                    "y": sprite.y + ((sprite.height * 0.2) if stacked else 0),
                    "ha": "left" if fits else "right",
                    "va": "center",
                    "color": custom_color or self.config.resolved_value_text_color,
                }

        if outside_x + text_width <= max_right:
            layout = {
                "text": text,
                "x": outside_x,
                "y": sprite.y + (
                    (sprite.height * 0.2)
                    if (
                        self._uses_advanced_appearance()
                        and self.config.bar_label_position == "outside"
                    )
                    else 0
                ),
                "ha": "left",
                "color": self.config.resolved_value_text_color,
            }
            return self._custom_value_color(layout)

        inside_x = sprite.x + sprite.width - self.config.value_label_gap

        if sprite.logo_path and self._logo_position() == "inside_right":
            logo_layout = self._logo_layout(sprite)

            if logo_layout:
                inside_x = min(
                    inside_x,
                    logo_layout["left"] - self.config.logo_label_gap,
                )
        required_inside_width = text_width + (self.config.value_label_inside_padding * 2)

        if (
            self.config.bar_shape != "lollipop"
            and sprite.width >= required_inside_width
        ):
            layout = {
                "text": text,
                "x": inside_x,
                "ha": "right",
                "color": self._value_label_inside_color(),
            }
            return self._custom_value_color(layout)

        layout = {
            "text": text,
            "x": max_right,
            "ha": "right",
            "color": self.config.resolved_value_text_color,
        }
        return self._custom_value_color(layout)

    def _custom_value_color(self, layout):
        if (
            self._uses_advanced_appearance()
            and not self.config.bar_value_use_theme_color
        ):
            layout["color"] = self.config.bar_value_color
        elif self.config.value_text_color is not None:
            layout["color"] = self.config.resolved_value_text_color

        return layout

    def _value_label_max_width(self):
        max_right = self.config.width - self.config.value_label_edge_padding
        return max(0, max_right - self._value_label_min_x())

    def _value_label_text_width(self, text):
        return estimate_text_width(
            text,
            self._font_pixel_size(self.config.value_font_size),
            self.config.text_average_char_width,
        )

    def _value_label_min_x(self):
        if self.config.value_label_min_x is not None:
            return self.config.value_label_min_x

        max_right = self.config.width - self.config.value_label_edge_padding

        if self.config.left_margin < max_right:
            return self.config.left_margin

        return self.config.label_min_x

    def _value_label_inside_color(self):
        if self.config.value_text_color is not None:
            return self.config.resolved_value_text_color

        return self.config.value_label_inside_color or self.config.background_color

    def _label_inside_color(self):
        if self.config.label_text_color is not None:
            return self.config.resolved_label_text_color

        return self.config.value_label_inside_color or self.config.background_color

    def _draw_logo(self, ax, sprite, opacity):
        if not sprite.logo_path or self._logo_position() == "hidden":
            return

        image = self._load_logo(sprite.logo_path)
        layout = self._logo_layout(sprite)

        if image is None or layout is None:
            return

        logo_path = self._logo_shape_path(sprite, layout)

        if (
            self.config.bar_logo_background_enabled
            and self.config.bar_logo_background_opacity > 0
        ):
            ax.add_patch(PathPatch(
                logo_path,
                facecolor=mcolors.to_rgba(
                    self.config.bar_logo_background_color,
                    self.config.bar_logo_background_opacity * opacity,
                ),
                edgecolor="none",
                zorder=2.9,
            ))

        clip = PathPatch(
            logo_path,
            facecolor="none",
            edgecolor="none",
            zorder=3,
        )
        ax.add_patch(clip)

        artist = ax.imshow(
            image,
            extent=(
                layout["left"],
                layout["right"],
                layout["bottom"],
                layout["top"],
            ),
            zorder=3,
            alpha=opacity,
        )
        artist.set_clip_path(clip)

        if self.config.bar_logo_border_enabled and self.config.bar_logo_border_width > 0:
            ax.add_patch(PathPatch(
                logo_path,
                facecolor="none",
                edgecolor=mcolors.to_rgba(
                    self.config.bar_logo_border_color,
                    opacity,
                ),
                linewidth=self.config.bar_logo_border_width,
                zorder=3.2,
            ))

    def _label_x(self, sprite):
        if (
            not sprite.logo_path
            or self._logo_position() != "outside_left"
        ):
            return sprite.x - 16

        return (
            sprite.x
            - self.config.logo_gap
            - self.config.logo_size
            - self.config.logo_label_gap
        )

    def _load_logo(self, logo_path):
        cache_key = (logo_path, self.config.logo_size)

        if cache_key not in self.logo_cache:
            try:
                self.logo_cache[cache_key] = self._prepare_logo_image(logo_path)
            except (OSError, ValueError):
                self.logo_cache[cache_key] = None

        return self.logo_cache[cache_key]

    def _prepare_logo_image(self, logo_path):
        logo_size = max(1, int(self.config.logo_size))

        with Image.open(logo_path) as image:
            image = image.convert("RGBA")
            image.thumbnail(
                (logo_size, logo_size),
                Image.Resampling.LANCZOS,
            )
            canvas = Image.new("RGBA", (logo_size, logo_size), (255, 255, 255, 0))
            offset = (
                (logo_size - image.width) // 2,
                (logo_size - image.height) // 2,
            )
            canvas.alpha_composite(image, offset)

        return np.asarray(canvas)

    def _opacity(self, sprite):
        return min(1.0, max(0.0, sprite.opacity))

    def _draw_footer(self, ax, scene):
        self._draw_time_label(ax, scene)
        self._draw_source_label(ax, scene)

    def _draw_time_label(self, ax, scene):
        if scene.time_label:
            ax.text(
                self.config.time_label_x,
                self.config.time_label_y,
                scene.time_label,
                ha="right",
                va="center",
                fontsize=self.config.time_label_font_size,
                fontfamily=self._font_family(self.config.time_label_font_family),
                fontweight=self.config.time_label_font_weight,
                color=self.config.resolved_time_label_text_color,
                alpha=0.22,
                zorder=0,
            )

    def _draw_source_label(self, ax, scene):
        if scene.source_label:
            ax.text(
                self.config.source_x,
                self.config.source_y,
                self._fit_source_label(scene.source_label),
                ha="left",
                va="center",
                fontsize=self.config.source_font_size,
                fontfamily=self._font_family(self.config.source_font_family),
                fontweight=self.config.source_font_weight,
                color=self.config.resolved_source_text_color,
                zorder=5,
            )

    def _fit_source_label(self, source_label):
        return self._fit_text(
            source_label,
            max_width=self._available_text_width(
                self.config.source_x,
                self.config.source_max_width,
            ),
            font_size=self.config.source_font_size,
        )

    def _available_text_width(self, x, configured_max_width):
        right_edge = self.config.width - self.config.value_label_edge_padding
        available_width = right_edge - x

        return max(0, min(configured_max_width, available_width))

    def _fit_text(self, text, max_width, font_size):
        return fit_text_to_width(
            text,
            max_width=max_width,
            font_size=self._font_pixel_size(font_size),
            average_char_width=self.config.text_average_char_width,
        )

    def _font_pixel_size(self, font_size):
        return font_size * (self.config.dpi / 72)

    def _font_family(self, configured_family):
        return configured_family or self.config.font_family
