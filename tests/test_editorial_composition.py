import unittest
from dataclasses import replace

import _test_path
from PIL import Image, ImageDraw, ImageFont

from config.chart_config import ChartConfig
from config.fun_fact_config import FunFactConfig
from core.layout_engine import LayoutEngine
from core.source_text_geometry import resolve_source_text_layout
from models.bar_data import BarData
from renderer.bar_renderer import BarRenderer
from studio.fun_fact_layout import (
    apply_fun_fact_layout,
    editorial_geometry,
    editorial_safe_area,
)


class EditorialCompositionTest(unittest.TestCase):
    def setUp(self):
        self.chart = ChartConfig(
            width=1000,
            height=600,
            left_margin=180,
            right_margin=80,
            source_x=40,
            source_y=560,
            time_label_y=480,
        )
        self.floating = FunFactConfig(
            enabled=True,
            layout="editorial_floating",
            editorial_card_x=540,
            editorial_card_y=300,
            editorial_card_width=360,
            editorial_card_height=220,
            panel_margin=24,
        )

    def test_legacy_defaults_are_reserved_left_and_manual(self):
        config = FunFactConfig()
        self.assertEqual(config.editorial_layout_mode, "reserved")
        self.assertEqual(config.editorial_headline_alignment, "left")
        self.assertEqual(config.editorial_body_alignment, "left")
        self.assertEqual(config.editorial_placement_mode, "manual")
        self.assertFalse(config.editorial_keep_inside_safe_area)

    def test_overlay_does_not_mutate_structural_or_source_geometry(self):
        disabled = replace(self.floating, enabled=False)
        overlay = replace(self.floating, editorial_layout_mode="overlay")
        self.assertEqual(
            apply_fun_fact_layout(self.chart, disabled),
            apply_fun_fact_layout(self.chart, overlay),
        )
        self.assertFalse(
            LayoutEngine(self.chart, overlay)._uses_floating_editorial_obstacle()
        )
        source_without = resolve_source_text_layout(
            self.chart, disabled, "Source: geometry must stay exact"
        )
        source_overlay = resolve_source_text_layout(
            self.chart, overlay, "Source: geometry must stay exact"
        )
        self.assertEqual(source_without.available_rect, source_overlay.available_rect)
        self.assertEqual(source_without.fitted_text, source_overlay.fitted_text)
        bars = [BarData(name="Leader", value=100), BarData(name="Second", value=70)]
        disabled_sprites = LayoutEngine(self.chart, disabled).build(bars)
        overlay_sprites = LayoutEngine(self.chart, overlay).build(bars)
        self.assertEqual(disabled_sprites, overlay_sprites)

    def test_reserved_preserves_legacy_obstacle_path(self):
        self.assertTrue(
            LayoutEngine(self.chart, self.floating)._uses_floating_editorial_obstacle()
        )
        self.assertNotEqual(
            apply_fun_fact_layout(self.chart, self.floating),
            self.chart,
        )

    def test_nine_placement_presets_use_actual_card_and_safe_bounds(self):
        expected = {
            "top_left": (24, 24),
            "top_center": (320, 24),
            "top_right": (616, 24),
            "middle_left": (24, 190),
            "center": (320, 190),
            "middle_right": (616, 190),
            "bottom_left": (24, 356),
            "bottom_center": (320, 356),
            "bottom_right": (616, 356),
        }
        self.assertEqual(editorial_safe_area(self.chart, self.floating), (24, 24, 976, 576))
        for placement, position in expected.items():
            with self.subTest(placement=placement):
                geometry = editorial_geometry(
                    self.chart,
                    replace(
                        self.floating,
                        editorial_layout_mode="overlay",
                        editorial_placement_mode=placement,
                        editorial_keep_inside_safe_area=True,
                    ),
                )
                self.assertEqual(geometry[:2], position)

    def test_manual_safe_area_clamps_position_without_resizing(self):
        geometry = editorial_geometry(
            self.chart,
            replace(
                self.floating,
                editorial_layout_mode="overlay",
                editorial_card_x=900,
                editorial_card_y=590,
                editorial_keep_inside_safe_area=True,
            ),
        )
        self.assertEqual(geometry, (616, 356, 360, 220))

    def test_line_alignment_is_independent_and_uses_text_box_width(self):
        canvas = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default(size=16)
        line_width = draw.textlength("Aligned", font=font)
        for alignment, expected_x in (
            ("left", 20),
            ("center", 20 + ((200 - line_width) / 2)),
            ("right", 220 - line_width),
        ):
            with self.subTest(alignment=alignment):
                target = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                BarRenderer._draw_wrapped_lines(
                    ImageDraw.Draw(target),
                    ["Aligned"],
                    canvas=target,
                    x=20,
                    y=20,
                    font=font,
                    fill=(255, 255, 255, 255),
                    spacing=2,
                    max_width=200,
                    alignment=alignment,
                )
                bbox = target.getchannel("A").getbbox()
                self.assertIsNotNone(bbox)
                self.assertAlmostEqual(bbox[0], expected_x, delta=2)

    def test_justify_keeps_single_and_last_lines_left(self):
        class RecordingDraw:
            def __init__(self):
                self.calls = []

            @staticmethod
            def textbbox(_position, _text, font=None):
                return 0, 0, 10, 10

            @staticmethod
            def textlength(text, font=None):
                return len(text) * 10

            def text(self, position, text, font=None, fill=None):
                self.calls.append((position, text))

        draw = RecordingDraw()
        font = type("Font", (), {"size": 16})()
        BarRenderer._draw_wrapped_lines(
            draw,
            ["two words", "last line"],
            x=12,
            y=8,
            font=font,
            fill=(255, 255, 255, 255),
            spacing=2,
            max_width=105,
            alignment="justify",
        )
        self.assertEqual(draw.calls[0], ((12.0, 8), "two"))
        self.assertEqual(draw.calls[-1], ((12.0, 20), "last line"))

        fallback = RecordingDraw()
        BarRenderer._draw_wrapped_lines(
            fallback,
            ["two words", "last line"],
            x=12,
            y=8,
            font=font,
            fill=(255, 255, 255, 255),
            spacing=2,
            max_width=220,
            alignment="justify",
        )
        self.assertEqual(fallback.calls[0], ((12.0, 8), "two words"))


if __name__ == "__main__":
    unittest.main()
