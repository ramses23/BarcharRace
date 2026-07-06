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


if __name__ == "__main__":
    unittest.main()
