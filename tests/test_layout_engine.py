import tempfile
import unittest
from pathlib import Path

import _test_path
from config.bar_selection_config import BarSelectionConfig
from config.chart_config import ChartConfig
from config.fun_fact_config import FunFactConfig
from core.layout_engine import LayoutEngine
from models.bar_data import BarData
from utils.text_fit import measure_text_width, measurement_font
from utils.value_formatter import format_value


class LayoutEngineTest(unittest.TestCase):
    def test_manual_vertical_layout_is_pixel_compatible(self):
        config = ChartConfig(logos_enabled=False, top_margin=200, bar_height=50, bar_gap=10)
        sprites = LayoutEngine(config).build([BarData(name="A", value=2), BarData(name="B", value=1)])
        self.assertEqual([(item.y, item.height) for item in sprites], [(200, 50), (260, 50)])

    def test_fill_available_uses_visible_text_and_ignores_date_position(self):
        config = ChartConfig(
            logos_enabled=False, height=600, bar_vertical_layout_mode="fill_available",
            bar_vertical_top_padding=10, bar_vertical_bottom_padding=10,
            title_enabled=True, title_y=40, title_font_size=30,
            subtitle_enabled=False, source_label_enabled=True, source_y=560,
            source_font_size=12, time_label_enabled=True, time_label_y=300,
        )
        sprites = LayoutEngine(config).build([BarData(name=str(i), value=10-i) for i in range(4)])
        self.assertEqual(len(sprites), 4)
        self.assertGreaterEqual(sprites[0].y, 70)
        self.assertLessEqual(sprites[-1].y + (sprites[-1].height / 2), 548)
        self.assertTrue(all(a.y + (a.height / 2) <= b.y - (b.height / 2) for a, b in zip(sprites, sprites[1:])))
    def test_assigns_rank_by_value(self):
        config = ChartConfig(logos_enabled=False)

        sprites = LayoutEngine(config=config).build(
            [
                BarData(name="Mexico", value=80),
                BarData(name="USA", value=100),
                BarData(name="Canada", value=60),
            ]
        )

        ranks = {sprite.name: sprite.rank for sprite in sprites}

        self.assertEqual(ranks["USA"], 1)
        self.assertEqual(ranks["Mexico"], 2)
        self.assertEqual(ranks["Canada"], 3)

    def test_keeps_aggregated_other_trailing(self):
        config = ChartConfig(
            logos_enabled=False,
            selection=BarSelectionConfig(
                top_n=2,
                aggregate_other=True,
                other_label="Other",
            ),
        )

        sprites = LayoutEngine(config=config).build(
            [
                BarData(name="USA", value=100),
                BarData(name="Other", value=500),
            ]
        )

        self.assertEqual([sprite.name for sprite in sprites], ["USA", "Other"])
        self.assertEqual([sprite.rank for sprite in sprites], [1, 2])

    def test_adds_logo_path_when_asset_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / "USA.png"
            logo_path.write_text("fake image", encoding="utf-8")

            config = ChartConfig(
                logos_dir=temp_dir,
                logo_file_extensions=(".png",),
            )

            sprites = LayoutEngine(config=config).build(
                [
                    BarData(name="USA", value=100),
                ]
            )

            self.assertEqual(sprites[0].logo_path, str(logo_path))

    def test_prefers_explicit_bar_logo_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            resolved_logo = Path(temp_dir) / "USA.png"
            resolved_logo.write_text("resolved", encoding="utf-8")

            config = ChartConfig(
                logos_dir=temp_dir,
                logo_file_extensions=(".png",),
            )

            sprites = LayoutEngine(config=config).build(
                [
                    BarData(
                        name="USA",
                        value=100,
                        logo_path="logos/custom_usa.png",
                        secondary_logo_path="logos/custom_secondary_usa.png",
                    ),
                ]
            )

            self.assertEqual(sprites[0].logo_path, "logos/custom_usa.png")

    def test_preserves_explicit_secondary_logo_path(self):
        sprites = LayoutEngine(config=ChartConfig()).build([
            BarData(
                name="USA",
                value=100,
                logo_path="portraits/usa.png",
                secondary_logo_path="flags/usa.png",
            ),
        ])

        self.assertEqual(sprites[0].logo_path, "portraits/usa.png")
        self.assertEqual(sprites[0].secondary_logo_path, "flags/usa.png")

    def test_does_not_add_logo_when_logos_are_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / "USA.png"
            logo_path.write_text("fake image", encoding="utf-8")

            config = ChartConfig(
                logos_enabled=False,
                logos_dir=temp_dir,
                logo_file_extensions=(".png",),
            )

            sprites = LayoutEngine(config=config).build(
                [
                    BarData(
                        name="USA",
                        value=100,
                        logo_path="logos/custom_usa.png",
                    ),
                ]
            )

            self.assertIsNone(sprites[0].logo_path)
            self.assertIsNone(sprites[0].secondary_logo_path)

    def test_auto_limits_bars_to_vertical_capacity(self):
        config = ChartConfig(
            height=160,
            top_margin=40,
            bottom_margin=20,
            bar_height=20,
            bar_gap=10,
            logos_enabled=False,
        )

        sprites = LayoutEngine(config=config).build(
            [
                BarData(name=f"Item {index}", value=100 - index)
                for index in range(6)
            ]
        )

        self.assertEqual(config.bar_capacity, 4)
        self.assertEqual(len(sprites), 4)
        self.assertEqual([sprite.rank for sprite in sprites], [1, 2, 3, 4])
        self.assertLessEqual(
            sprites[-1].y + (sprites[-1].height / 2),
            config.height - config.bottom_margin,
        )

    def test_can_disable_auto_fit_bar_count(self):
        config = ChartConfig(
            height=160,
            top_margin=40,
            bottom_margin=20,
            bar_height=20,
            bar_gap=10,
            auto_fit_bar_count=False,
            logos_enabled=False,
        )

        sprites = LayoutEngine(config=config).build(
            [
                BarData(name=f"Item {index}", value=100 - index)
                for index in range(6)
            ]
        )

        self.assertEqual(len(sprites), 6)

    def test_max_visible_bars_limits_layout(self):
        config = ChartConfig(
            max_visible_bars=2,
            auto_fit_bar_count=False,
            logos_enabled=False,
        )

        sprites = LayoutEngine(config=config).build(
            [
                BarData(name="A", value=100),
                BarData(name="B", value=80),
                BarData(name="C", value=60),
            ]
        )

        self.assertEqual([sprite.name for sprite in sprites], ["A", "B"])

    def test_zero_values_are_not_rendered(self):
        config = ChartConfig(logos_enabled=False)

        sprites = LayoutEngine(config=config).build(
            [
                BarData(name="A", value=0),
                BarData(name="B", value=0),
            ]
        )

        self.assertEqual(sprites, [])

    def test_zero_values_are_removed_from_mixed_data(self):
        config = ChartConfig(logos_enabled=False)

        sprites = LayoutEngine(config=config).build(
            [
                BarData(name="Visible A", value=100),
                BarData(name="Hidden zero", value=0),
                BarData(name="Visible B", value=50),
            ]
        )

        self.assertEqual(
            [sprite.name for sprite in sprites],
            ["Visible A", "Visible B"],
        )
        self.assertEqual([sprite.rank for sprite in sprites], [1, 2])

    def test_reserves_measured_lane_for_explicit_outside_values(self):
        config = ChartConfig(
            width=1000,
            dpi=72,
            left_margin=100,
            right_margin=300,
            value_label_edge_padding=300,
            value_label_gap=12,
            value_font_size=24,
            bar_appearance_mode="advanced",
            bar_value_position="outside",
            logos_enabled=False,
        )
        bars = [
            BarData(name="A", value=779_346_252.6),
            BarData(name="B", value=655_129_405.8),
        ]

        sprites = LayoutEngine(config=config).build(bars)
        font = measurement_font(
            config.value_font_size,
            config.dpi,
            config.value_font_family or config.font_family,
        )
        widest_text = max(
            (
                format_value(bar.value, value_format=config.value_format)
                for bar in bars
            ),
            key=lambda text: measure_text_width(text, font),
        )
        value_right = (
            sprites[0].x
            + sprites[0].width
            + config.value_label_gap
            + measure_text_width(widest_text, font)
        )

        self.assertLess(sprites[0].width, config.max_bar_width)
        self.assertLessEqual(
            value_right,
            config.width - config.value_label_edge_padding,
        )

    def test_unified_mode_reserves_lane_for_explicit_outside_values(self):
        config = ChartConfig(
            width=1000,
            dpi=72,
            left_margin=100,
            right_margin=300,
            value_label_edge_padding=300,
            value_label_gap=12,
            value_font_size=24,
            bar_appearance_mode="unified",
            bar_value_position="outside",
            logos_enabled=False,
        )

        sprite = LayoutEngine(config=config).build([
            BarData(name="A", value=779_346_252.6),
        ])[0]

        self.assertLess(sprite.width, config.max_bar_width)

    def test_keeps_full_bar_width_when_outside_lane_already_fits(self):
        config = ChartConfig(
            width=1000,
            dpi=72,
            left_margin=100,
            right_margin=400,
            value_label_edge_padding=20,
            value_font_size=12,
            bar_appearance_mode="advanced",
            bar_value_position="outside",
            logos_enabled=False,
        )

        sprite = LayoutEngine(config=config).build([
            BarData(name="A", value=100),
        ])[0]

        self.assertEqual(sprite.width, config.max_bar_width)

    def test_auto_value_position_keeps_legacy_bar_width(self):
        config = ChartConfig(
            width=1000,
            left_margin=100,
            right_margin=300,
            value_label_edge_padding=300,
            bar_appearance_mode="advanced",
            bar_value_position="auto",
            logos_enabled=False,
        )

        sprite = LayoutEngine(config=config).build([
            BarData(name="A", value=779_346_252.6),
        ])[0]

        self.assertEqual(sprite.width, config.max_bar_width)

    def test_floating_editorial_card_limits_only_intersecting_rows(self):
        config = ChartConfig(
            width=1000,
            height=600,
            dpi=72,
            left_margin=100,
            right_margin=50,
            top_margin=100,
            bar_height=50,
            bar_gap=50,
            value_label_edge_padding=20,
            value_label_gap=10,
            value_font_size=12,
            bar_appearance_mode="advanced",
            bar_value_position="outside",
            logos_enabled=False,
        )
        fun_facts = FunFactConfig(
            enabled=True,
            layout="editorial_floating",
            editorial_card_x=500,
            editorial_card_y=175,
            editorial_card_width=450,
            editorial_card_height=250,
            editorial_collision_gap=20,
        )
        bars = [
            BarData(name="A", value=100),
            BarData(name="B", value=40),
            BarData(name="C", value=30),
            BarData(name="D", value=20),
        ]

        sprites = LayoutEngine(
            config=config,
            fun_fact_config=fun_facts,
        ).build(bars)

        scales = [sprite.width / sprite.value for sprite in sprites]
        self.assertTrue(all(abs(scale - scales[0]) < 1e-9 for scale in scales))
        self.assertGreater(sprites[0].x + sprites[0].width, 500)
        self.assertLessEqual(sprites[1].x + sprites[1].width, 480)
        self.assertLessEqual(sprites[2].x + sprites[2].width, 480)
        self.assertLessEqual(sprites[3].x + sprites[3].width, 480)


if __name__ == "__main__":
    unittest.main()
