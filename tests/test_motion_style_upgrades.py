import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import _test_path
from PIL import Image, ImageDraw

from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from core.layout_engine import LayoutEngine
from core.motion_engine import MotionEngine
from models.bar_data import BarData
from models.bar_sprite import BarSprite
from renderer.bar_renderer import BarRenderer
from studio.project_builder import build_project_data, project_form_values
from config.project_file_loader import load_project_data
from utils.logo_color import representative_logo_color


def sprite(name, rank, y):
    return BarSprite(
        name=name, value=100, color="#123456", x=40, y=y,
        width=100, height=20, rank=rank,
    )


class MotionStyleUpgradeTest(unittest.TestCase):

    def test_font_variants_and_fallback_are_resolved_to_real_files(self):
        renderer = BarRenderer(config=ChartConfig())
        try:
            variants = {
                renderer._text_font_path("DejaVu Sans", weight, style)
                for weight in ("normal", "bold")
                for style in ("normal", "italic")
            }
            fallback = renderer._text_font_path(
                "Definitely Missing Font", "bold", "italic"
            )
        finally:
            renderer.close()
        self.assertTrue(all(Path(path).is_file() for path in variants))
        self.assertTrue(Path(fallback).is_file())
        self.assertGreaterEqual(len(variants), 3)

    def test_typography_styles_survive_builder_and_loader(self):
        data = self._project_data(
            text_styles={
                "title_font_weight": "bold",
                "title_font_style": "italic",
                "label_font_weight": "bold",
                "label_font_style": "italic",
            },
            bar_gap=44,
            bar_color_source="primary_logo",
            primary_logo_min_size=36,
            background_motion="forward_motion",
            background_motion_speed=1.8,
            background_motion_intensity=0.6,
            fun_facts={
                "editorial_headline_font_weight": "bold",
                "editorial_headline_font_style": "italic",
            },
        )
        config = load_project_data(data).chart_config
        self.assertEqual((config.title_font_weight, config.title_font_style), ("bold", "italic"))
        self.assertEqual((config.label_font_weight, config.label_font_style), ("bold", "italic"))
        self.assertEqual(config.bar_gap, 44)
        self.assertEqual(config.bar_color_source, "primary_logo")
        self.assertEqual(config.primary_logo_min_size, 36)
        self.assertEqual(config.background_motion, "forward_motion")
        self.assertEqual(config.background_motion_speed, 1.8)
        facts = load_project_data(data).fun_fact_config
        self.assertEqual(facts.editorial_headline_font_style, "italic")

    def test_bar_spacing_default_and_increased_geometry(self):
        bars = [BarData("A", 10), BarData("B", 9)]
        legacy = LayoutEngine(ChartConfig(logos_enabled=False)).build(bars)
        spaced = LayoutEngine(ChartConfig(logos_enabled=False, bar_gap=50)).build(bars)
        self.assertEqual(legacy[1].y - legacy[0].y, 54 + 18)
        self.assertEqual(spaced[1].y - spaced[0].y, 54 + 50)
        self.assertGreater(
            spaced[1].y - spaced[0].y,
            (spaced[0].height + spaced[1].height) / 2,
        )

    def test_logo_color_ignores_transparency_and_white_padding(self):
        with tempfile.TemporaryDirectory() as directory:
            red = Path(directory) / "red.png"
            blue = Path(directory) / "blue.jpg"
            padded = Path(directory) / "padded.png"
            Image.new("RGBA", (32, 32), (240, 20, 20, 255)).save(red)
            Image.new("RGB", (32, 32), (15, 45, 230)).save(blue)
            image = Image.new("RGBA", (80, 80), (255, 255, 255, 0))
            ImageDraw.Draw(image).rectangle((31, 31, 48, 48), fill=(235, 25, 25, 255))
            image.save(padded)
            self.assertGreater(int(representative_logo_color(red)[1:3], 16), 180)
            self.assertGreater(int(representative_logo_color(blue)[5:7], 16), 170)
            self.assertGreater(int(representative_logo_color(padded)[1:3], 16), 180)

    def test_logo_color_source_falls_back_and_preserves_manual_color(self):
        with tempfile.TemporaryDirectory() as directory:
            logo = Path(directory) / "logo.png"
            Image.new("RGBA", (24, 24), (20, 210, 60, 255)).save(logo)
            bar = BarData("A", 10, color="#AA1122", logo_path=str(logo))
            manual = LayoutEngine(ChartConfig(logos_enabled=True)).build([bar])[0]
            automatic = LayoutEngine(ChartConfig(
                logos_enabled=True, bar_color_source="primary_logo"
            )).build([bar])[0]
            restored = LayoutEngine(ChartConfig(logos_enabled=True)).build([bar])[0]
            missing = LayoutEngine(ChartConfig(
                logos_enabled=True, bar_color_source="primary_logo"
            )).build([replace(bar, logo_path=str(Path(directory) / "missing.png"))])[0]
            self.assertEqual(manual.color, "#AA1122")
            self.assertNotEqual(automatic.color, manual.color)
            self.assertEqual(restored.color, "#AA1122")
            self.assertEqual(missing.color, "#AA1122")

    def test_forward_background_is_frame_deterministic_and_off_is_legacy(self):
        self.assertEqual(ChartConfig().background_motion, "off")
        renderer = BarRenderer(config=ChartConfig(
            width=320, height=180, dpi=72,
            background_motion="forward_motion",
        ))
        try:
            first = renderer._forward_motion_background(100)
            repeated = renderer._forward_motion_background(100)
            later = renderer._forward_motion_background(110)
        finally:
            renderer.close()
        self.assertTrue((first == repeated).all())
        self.assertFalse((first == later).all())

    def test_rank_y_uses_period_endpoints_without_changing_steps(self):
        animation = AnimationConfig(easing="ease_in_out_cubic")
        engine = MotionEngine(animation)
        start = [sprite("A", 2, 40), sprite("B", 3, 70), sprite("C", 5, 130)]
        end = [sprite("A", 3, 70), sprite("B", 2, 40), sprite("C", 2, 40)]
        configured_steps = 8
        frames = engine.interpolate_sprites_continuous(
            start, start, end, end, steps=configured_steps
        )
        midpoint = {item.name: item for item in frames[configured_steps // 2]}
        eased = animation.easing_function()(0.5)
        self.assertAlmostEqual(midpoint["A"].y, 40 + (30 * eased))
        self.assertAlmostEqual(midpoint["B"].y, 70 - (30 * eased))
        self.assertAlmostEqual(midpoint["C"].y, 130 - (90 * eased))
        self.assertEqual(len(frames), configured_steps + 1)

    def test_primary_logo_minimum_can_extend_beyond_a_short_bar(self):
        renderer = BarRenderer(config=ChartConfig(
            width=200, height=100, bar_logo_position="inside_left",
            logo_size=20, primary_logo_min_size=36,
        ))
        try:
            layout = renderer._base_logo_layout(
                BarSprite(
                    name="Tiny", value=1, color="#000000", x=20, y=50,
                    width=12, height=20, rank=1, logo_path="logo.png",
                ),
                slot="primary",
            )
        finally:
            renderer.close()
        self.assertGreaterEqual(layout["size"], 36)
        self.assertGreater(layout["size"], 12)
        self.assertGreaterEqual(layout["left"], 0)
        self.assertLessEqual(layout["right"], 200)

    def _project_data(self, **overrides):
        defaults = dict(
            name="test", csv_path="data.csv", year_column="year",
            name_column="name", value_column="value", title="Test",
            source_label="Source", output_file="out.mp4", frames_dir="frames",
            layout_preset="youtube_1080p", theme="clean_report",
            typography_preset="studio", value_format="decimal", fps=30,
            steps_per_transition=30, top_n=5, max_visible_bars=5,
        )
        defaults.update(overrides)
        return build_project_data(**defaults)


if __name__ == "__main__":
    unittest.main()
