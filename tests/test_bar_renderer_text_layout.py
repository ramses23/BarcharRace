import unittest

import _test_path
from config.chart_config import ChartConfig
from models.bar_sprite import BarSprite
from renderer.bar_renderer import BarRenderer


class BarRendererTextLayoutTest(unittest.TestCase):
    def test_fits_long_bar_label(self):
        renderer = BarRenderer(
            config=ChartConfig(
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


class FakeAxis:
    def __init__(self):
        self.barh_calls = []

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


if __name__ == "__main__":
    unittest.main()
