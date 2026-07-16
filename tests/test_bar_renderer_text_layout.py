import tempfile
import unittest
from pathlib import Path

import _test_path
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from config.chart_config import ChartConfig
from models.bar_sprite import BarSprite
from models.scene import Scene
from renderer.bar_renderer import BarRenderer


class BarRendererTextLayoutTest(unittest.TestCase):
    def test_fits_long_bar_label(self):
        renderer = BarRenderer(
            config=ChartConfig(
                dpi=72,
                label_font_size=20,
                label_min_x=40,
                text_average_char_width=0.5,
                logos_enabled=False,
            )
        )
        sprite = BarSprite(
            name="United States of America",
            value=100,
            color="#123456",
            x=200,
            y=0,
            width=100,
            height=40,
        )

        self.assertEqual(renderer._fit_bar_label(sprite), "United Stat...")

    def test_tracks_draw_and_save_seconds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            renderer = BarRenderer(output_dir=temp_dir, config=ChartConfig())
            scene = Scene(title="Title")
            renderer.render(scene, filename="frame.png")

        try:
            self.assertGreaterEqual(renderer.draw_seconds, 0.0)
            self.assertGreaterEqual(renderer.save_seconds, 0.0)
        finally:
            renderer.close()

    def test_png_save_kwargs_use_configured_compression_level(self):
        renderer = BarRenderer(config=ChartConfig(png_compress_level=0))
        fig = plt.figure()

        try:
            kwargs = renderer._savefig_kwargs(fig, "frame.png")

            self.assertEqual(kwargs["pil_kwargs"]["compress_level"], 0)
        finally:
            plt.close(fig)

    def test_png_save_kwargs_clamp_compression_level(self):
        renderer = BarRenderer(config=ChartConfig(png_compress_level=99))
        fig = plt.figure()

        try:
            kwargs = renderer._savefig_kwargs(fig, "frame.png")

            self.assertEqual(kwargs["pil_kwargs"]["compress_level"], 9)
        finally:
            plt.close(fig)

    def test_reuses_figure_until_closed(self):
        renderer = BarRenderer(config=ChartConfig())
        first_figure, first_axis = renderer._figure_axis()
        second_figure, second_axis = renderer._figure_axis()

        self.assertIs(first_figure, second_figure)
        self.assertIs(first_axis, second_axis)

        renderer.close()

        self.assertIsNone(renderer._figure)
        self.assertIsNone(renderer._axis)

    def test_reuses_scene_artists_between_rgba_frames(self):
        renderer = BarRenderer(
            config=ChartConfig(
                width=320,
                height=180,
                dpi=72,
                left_margin=100,
                right_margin=20,
                top_margin=40,
                bottom_margin=20,
                logos_enabled=False,
            )
        )
        first_scene = Scene(
            title="Race",
            subtitle="2000 -> 2001",
            time_label="2000",
            bars=[
                BarSprite(
                    name="USA",
                    value=100,
                    color="#123456",
                    x=100,
                    y=70,
                    width=180,
                    height=30,
                    rank=1,
                )
            ],
        )
        second_scene = Scene(
            title="Race",
            subtitle="2000 -> 2001",
            time_label="2001",
            bars=[
                BarSprite(
                    name="USA",
                    value=110,
                    color="#123456",
                    x=100,
                    y=65,
                    width=195,
                    height=30,
                    rank=1,
                )
            ],
        )

        try:
            first_rgba = renderer.render_rgba(first_scene)
            first_artists = renderer._bar_artists[0]
            first_gradient_artist = renderer._gradient_artist
            artist_counts = (
                len(renderer._axis.texts),
                len(renderer._axis.images),
                len(renderer._axis.patches),
            )

            second_rgba = renderer.render_rgba(second_scene)

            self.assertIs(renderer._bar_artists[0], first_artists)
            self.assertIs(renderer._gradient_artist, first_gradient_artist)
            self.assertEqual(len(renderer._gradient_artist.get_paths()), 64)
            self.assertEqual(len(renderer._gradient_artist.get_facecolors()), 64)
            self.assertEqual(
                (
                    len(renderer._axis.texts),
                    len(renderer._axis.images),
                    len(renderer._axis.patches),
                ),
                artist_counts,
            )
            self.assertNotEqual(first_rgba, second_rgba)
        finally:
            renderer.close()

    def test_applies_font_family_per_scene_element(self):
        renderer = BarRenderer(
            config=ChartConfig(
                width=320,
                height=180,
                dpi=72,
                left_margin=100,
                right_margin=20,
                title_font_family="DejaVu Serif",
                subtitle_font_family="DejaVu Sans Mono",
                time_label_font_family="DejaVu Serif",
                source_font_family="DejaVu Sans Mono",
                label_font_family="DejaVu Serif",
                value_font_family="DejaVu Sans Mono",
                rank_label_font_family="DejaVu Serif",
                title_text_color="#101112",
                subtitle_text_color="#202122",
                label_text_color="#303132",
                value_text_color="#404142",
                time_label_text_color="#505152",
                source_text_color="#606162",
                rank_label_text_color="#707172",
                title_font_size=41,
                subtitle_font_size=22,
                time_label_font_size=55,
                source_font_size=13,
                label_font_size=17,
                value_font_size=15,
                rank_label_font_size=12,
                title_x=25,
                title_y=20,
                subtitle_x=35,
                subtitle_y=42,
                time_label_x=280,
                time_label_y=150,
                source_x=30,
                source_y=165,
                logos_enabled=False,
            )
        )
        scene = Scene(
            title="Race",
            subtitle="Subtitle",
            time_label="2024",
            source_label="Source: Test",
            bars=[
                BarSprite(
                    name="Mexico",
                    value=100,
                    color="#123456",
                    x=100,
                    y=70,
                    width=180,
                    height=30,
                    rank=1,
                )
            ],
        )

        try:
            renderer.render_rgba(scene)
            bar_artists = renderer._bar_artists[0]

            self.assertEqual(renderer._title_artist.get_fontfamily(), ["DejaVu Serif"])
            self.assertEqual(
                renderer._subtitle_artist.get_fontfamily(),
                ["DejaVu Sans Mono"],
            )
            self.assertEqual(
                renderer._time_label_artist.get_fontfamily(),
                ["DejaVu Serif"],
            )
            self.assertEqual(
                renderer._source_artist.get_fontfamily(),
                ["DejaVu Sans Mono"],
            )
            self.assertEqual(bar_artists.name_label.get_fontfamily(), ["DejaVu Serif"])
            self.assertEqual(
                bar_artists.value_label.get_fontfamily(),
                ["DejaVu Sans Mono"],
            )
            self.assertEqual(bar_artists.rank_label.get_fontfamily(), ["DejaVu Serif"])
            self.assertEqual(renderer._title_artist.get_position(), (25, 20))
            self.assertEqual(renderer._subtitle_artist.get_position(), (35, 42))
            self.assertEqual(renderer._time_label_artist.get_position(), (280, 150))
            self.assertEqual(renderer._source_artist.get_position(), (30, 165))
            self.assertEqual(renderer._title_artist.get_fontsize(), 41)
            self.assertEqual(renderer._subtitle_artist.get_fontsize(), 22)
            self.assertEqual(renderer._time_label_artist.get_fontsize(), 55)
            self.assertEqual(renderer._source_artist.get_fontsize(), 13)
            self.assertEqual(bar_artists.name_label.get_fontsize(), 17)
            self.assertEqual(bar_artists.value_label.get_fontsize(), 15)
            self.assertEqual(bar_artists.rank_label.get_fontsize(), 12)
            self.assertEqual(renderer._title_artist.get_color(), "#101112")
            self.assertEqual(renderer._subtitle_artist.get_color(), "#202122")
            self.assertEqual(bar_artists.name_label.get_color(), "#303132")
            self.assertEqual(bar_artists.value_label.get_color(), "#404142")
            self.assertEqual(renderer._time_label_artist.get_color(), "#505152")
            self.assertEqual(renderer._source_artist.get_color(), "#606162")
            self.assertEqual(bar_artists.rank_label.get_color(), "#707172")
        finally:
            renderer.close()

    def test_canvas_axis_fills_entire_figure(self):
        renderer = BarRenderer(config=ChartConfig())
        fig, ax = plt.subplots()

        try:
            renderer._setup_canvas(fig, ax)

            self.assertEqual(
                tuple(round(value, 6) for value in ax.get_position().bounds),
                (0, 0, 1, 1),
            )
        finally:
            plt.close(fig)

    def test_font_pixel_size_uses_configured_dpi(self):
        renderer = BarRenderer(config=ChartConfig(dpi=144))

        self.assertEqual(renderer._font_pixel_size(12), 24)

    def test_bar_label_reserves_space_after_rank_label(self):
        renderer = BarRenderer(
            config=ChartConfig(
                dpi=72,
                left_margin=100,
                rank_label_gap=50,
                rank_label_min_x=20,
                rank_label_label_gap=20,
                label_font_size=10,
                label_min_x=10,
                text_average_char_width=0.5,
                logos_enabled=False,
            )
        )
        sprite = BarSprite(
            name="Very Long Label",
            value=100,
            color="#123456",
            x=120,
            y=0,
            width=100,
            height=40,
            rank=1,
        )

        self.assertEqual(renderer._rank_label_x(), 50)
        self.assertEqual(renderer._bar_label_min_x(sprite), 70)
        self.assertEqual(renderer._fit_bar_label(sprite), "Ver...")

    def test_bar_label_uses_label_min_x_when_rank_labels_are_disabled(self):
        renderer = BarRenderer(
            config=ChartConfig(
                dpi=72,
                left_margin=100,
                rank_labels_enabled=False,
                rank_label_gap=50,
                rank_label_min_x=20,
                rank_label_label_gap=80,
                label_font_size=10,
                label_min_x=10,
                text_average_char_width=0.5,
                logos_enabled=False,
            )
        )
        sprite = BarSprite(
            name="Very Long Label",
            value=100,
            color="#123456",
            x=120,
            y=0,
            width=100,
            height=40,
            rank=1,
        )

        self.assertEqual(renderer._bar_label_min_x(sprite), 10)
        self.assertEqual(renderer._fit_bar_label(sprite), "Very Long Label")

    def test_places_value_outside_when_it_fits(self):
        renderer = BarRenderer(
            config=ChartConfig(
                width=500,
                value_font_size=10,
                text_average_char_width=0.5,
                value_label_gap=10,
                value_label_edge_padding=20,
            )
        )
        sprite = BarSprite(
            name="USA",
            value=100,
            color="#123456",
            x=100,
            y=0,
            width=100,
            height=40,
        )

        layout = renderer._value_label_layout(sprite, "100")

        self.assertEqual(layout["x"], 210)
        self.assertEqual(layout["ha"], "left")
        self.assertEqual(layout["color"], renderer.config.muted_text_color)

    def test_places_value_inside_when_outside_would_overflow(self):
        renderer = BarRenderer(
            config=ChartConfig(
                width=300,
                value_font_size=10,
                text_average_char_width=0.5,
                value_label_gap=10,
                value_label_edge_padding=20,
                value_label_inside_padding=10,
            )
        )
        sprite = BarSprite(
            name="USA",
            value=100,
            color="#123456",
            x=60,
            y=0,
            width=220,
            height=40,
        )

        layout = renderer._value_label_layout(sprite, "100")

        self.assertEqual(layout["x"], 270)
        self.assertEqual(layout["ha"], "right")
        self.assertEqual(layout["color"], renderer.config.background_color)

    def test_clamps_value_when_bar_is_too_small_for_inside_label(self):
        renderer = BarRenderer(
            config=ChartConfig(
                width=220,
                value_font_size=20,
                text_average_char_width=0.5,
                value_label_gap=10,
                value_label_edge_padding=20,
                value_label_inside_padding=10,
            )
        )
        sprite = BarSprite(
            name="USA",
            value=100,
            color="#123456",
            x=160,
            y=0,
            width=20,
            height=40,
        )

        layout = renderer._value_label_layout(sprite, "100")

        self.assertEqual(layout["x"], 200)
        self.assertEqual(layout["ha"], "right")
        self.assertEqual(layout["color"], renderer.config.muted_text_color)

    def test_value_label_max_width_uses_data_area_left_edge(self):
        renderer = BarRenderer(
            config=ChartConfig(
                width=500,
                left_margin=120,
                value_label_edge_padding=20,
            )
        )

        self.assertEqual(renderer._value_label_min_x(), 120)
        self.assertEqual(renderer._value_label_max_width(), 360)

    def test_value_label_max_width_uses_configured_left_edge(self):
        renderer = BarRenderer(
            config=ChartConfig(
                width=500,
                left_margin=120,
                value_label_min_x=180,
                value_label_edge_padding=20,
            )
        )

        self.assertEqual(renderer._value_label_min_x(), 180)
        self.assertEqual(renderer._value_label_max_width(), 300)

    def test_value_label_max_width_falls_back_for_tiny_canvas(self):
        renderer = BarRenderer(
            config=ChartConfig(
                width=220,
                left_margin=320,
                label_min_x=40,
                value_label_edge_padding=20,
            )
        )

        self.assertEqual(renderer._value_label_min_x(), 40)
        self.assertEqual(renderer._value_label_max_width(), 160)

    def test_truncates_very_large_value_to_safe_value_area(self):
        renderer = BarRenderer(
            config=ChartConfig(
                dpi=72,
                width=300,
                left_margin=100,
                value_label_min_x=120,
                value_font_size=10,
                text_average_char_width=0.5,
                value_label_gap=10,
                value_label_edge_padding=20,
                value_label_inside_padding=10,
            )
        )
        sprite = BarSprite(
            name="USA",
            value=100,
            color="#123456",
            x=260,
            y=0,
            width=5,
            height=40,
        )

        layout = renderer._value_label_layout(sprite, "1234567890" * 5)

        self.assertEqual(layout["x"], 280)
        self.assertEqual(layout["ha"], "right")
        self.assertTrue(layout["text"].endswith("..."))
        self.assertLessEqual(
            renderer._value_label_text_width(layout["text"]),
            renderer._value_label_max_width(),
        )

    def test_draws_bar_shadow_with_configured_offset(self):
        renderer = BarRenderer(
            config=ChartConfig(
                bar_shadow_color="#111111",
                bar_shadow_alpha=0.5,
                bar_shadow_offset_x=7,
                bar_shadow_offset_y=3,
            )
        )
        axis = FakeAxis()
        sprite = BarSprite(
            name="USA",
            value=100,
            color="#123456",
            x=100,
            y=40,
            width=200,
            height=30,
        )

        renderer._draw_bar_shadow(axis, sprite, opacity=0.8)

        self.assertEqual(len(axis.barh_calls), 1)
        self.assertEqual(axis.barh_calls[0]["y"], 43)
        self.assertEqual(axis.barh_calls[0]["width"], 200)
        self.assertEqual(axis.barh_calls[0]["height"], 30)
        self.assertEqual(axis.barh_calls[0]["left"], 107)
        self.assertEqual(axis.barh_calls[0]["zorder"], 1)
        self.assertAlmostEqual(axis.barh_calls[0]["color"][3], 0.4)

    def test_skips_bar_shadow_when_disabled(self):
        renderer = BarRenderer(config=ChartConfig(bar_shadow_enabled=False))
        axis = FakeAxis()
        sprite = BarSprite(
            name="USA",
            value=100,
            color="#123456",
            x=100,
            y=40,
            width=200,
            height=30,
        )

        renderer._draw_bar_shadow(axis, sprite, opacity=1.0)

        self.assertEqual(axis.barh_calls, [])

    def test_draws_gradient_bar_when_enabled(self):
        renderer = BarRenderer(
            config=ChartConfig(
                bar_gradient_enabled=True,
                bar_gradient_lighten=0.25,
            )
        )
        axis = FakeAxis()
        sprite = BarSprite(
            name="USA",
            value=100,
            color="#123456",
            x=100,
            y=40,
            width=200,
            height=30,
        )

        renderer._draw_bar(axis, sprite, rgba=(0.1, 0.2, 0.3, 0.8))

        self.assertEqual(axis.barh_calls, [])
        self.assertEqual(len(axis.imshow_calls), 1)
        self.assertEqual(axis.imshow_calls[0]["extent"], (100, 300, 55.0, 25.0))
        self.assertEqual(axis.imshow_calls[0]["zorder"], 2)
        self.assertEqual(axis.imshow_calls[0]["image"].shape, (1, 64, 4))
        self.assertAlmostEqual(axis.imshow_calls[0]["image"][0, 0, 0], 0.1)
        self.assertAlmostEqual(axis.imshow_calls[0]["image"][0, -1, 0], 0.325)
        self.assertAlmostEqual(axis.imshow_calls[0]["image"][0, -1, 3], 0.8)

    def test_draws_solid_bar_when_gradient_is_disabled(self):
        renderer = BarRenderer(config=ChartConfig(bar_gradient_enabled=False))
        axis = FakeAxis()
        sprite = BarSprite(
            name="USA",
            value=100,
            color="#123456",
            x=100,
            y=40,
            width=200,
            height=30,
        )

        renderer._draw_bar(axis, sprite, rgba=(0.1, 0.2, 0.3, 0.8))

        self.assertEqual(axis.imshow_calls, [])
        self.assertEqual(len(axis.barh_calls), 1)
        self.assertEqual(axis.barh_calls[0]["y"], 40)
        self.assertEqual(axis.barh_calls[0]["width"], 200)
        self.assertEqual(axis.barh_calls[0]["height"], 30)
        self.assertEqual(axis.barh_calls[0]["left"], 100)
        self.assertEqual(axis.barh_calls[0]["color"], (0.1, 0.2, 0.3, 0.8))
        self.assertEqual(axis.barh_calls[0]["zorder"], 2)

    def test_fits_title_subtitle_and_source_labels(self):
        renderer = BarRenderer(
            config=ChartConfig(
                dpi=72,
                title_font_size=10,
                subtitle_font_size=10,
                source_font_size=10,
                text_average_char_width=0.5,
                title_max_width=60,
                subtitle_max_width=40,
                source_max_width=50,
            )
        )

        self.assertEqual(
            renderer._fit_title("Professional Bar Chart Race"),
            "Professio...",
        )
        self.assertEqual(
            renderer._fit_subtitle("Subtitle that is too long"),
            "Subti...",
        )
        self.assertEqual(
            renderer._fit_source_label("Source: very/long/path/to/source.csv"),
            "Source:...",
        )

    def test_fits_main_text_to_available_canvas_width(self):
        renderer = BarRenderer(
            config=ChartConfig(
                dpi=72,
                width=220,
                left_margin=100,
                source_x=120,
                value_label_edge_padding=20,
                title_font_size=10,
                source_font_size=10,
                text_average_char_width=0.5,
                title_max_width=500,
                source_max_width=500,
            )
        )

        self.assertEqual(
            renderer._available_text_width(100, 500),
            100,
        )
        self.assertEqual(
            renderer._available_text_width(120, 500),
            80,
        )
        self.assertEqual(
            renderer._fit_title("A Very Long Narrow Canvas Title"),
            "A Very Long Narro...",
        )
        self.assertEqual(
            renderer._fit_source_label("Source: extremely/long/path.csv"),
            "Source: extre...",
        )

    def test_available_text_width_never_goes_negative(self):
        renderer = BarRenderer(
            config=ChartConfig(
                width=200,
                value_label_edge_padding=30,
            )
        )

        self.assertEqual(renderer._available_text_width(250, 500), 0)

    def test_header_uses_configured_font_weights(self):
        renderer = BarRenderer(
            config=ChartConfig(
                title_font_weight="heavy",
                subtitle_font_weight="light",
            )
        )
        axis = FakeAxis()
        scene = Scene(title="Title", subtitle="Subtitle")

        renderer._draw_header(axis, scene)

        self.assertEqual(axis.text_calls[0]["text"], "Title")
        self.assertEqual(axis.text_calls[0]["fontweight"], "heavy")
        self.assertEqual(axis.text_calls[1]["text"], "Subtitle")
        self.assertEqual(axis.text_calls[1]["fontweight"], "light")

    def test_load_logo_resizes_and_caches_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / "large_logo.png"
            Image.new("RGBA", (240, 120), (255, 0, 0, 255)).save(logo_path)
            renderer = BarRenderer(config=ChartConfig(logo_size=32))

            image = renderer._load_logo(str(logo_path))
            cached_image = renderer._load_logo(str(logo_path))

        self.assertEqual(image.shape, (32, 32, 4))
        self.assertEqual(str(image.dtype), "uint8")
        self.assertIs(image, cached_image)

    def test_reused_logo_composite_uses_the_cached_sprite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / "logo.png"
            Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(logo_path)
            renderer = BarRenderer(config=ChartConfig(
                width=320,
                height=180,
                dpi=72,
                left_margin=100,
                right_margin=20,
                top_margin=40,
                bottom_margin=20,
                bar_appearance_mode="advanced",
                logo_size=32,
            ))
            scene = Scene(
                title="Logo",
                bars=[
                    BarSprite(
                        name="Example",
                        value=100,
                        color="#4E79A7",
                        x=100,
                        y=90,
                        width=160,
                        height=36,
                        rank=1,
                        logo_path=str(logo_path),
                    )
                ],
            )

            try:
                renderer.render_rgba(scene)
                first_command = renderer._logo_composite_artist.commands[0]
                sprite_cache_size = len(renderer._logo_sprite_cache)
                renderer.render_rgba(scene)
                second_command = renderer._logo_composite_artist.commands[0]

                self.assertIs(first_command[0], second_command[0])
                self.assertEqual(len(renderer._logo_sprite_cache), sprite_cache_size)
                self.assertIsNone(renderer._bar_artists[0].logo)
            finally:
                renderer.close()

    def test_text_compositor_reuses_static_rank_category_and_value_sprites(self):
        renderer = BarRenderer(config=ChartConfig(
            width=640,
            height=180,
            dpi=72,
            left_margin=220,
            right_margin=20,
            top_margin=40,
            bottom_margin=20,
            logos_enabled=False,
        ))
        scene = Scene(
            title="Cached title",
            bars=[
                BarSprite(
                    name="Mexico",
                    value=100,
                    color="#4E79A7",
                    x=220,
                    y=90,
                    width=320,
                    height=36,
                    rank=1,
                )
            ],
        )

        try:
            renderer.render_rgba(scene)
            first_foreground = renderer._text_foreground_artist.commands[0][0]
            first_bar_images = tuple(
                command[0]
                for command in renderer._text_bar_artist.commands
            )
            cache_size = len(renderer._text_sprite_cache)

            renderer.render_rgba(scene)
            second_bar_images = tuple(
                command[0]
                for command in renderer._text_bar_artist.commands
            )

            self.assertIs(
                renderer._text_foreground_artist.commands[0][0],
                first_foreground,
            )
            self.assertEqual(len(first_bar_images), 3)
            self.assertTrue(all(
                first is second
                for first, second in zip(first_bar_images, second_bar_images)
            ))
            self.assertEqual(len(renderer._text_sprite_cache), cache_size)
            self.assertFalse(renderer._title_artist.get_visible())
            self.assertFalse(renderer._bar_artists[0].name_label.get_visible())
        finally:
            renderer.close()

    def test_text_compositor_preserves_upright_vertical_orientation(self):
        renderer = BarRenderer(config=ChartConfig(
            width=180,
            height=120,
            dpi=72,
            title_x=40,
            title_y=55,
            title_font_size=56,
            title_font_family="DejaVu Sans",
            title_text_color="#000000",
            logos_enabled=False,
        ))

        try:
            rgba = np.frombuffer(
                renderer.render_rgba(Scene(title="L")),
                dtype=np.uint8,
            ).reshape((120, 180, 4))
            dark = np.all(rgba[:, :, :3] < 80, axis=2)
            y_values, x_values = np.where(dark)
            relevant = (
                (x_values >= 35)
                & (x_values <= 100)
                & (y_values >= 10)
                & (y_values <= 95)
            )
            text_y = y_values[relevant]
            midpoint = (int(text_y.min()) + int(text_y.max())) // 2

            self.assertGreater(
                int(np.count_nonzero(text_y > midpoint)),
                int(np.count_nonzero(text_y <= midpoint)),
            )
        finally:
            renderer.close()

    def test_text_sprite_cache_preserves_value_border_and_shadow_style(self):
        renderer = BarRenderer(config=ChartConfig(dpi=72))
        style = {
            "ha": "right",
            "va": "center",
            "font_size": 24,
            "font_family": "DejaVu Sans",
            "font_weight": "normal",
            "color": "#FFFFFF",
            "stroke_width": 2,
            "stroke_color": "#112233",
            "shadow_offset": (4, 3),
            "shadow_color": "#000000",
            "shadow_opacity": 0.72,
        }

        styled = renderer._cached_text_sprite("125.0", **style)
        cached = renderer._cached_text_sprite("125.0", **style)
        plain = renderer._cached_text_sprite(
            "125.0",
            **{
                **style,
                "stroke_width": 0,
                "shadow_offset": None,
                "shadow_opacity": 0,
            },
        )

        self.assertIs(styled, cached)
        self.assertGreaterEqual(styled.image.shape[0], plain.image.shape[0])
        self.assertGreater(styled.image.shape[1], plain.image.shape[1])
        self.assertGreater(int(styled.image[:, :, 3].max()), 0)
        self.assertTrue(styled.image.flags.c_contiguous)

    def test_logo_compositor_supports_modes_positions_and_shapes(self):
        cases = (
            ("outside_left", "adaptive", "rectangle", "square"),
            ("inside_left", "adaptive", "lollipop", "circle"),
            ("inside_right", "adaptive", "capsule", "circle"),
            ("inside_right", "adaptive", "rounded", "rounded"),
            ("inside_right", "square", "capsule", "square"),
            ("hidden", "circle", "capsule", "circle"),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / "logo.png"
            Image.new("RGBA", (32, 32), (225, 40, 60, 255)).save(logo_path)
            scene = Scene(
                title="Logo",
                bars=[
                    BarSprite(
                        name="Example",
                        value=100,
                        color="#4E79A7",
                        x=100,
                        y=90,
                        width=160,
                        height=36,
                        rank=1,
                        logo_path=str(logo_path),
                    )
                ],
            )

            for appearance_mode in ("simple", "advanced"):
                for position, logo_shape, bar_shape, resolved_shape in cases:
                    with self.subTest(
                        appearance_mode=appearance_mode,
                        position=position,
                        logo_shape=logo_shape,
                        bar_shape=bar_shape,
                    ):
                        renderer = BarRenderer(config=ChartConfig(
                            width=320,
                            height=180,
                            dpi=72,
                            left_margin=100,
                            right_margin=20,
                            top_margin=40,
                            bottom_margin=20,
                            bar_appearance_mode=appearance_mode,
                            bar_logo_position=position,
                            bar_logo_shape=logo_shape,
                            bar_shape=bar_shape,
                            logo_size=32,
                        ))

                        try:
                            rgba = renderer.render_rgba(scene)
                            commands = renderer._logo_composite_artist.commands

                            self.assertEqual(len(rgba), 320 * 180 * 4)
                            self.assertEqual(
                                len(commands),
                                0 if position == "hidden" else 1,
                            )
                            self.assertEqual(
                                renderer._resolved_logo_shape(),
                                resolved_shape,
                            )

                            if commands:
                                self.assertGreater(int(commands[0][0][:, :, 3].max()), 0)
                                self.assertTrue(commands[0][0].flags.c_contiguous)
                        finally:
                            renderer.close()

    def test_logo_compositor_supports_two_logos_in_all_layout_modes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            primary_path = Path(temp_dir) / "primary.png"
            secondary_path = Path(temp_dir) / "secondary.png"
            Image.new("RGBA", (48, 48), (225, 40, 60, 255)).save(primary_path)
            Image.new("RGBA", (48, 48), (40, 120, 225, 255)).save(secondary_path)
            sprite = BarSprite(
                name="Example",
                value=100,
                color="#4E79A7",
                x=100,
                y=90,
                width=180,
                height=40,
                rank=1,
                logo_path=str(primary_path),
                secondary_logo_path=str(secondary_path),
            )

            cases = (
                ("badge", "inside_left"),
                ("side_by_side", "inside_left"),
                ("independent", "inside_right"),
            )
            for layout_mode, secondary_position in cases:
                with self.subTest(layout_mode=layout_mode):
                    renderer = BarRenderer(config=ChartConfig(
                        width=360,
                        height=180,
                        dpi=72,
                        bar_logo_position=(
                            "outside_left"
                            if layout_mode == "independent"
                            else "inside_left"
                        ),
                        logo_size=32,
                        bar_secondary_logo_enabled=True,
                        bar_secondary_logo_layout=layout_mode,
                        bar_secondary_logo_position=secondary_position,
                        bar_secondary_logo_size=18,
                        bar_secondary_logo_gap=5,
                    ))

                    try:
                        renderer.render_rgba(Scene(title="", bars=[sprite]))
                        layouts = renderer._logo_layouts_for_sprite(sprite)

                        self.assertEqual(len(layouts), 2)
                        self.assertEqual(len(renderer._logo_composite_artist.commands), 2)
                        self.assertEqual([item[0] for item in layouts], ["primary", "secondary"])

                        primary_layout = layouts[0][2]
                        secondary_layout = layouts[1][2]
                        if layout_mode == "badge":
                            self.assertLess(secondary_layout["left"], primary_layout["right"])
                            self.assertGreater(secondary_layout["right"], primary_layout["left"])
                        elif layout_mode == "side_by_side":
                            self.assertGreaterEqual(
                                secondary_layout["left"],
                                primary_layout["right"] + 5,
                            )
                        else:
                            self.assertLess(primary_layout["right"], sprite.x)
                            self.assertGreaterEqual(secondary_layout["left"], sprite.x)
                            self.assertLessEqual(
                                secondary_layout["right"],
                                sprite.x + sprite.width,
                            )

                        cache_slots = {key[1] for key in renderer._logo_sprite_cache}
                        self.assertEqual(cache_slots, {"primary", "secondary"})
                    finally:
                        renderer.close()

    def test_disabling_second_logo_keeps_primary_logo(self):
        sprite = BarSprite(
            name="Example",
            value=100,
            color="#4E79A7",
            x=100,
            y=90,
            width=180,
            height=40,
            logo_path="primary.png",
            secondary_logo_path="secondary.png",
        )
        renderer = BarRenderer(config=ChartConfig(
            bar_secondary_logo_enabled=False,
        ))

        layouts = renderer._logo_layouts_for_sprite(sprite)

        self.assertEqual(len(layouts), 1)
        self.assertEqual(layouts[0][0], "primary")

    def test_logo_compositor_preserves_vertical_orientation_and_opacity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / "oriented_logo.png"
            logo = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
            logo.paste((0, 0, 255, 255), (0, 16, 32, 32))
            logo.save(logo_path)
            renderer = BarRenderer(config=ChartConfig(
                width=240,
                height=160,
                dpi=72,
                left_margin=100,
                right_margin=20,
                top_margin=30,
                bottom_margin=20,
                bar_logo_position="outside_left",
                bar_logo_shape="square",
                logo_size=32,
                logo_gap=8,
            ))
            sprite = BarSprite(
                name="Example",
                value=100,
                color="#4E79A7",
                x=100,
                y=80,
                width=100,
                height=32,
                rank=1,
                logo_path=str(logo_path),
                opacity=0.5,
            )

            try:
                rgba = np.frombuffer(
                    renderer.render_rgba(Scene(title="", bars=[sprite])),
                    dtype=np.uint8,
                ).reshape((160, 240, 4))
                layout = renderer._logo_layout(sprite)
                center_x = int(round((layout["left"] + layout["right"]) / 2))
                upper_y = int(round(layout["top"] + 8))
                lower_y = int(round(layout["bottom"] - 8))

                self.assertGreater(
                    int(rgba[upper_y, center_x, 0]),
                    int(rgba[upper_y, center_x, 2]) + 80,
                )
                self.assertGreater(
                    int(rgba[lower_y, center_x, 2]),
                    int(rgba[lower_y, center_x, 0]) + 80,
                )
                self.assertLessEqual(
                    int(renderer._logo_composite_artist.commands[0][0][:, :, 3].max()),
                    128,
                )
            finally:
                renderer.close()

    def test_footer_uses_configured_font_weights_and_fits_source(self):
        renderer = BarRenderer(
            config=ChartConfig(
                dpi=72,
                time_label_font_weight="heavy",
                source_font_weight="medium",
                source_font_size=10,
                source_max_width=50,
                text_average_char_width=0.5,
            )
        )
        axis = FakeAxis()
        scene = Scene(
            title="Title",
            time_label="2000",
            source_label="Source: very/long/path/to/source.csv",
        )

        renderer._draw_footer(axis, scene)

        self.assertEqual(axis.text_calls[0]["text"], "2000")
        self.assertEqual(axis.text_calls[0]["fontweight"], "heavy")
        self.assertEqual(axis.text_calls[0]["zorder"], 0)
        self.assertEqual(axis.text_calls[1]["text"], "Source:...")
        self.assertEqual(axis.text_calls[1]["fontweight"], "medium")
        self.assertEqual(axis.text_calls[1]["zorder"], 5)


    def test_renders_all_bar_shapes_with_reused_gradient_artists(self):
        scene = Scene(
            title="Shapes",
            bars=[
                BarSprite(
                    name="Example",
                    value=100,
                    color="#4E79A7",
                    x=100,
                    y=90,
                    width=160,
                    height=36,
                    rank=1,
                )
            ],
        )

        for shape in ("rectangle", "rounded", "capsule", "lollipop"):
            with self.subTest(shape=shape):
                renderer = BarRenderer(config=ChartConfig(
                    width=320,
                    height=180,
                    dpi=72,
                    left_margin=100,
                    right_margin=20,
                    top_margin=40,
                    bottom_margin=20,
                    logos_enabled=False,
                    bar_shape=shape,
                    bar_gradient_enabled=True,
                    bar_border_enabled=True,
                    bar_border_color="#FFFFFF",
                    bar_border_width=2.5,
                ))

                try:
                    rgba = renderer.render_rgba(scene)
                    artists = renderer._bar_artists[0]

                    self.assertEqual(len(rgba), 320 * 180 * 4)
                    self.assertTrue(artists.border.get_visible())
                    self.assertEqual(artists.border.get_linewidth(), 2.5)
                    self.assertGreater(len(artists.border.get_path().vertices), 0)
                    self.assertGreaterEqual(
                        len(renderer._gradient_artist.get_paths()),
                        64,
                    )
                finally:
                    renderer.close()

    def test_capsule_gradient_tapers_at_rounded_ends(self):
        renderer = BarRenderer(config=ChartConfig(bar_shape="capsule"))
        sprite = BarSprite(
            name="Example",
            value=100,
            color="#4E79A7",
            x=100,
            y=90,
            width=160,
            height=36,
        )

        left_top, left_bottom = renderer._bar_vertical_bounds(sprite, sprite.x)
        middle_top, middle_bottom = renderer._bar_vertical_bounds(
            sprite,
            sprite.x + (sprite.width / 2),
        )

        self.assertAlmostEqual(left_top, sprite.y)
        self.assertAlmostEqual(left_bottom, sprite.y)
        self.assertEqual(middle_top, sprite.y - (sprite.height / 2))
        self.assertEqual(middle_bottom, sprite.y + (sprite.height / 2))

    def test_lollipop_value_never_moves_inside_the_circle(self):
        renderer = BarRenderer(config=ChartConfig(
            width=640,
            value_label_edge_padding=24,
            bar_shape="lollipop",
        ))
        sprite = BarSprite(
            name="Example",
            value=125,
            color="#4E79A7",
            x=210,
            y=90,
            width=360,
            height=42,
        )

        layout = renderer._value_label_layout(sprite, "125.0")

        self.assertEqual(layout["ha"], "right")
        self.assertEqual(layout["x"], 616)

    def test_solid_lollipop_uses_circle_endpoint_and_offset_shadow(self):
        renderer = BarRenderer(config=ChartConfig(
            bar_shape="lollipop",
            bar_gradient_enabled=False,
            bar_shadow_offset_x=7,
            bar_shadow_offset_y=3,
        ))
        sprite = BarSprite(
            name="Example",
            value=100,
            color="#4E79A7",
            x=100,
            y=90,
            width=160,
            height=36,
        )
        figure, axis = renderer._figure_axis()
        renderer._setup_canvas(figure, axis)
        renderer._initialize_scene_artists(axis)
        renderer._ensure_bar_artist_capacity(axis, 1)
        artists = renderer._bar_artists[0]

        try:
            renderer._update_bar_artists(artists, sprite)
            bar_extents = artists.bar.get_path().get_extents()
            shadow_extents = artists.shadow.get_path().get_extents()

            self.assertAlmostEqual(bar_extents.xmax, sprite.x + sprite.width)
            self.assertAlmostEqual(bar_extents.height, sprite.height)
            self.assertAlmostEqual(shadow_extents.xmin - bar_extents.xmin, 7)
            self.assertAlmostEqual(shadow_extents.ymin - bar_extents.ymin, 3)
        finally:
            renderer.close()

    def test_advanced_appearance_layers_are_composited_and_reused(self):
        renderer = BarRenderer(config=ChartConfig(
            width=320,
            height=180,
            dpi=72,
            left_margin=100,
            right_margin=20,
            top_margin=40,
            bottom_margin=20,
            logos_enabled=False,
            bar_appearance_mode="advanced",
            bar_shape="capsule",
            bar_fill_type="gradient",
            bar_texture_enabled=True,
            bar_texture_preset="brushed_metal",
            bar_bevel_enabled=True,
            bar_inner_shadow_opacity=0.2,
            bar_outer_glow_enabled=True,
            bar_glow_opacity=0.3,
            bar_glow_blur=6,
            bar_track_enabled=True,
            bar_track_opacity=0.2,
            bar_border_enabled=True,
        ))
        scene = Scene(
            title="Advanced",
            bars=[
                BarSprite(
                    name="Example",
                    value=100,
                    color="#4E79A7",
                    x=100,
                    y=90,
                    width=160,
                    height=36,
                    rank=1,
                )
            ],
        )

        try:
            first_rgba = renderer.render_rgba(scene)
            artists = renderer._bar_artists[0]
            cached_fill = renderer._advanced_fill_cache["#4e79a7"]
            first_command = renderer._advanced_composite_artist.commands[-1]
            mask_cache_size = len(renderer._advanced_shape_mask_cache)
            material_cache_size = len(renderer._advanced_material_cache)
            second_rgba = renderer.render_rgba(scene)

            self.assertEqual(len(first_rgba), 320 * 180 * 4)
            self.assertEqual(len(second_rgba), 320 * 180 * 4)
            self.assertEqual(first_rgba, second_rgba)
            self.assertIsNone(renderer._gradient_artist)
            self.assertIsNone(artists.track)
            self.assertIsNone(artists.shadow)
            self.assertIsNone(artists.fill_image)
            self.assertIsNone(artists.fill_clip)
            self.assertEqual(artists.glow, ())
            self.assertTrue(renderer._advanced_track_collection.get_visible())
            self.assertTrue(renderer._advanced_shadow_collection.get_visible())
            self.assertTrue(renderer._advanced_glow_collection.get_visible())
            self.assertEqual(
                len(renderer._advanced_composite_artist.commands),
                1,
            )
            self.assertEqual(first_command[0].dtype, np.uint8)
            self.assertGreater(int(first_command[0][:, :, 3].max()), 0)
            self.assertLess(first_command[0].shape[0], renderer.config.height)
            self.assertLess(first_command[0].shape[1], renderer.config.width)
            self.assertIs(
                renderer._advanced_fill_cache["#4e79a7"],
                cached_fill,
            )
            self.assertEqual(len(renderer._advanced_fill_cache), 1)
            self.assertEqual(
                len(renderer._advanced_shape_mask_cache),
                mask_cache_size,
            )
            self.assertEqual(
                len(renderer._advanced_material_cache),
                material_cache_size,
            )
        finally:
            renderer.close()

    def test_advanced_compositor_supports_every_bar_shape(self):
        scene = Scene(
            title="Advanced",
            bars=[
                BarSprite(
                    name="Example",
                    value=100,
                    color="#4E79A7",
                    x=100,
                    y=90,
                    width=160,
                    height=36,
                    rank=1,
                )
            ],
        )

        for shape in ("rectangle", "rounded", "capsule", "lollipop"):
            with self.subTest(shape=shape):
                renderer = BarRenderer(config=ChartConfig(
                    width=320,
                    height=180,
                    dpi=72,
                    left_margin=100,
                    right_margin=20,
                    top_margin=40,
                    bottom_margin=20,
                    logos_enabled=False,
                    bar_appearance_mode="advanced",
                    bar_shape=shape,
                    bar_fill_type="texture",
                    bar_texture_enabled=True,
                    bar_texture_preset="carbon",
                    bar_bevel_enabled=True,
                    bar_inner_shadow_opacity=0.2,
                    bar_outer_glow_enabled=True,
                    bar_shine_enabled=True,
                    bar_track_enabled=True,
                    bar_border_enabled=True,
                ))

                try:
                    rgba = renderer.render_rgba(scene)
                    command_image = (
                        renderer._advanced_composite_artist.commands[-1][0]
                    )

                    self.assertEqual(len(rgba), 320 * 180 * 4)
                    self.assertEqual(
                        len(renderer._advanced_composite_artist.commands),
                        1,
                    )
                    self.assertGreater(int(command_image[:, :, 3].max()), 0)
                    self.assertGreater(float(np.std(command_image[:, :, :3])), 0)
                finally:
                    renderer.close()

    def test_advanced_gradient_direction_changes_fill_axis(self):
        common = {
            "bar_appearance_mode": "advanced",
            "bar_fill_type": "gradient",
            "bar_fill_use_category_color": False,
            "bar_fill_color_start": "#000000",
            "bar_fill_color_center": "#808080",
            "bar_fill_color_end": "#FFFFFF",
            "bar_highlight_position": 0.5,
        }
        horizontal = BarRenderer(config=ChartConfig(
            **common,
            bar_gradient_direction="horizontal",
        ))._advanced_fill_image("#123456")
        vertical = BarRenderer(config=ChartConfig(
            **common,
            bar_gradient_direction="vertical",
        ))._advanced_fill_image("#123456")

        self.assertFalse(np.allclose(horizontal[32, 0], horizontal[32, -1]))
        self.assertTrue(np.allclose(horizontal[0, 128], horizontal[-1, 128]))
        self.assertFalse(np.allclose(vertical[0, 128], vertical[-1, 128]))
        self.assertTrue(np.allclose(vertical[32, 0], vertical[32, -1]))

    def test_advanced_texture_presets_generate_finite_fill(self):
        for preset in (
            "noise",
            "brushed_metal",
            "grunge",
            "paper",
            "carbon",
        ):
            with self.subTest(preset=preset):
                renderer = BarRenderer(config=ChartConfig(
                    bar_appearance_mode="advanced",
                    bar_fill_type="texture",
                    bar_texture_enabled=True,
                    bar_texture_preset=preset,
                    bar_texture_intensity=0.5,
                    bar_texture_contrast=1.3,
                ))
                image = renderer._advanced_fill_image("#4E79A7")

                self.assertEqual(image.shape, (64, 256, 4))
                self.assertTrue(np.isfinite(image).all())
                self.assertGreater(float(np.std(image[:, :, :3])), 0.01)

    def test_advanced_custom_texture_image_is_loaded_and_tiled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            texture_path = Path(temp_dir) / "texture.png"
            texture = Image.new("RGB", (4, 4), "white")
            texture.putpixel((0, 0), (0, 0, 0))
            texture.putpixel((2, 2), (30, 90, 180))
            texture.save(texture_path)
            renderer = BarRenderer(config=ChartConfig(
                bar_appearance_mode="advanced",
                bar_fill_type="texture",
                bar_texture_enabled=True,
                bar_texture_preset="custom_image",
                bar_texture_custom_image=str(texture_path),
                bar_texture_intensity=0.7,
                bar_texture_scale=2.0,
            ))

            image = renderer._advanced_fill_image("#4E79A7")

        self.assertEqual(image.shape, (64, 256, 4))
        self.assertGreater(float(np.std(image[:, :, :3])), 0.01)

    def test_advanced_content_positions_and_value_effects(self):
        renderer = BarRenderer(config=ChartConfig(
            width=500,
            bar_appearance_mode="advanced",
            bar_label_position="inside",
            bar_value_position="above",
            bar_value_use_theme_color=False,
            bar_value_color="#ABCDEF",
            bar_value_border_enabled=True,
            bar_value_border_width=1.5,
            bar_value_shadow_enabled=True,
        ))
        sprite = BarSprite(
            name="Example",
            value=100,
            color="#4E79A7",
            x=100,
            y=90,
            width=200,
            height=40,
        )
        label_layout = renderer._bar_label_layout(sprite)
        value_layout = renderer._value_label_layout(sprite, "100")
        figure, axis = renderer._figure_axis()
        renderer._setup_canvas(figure, axis)
        renderer._initialize_scene_artists(axis)
        renderer._ensure_bar_artist_capacity(axis, 1)

        try:
            self.assertEqual(label_layout["ha"], "left")
            self.assertGreater(label_layout["x"], sprite.x)
            self.assertEqual(value_layout["va"], "bottom")
            self.assertLess(value_layout["y"], sprite.y)
            self.assertEqual(value_layout["color"], "#ABCDEF")
            self.assertEqual(
                len(renderer._bar_artists[0].value_label.get_path_effects()),
                3,
            )
        finally:
            renderer.close()

    def test_lollipop_inside_left_logo_adds_a_circular_socket(self):
        renderer = BarRenderer(config=ChartConfig(
            bar_shape="lollipop",
            bar_logo_position="inside_left",
        ))
        sprite = BarSprite(
            name="Example",
            value=100,
            color="#4E79A7",
            x=100,
            y=90,
            width=160,
            height=36,
            logo_path="logo.png",
        )
        radius = sprite.height / 2
        left_center = sprite.x + radius
        middle = sprite.x + (sprite.width / 2)
        right_center = sprite.x + sprite.width - radius

        left_top, left_bottom = renderer._bar_vertical_bounds(sprite, left_center)
        middle_top, middle_bottom = renderer._bar_vertical_bounds(sprite, middle)
        right_top, right_bottom = renderer._bar_vertical_bounds(sprite, right_center)

        self.assertAlmostEqual(left_top, sprite.y - radius)
        self.assertAlmostEqual(left_bottom, sprite.y + radius)
        self.assertGreater(middle_top, sprite.y - radius)
        self.assertLess(middle_bottom, sprite.y + radius)
        self.assertAlmostEqual(right_top, sprite.y - radius)
        self.assertAlmostEqual(right_bottom, sprite.y + radius)

    def test_logo_inside_right_uses_adaptive_circle_background_and_border(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / "logo.png"
            Image.new("RGBA", (30, 20), "#E15759").save(logo_path)
            renderer = BarRenderer(config=ChartConfig(
                width=320,
                height=180,
                dpi=72,
                bar_shape="capsule",
                bar_logo_position="inside_right",
                bar_logo_shape="adaptive",
                bar_logo_padding=3,
                bar_logo_border_enabled=True,
                bar_logo_border_color="#FFFFFF",
                bar_logo_border_width=2,
                bar_logo_background_enabled=True,
                bar_logo_background_color="#101010",
                bar_logo_background_opacity=0.8,
                bar_gradient_enabled=False,
            ))
            sprite = BarSprite(
                name="Example",
                value=100,
                color="#4E79A7",
                x=100,
                y=90,
                width=160,
                height=36,
                logo_path=str(logo_path),
            )
            figure, axis = renderer._figure_axis()
            renderer._setup_canvas(figure, axis)
            renderer._initialize_scene_artists(axis)

            try:
                renderer._update_logo_composite([sprite])
                layout = renderer._logo_layout(sprite)
                command_image, command_left, command_top = (
                    renderer._logo_composite_artist.commands[0]
                )
                padding = int(np.ceil(renderer.config.bar_logo_border_width / 2)) + 1

                self.assertAlmostEqual(layout["right"], sprite.x + sprite.width - 3)
                self.assertEqual(renderer._resolved_logo_shape(), "circle")
                self.assertEqual(len(renderer._logo_composite_artist.commands), 1)
                self.assertEqual(
                    command_image.shape[:2],
                    (
                        int(round(layout["size"])) + (padding * 2),
                        int(round(layout["size"])) + (padding * 2),
                    ),
                )
                self.assertEqual(command_left, int(round(layout["left"])) - padding)
                self.assertEqual(command_top, int(round(layout["top"])) - padding)
                self.assertEqual(int(command_image[0, 0, 3]), 0)
                self.assertGreater(int(command_image[:, :, 3].max()), 0)
                self.assertGreater(len(renderer._logo_shape_mask_cache), 0)
                self.assertGreater(len(renderer._logo_border_mask_cache), 0)
            finally:
                renderer.close()

    def test_inside_logo_slots_reserve_label_and_value_space(self):
        sprite = BarSprite(
            name="A very long category",
            value=100,
            color="#4E79A7",
            x=100,
            y=90,
            width=220,
            height=40,
            logo_path="logo.png",
        )
        left_renderer = BarRenderer(config=ChartConfig(
            bar_appearance_mode="advanced",
            bar_logo_position="inside_left",
            bar_label_position="inside",
        ))
        right_renderer = BarRenderer(config=ChartConfig(
            bar_appearance_mode="advanced",
            bar_logo_position="inside_right",
            bar_value_position="inside",
        ))

        left_layout = left_renderer._logo_layout(sprite)
        label_layout = left_renderer._bar_label_layout(sprite)
        right_layout = right_renderer._logo_layout(sprite)
        value_layout = right_renderer._value_label_layout(sprite, "100")

        self.assertGreater(label_layout["x"], left_layout["right"])
        self.assertLess(value_layout["x"], right_layout["left"])

    def test_category_alignment_uses_the_existing_label_area(self):
        sprite = BarSprite(
            name="Category",
            value=100,
            color="#4E79A7",
            x=200,
            y=90,
            width=160,
            height=36,
        )
        expected = {
            "left": (40, "left"),
            "center": (112, "center"),
            "right": (184, "right"),
        }

        for alignment, (expected_x, expected_ha) in expected.items():
            with self.subTest(alignment=alignment):
                renderer = BarRenderer(config=ChartConfig(
                    label_min_x=40,
                    bar_label_alignment=alignment,
                ))
                layout = renderer._bar_label_layout(sprite)

                self.assertEqual(layout["x"], expected_x)
                self.assertEqual(layout["ha"], expected_ha)

    def test_background_image_contain_uses_selected_margin_color(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            background_path = Path(temp_dir) / "background.png"
            Image.new("RGB", (80, 20), "#FF0000").save(background_path)
            renderer = BarRenderer(config=ChartConfig(
                width=80,
                height=80,
                dpi=72,
                background_mode="image",
                background_color_override="#123456",
                background_image_path=str(background_path),
                background_image_fit="contain",
            ))

            prepared = renderer._prepare_background_image(background_path)
            scene = Scene(title="Background")

            try:
                renderer.render_rgba(scene)

                self.assertEqual(prepared.shape, (80, 80, 4))
                self.assertEqual(tuple(prepared[0, 0, :3]), (18, 52, 86))
                self.assertEqual(tuple(prepared[40, 40, :3]), (255, 0, 0))
                self.assertIsNotNone(renderer._background_image_artist)
                self.assertEqual(
                    tuple(renderer._background_image_artist.get_extent()),
                    (0, 80, 80, 0),
                )
            finally:
                renderer.close()

    def test_static_background_compositor_preserves_image_orientation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            background_path = Path(temp_dir) / "quadrants.png"
            background = Image.new("RGB", (80, 80), "#000000")
            background.paste("#FF0000", (0, 0, 40, 40))
            background.paste("#00FF00", (40, 0, 80, 40))
            background.paste("#0000FF", (0, 40, 40, 80))
            background.paste("#FFFF00", (40, 40, 80, 80))
            background.save(background_path)
            renderer = BarRenderer(config=ChartConfig(
                width=80,
                height=80,
                dpi=72,
                background_mode="image",
                background_image_path=str(background_path),
                background_image_fit="stretch",
                logos_enabled=False,
            ))

            try:
                rgba = np.frombuffer(
                    renderer.render_rgba(Scene(title="")),
                    dtype=np.uint8,
                ).reshape((80, 80, 4))

                self.assertEqual(tuple(rgba[10, 10, :3]), (255, 0, 0))
                self.assertEqual(tuple(rgba[10, 70, :3]), (0, 255, 0))
                self.assertEqual(tuple(rgba[70, 10, :3]), (0, 0, 255))
                self.assertEqual(tuple(rgba[70, 70, :3]), (255, 255, 0))
                self.assertTrue(renderer._background_image_artist.image.flags.c_contiguous)
            finally:
                renderer.close()


class FakeAxis:
    def __init__(self):
        self.barh_calls = []
        self.imshow_calls = []
        self.text_calls = []

    def barh(self, y, width, height, left, color, edgecolor, zorder):
        self.barh_calls.append(
            {
                "y": y,
                "width": width,
                "height": height,
                "left": left,
                "color": color,
                "edgecolor": edgecolor,
                "zorder": zorder,
            }
        )

    def imshow(self, image, extent, aspect, interpolation, zorder):
        self.imshow_calls.append(
            {
                "image": image,
                "extent": extent,
                "aspect": aspect,
                "interpolation": interpolation,
                "zorder": zorder,
            }
        )

    def text(self, x, y, text, **kwargs):
        text_call = {"x": x, "y": y, "text": text}
        text_call.update(kwargs)
        self.text_calls.append(text_call)


if __name__ == "__main__":
    unittest.main()
