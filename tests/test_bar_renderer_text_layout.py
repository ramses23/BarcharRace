import unittest

import _test_path
import matplotlib.pyplot as plt
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
        self.assertEqual(axis.text_calls[1]["text"], "Source:...")
        self.assertEqual(axis.text_calls[1]["fontweight"], "medium")


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
