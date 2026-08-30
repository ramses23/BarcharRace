import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import _test_path
from PIL import Image, ImageDraw

from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from config.fun_fact_config import FunFactConfig
from core.layout_engine import LayoutEngine
from core.scene_geometry import build_scene_geometry
from core.value_axis import ValueAxisTracker, scale_bar_sprites
from core.motion_engine import MotionEngine
from models.bar_data import BarData
from models.bar_sprite import BarSprite
from models.scene import Scene
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

    def test_primary_logo_minimum_is_capped_by_bar_height(self):
        renderer = BarRenderer(config=ChartConfig(
            width=200, height=100, bar_logo_position="inside_left",
            logo_size=20, primary_logo_min_size=100,
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
        self.assertEqual(layout["size"], 20)
        self.assertGreater(layout["size"], 12)
        self.assertGreaterEqual(layout["left"], 0)
        self.assertLessEqual(layout["right"], 200)

    def test_primary_logo_size_depends_on_row_height_not_bar_width(self):
        renderer = BarRenderer(config=ChartConfig(
            width=800,
            height=300,
            bar_logo_position="inside_right",
            logo_size=100,
            primary_logo_min_size=0,
            value_labels_enabled=True,
            bar_appearance_mode="advanced",
            bar_value_position="outside",
        ))
        try:
            layouts = []
            for width in (500, 100, 30, 10, 2):
                item = BarSprite(
                    name="Row", value=width, color="#000000",
                    x=100, y=100, width=width, height=48,
                    rank=1, logo_path="logo.png",
                )
                layout = renderer._logo_layout(item)
                value_layout = renderer._value_label_layout(item, "100")
                layouts.append(layout)
                self.assertEqual(layout["size"], 48)
                self.assertGreaterEqual(
                    value_layout["x"],
                    layout["right"] + renderer.config.logo_label_gap,
                )
            self.assertEqual(
                {round(layout["size"], 6) for layout in layouts},
                {48.0},
            )

            original = BarSprite(
                name="Row", value=100, color="#000000", x=100, y=100,
                width=500, height=48, rank=1, logo_path="logo.png",
            )
            scaled = None
            for mode in ("static", "dynamic"):
                axis_config = replace(
                    renderer.config,
                    value_grid_enabled=True,
                    value_grid_mode=mode,
                )
                tracker = ValueAxisTracker.from_config(
                    axis_config, [[original]]
                )
                scaled = scale_bar_sprites(
                    [replace(original, width=10)],
                    tracker.next([replace(original, width=10)]).scale,
                )[0]
                self.assertEqual(
                    renderer._logo_layout(original)["size"],
                    renderer._logo_layout(scaled)["size"],
                )

            geometry = build_scene_geometry(
                renderer.config,
                FunFactConfig(),
                Scene(title="", subtitle="", bars=[scaled]),
            )
            self.assertEqual(
                geometry["primary_logo_rects"][0]["width"],
                renderer._logo_layout(scaled)["size"],
            )
        finally:
            renderer.close()

    def test_primary_logo_size_is_percentage_of_bar_height(self):
        item = BarSprite(
            name="Row", value=1, color="#000000", x=100, y=100,
            width=10, height=48, rank=1, logo_path="logo.png",
        )
        for percent, expected in ((100, 48), (75, 36), (50, 24), (25, 12)):
            with self.subTest(percent=percent):
                renderer = BarRenderer(config=ChartConfig(
                    width=300,
                    height=200,
                    logo_size=percent,
                    bar_logo_position="inside_right",
                ))
                try:
                    layout = renderer._logo_layout(item)
                finally:
                    renderer.close()
                self.assertEqual(layout["size"], expected)

    def test_primary_outer_badge_contains_padding_border_and_shapes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / "logo.png"
            Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(logo_path)
            item = BarSprite(
                name="Row", value=1, color="#000000", x=100, y=100,
                width=2, height=48, rank=1, logo_path=str(logo_path),
            )
            for shape in ("adaptive", "circle", "square"):
                with self.subTest(shape=shape):
                    renderer = BarRenderer(config=ChartConfig(
                        width=300,
                        height=200,
                        logo_size=100,
                        bar_logo_position="inside_right",
                        bar_logo_shape=shape,
                        bar_logo_padding=7,
                        bar_logo_background_enabled=True,
                        bar_logo_border_enabled=True,
                        bar_logo_border_width=4,
                    ))
                    try:
                        layout = renderer._logo_layout(item)
                        command = renderer._logo_composite_command(
                            item, layout=layout
                        )
                        geometry = build_scene_geometry(
                            renderer.config,
                            FunFactConfig(),
                            Scene(title="", bars=[item]),
                        )
                    finally:
                        renderer.close()

                    image = command[0]
                    artwork = (
                        (image[:, :, 0] > 180)
                        & (image[:, :, 1] < 100)
                        & (image[:, :, 2] < 100)
                    )
                    artwork_columns = artwork.any(axis=0).nonzero()[0]
                    self.assertEqual(layout["size"], 48)
                    self.assertLessEqual(image.shape[0], 48)
                    self.assertLessEqual(image.shape[1], 48)
                    self.assertLessEqual(
                        artwork_columns[-1] - artwork_columns[0] + 1,
                        48 - 14,
                    )
                    self.assertEqual(
                        geometry["primary_logo_rects"][0]["height"],
                        layout["size"],
                    )
                    self.assertEqual(image.shape[0], round(layout["size"]))

    def test_secondary_logo_retains_width_capped_sizing(self):
        renderer = BarRenderer(config=ChartConfig(
            width=300,
            height=200,
            bar_secondary_logo_enabled=True,
            bar_secondary_logo_layout="independent",
            bar_secondary_logo_position="inside_left",
            bar_secondary_logo_size=40,
            bar_secondary_logo_padding=3,
        ))
        try:
            item = BarSprite(
                name="Row", value=1, color="#000000", x=50, y=80,
                width=10, height=48, rank=1,
                secondary_logo_path="secondary.png",
            )
            secondary = renderer._base_logo_layout(item, slot="secondary")
        finally:
            renderer.close()

        self.assertEqual(secondary["size"], 4)

    def test_primary_logo_height_floor_renders_in_both_aspect_ratios(self):
        for width, height in ((320, 180), (180, 320)):
            with self.subTest(width=width, height=height):
                renderer = BarRenderer(config=ChartConfig(
                    width=width,
                    height=height,
                    bar_logo_position="inside_right",
                    logo_size=100,
                ))
                item = BarSprite(
                    name="Row", value=1, color="#000000",
                    x=20, y=90, width=10, height=48,
                    rank=1, logo_path="logo.png",
                )
                try:
                    layout = renderer._logo_layout(item)
                    rgba = renderer.render_rgba(Scene(title="", bars=[item]))
                finally:
                    renderer.close()

                self.assertEqual(layout["size"], 48)
                self.assertGreaterEqual(layout["left"], 0)
                self.assertLessEqual(layout["right"], width)
                self.assertEqual(len(rgba), width * height * 4)

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
