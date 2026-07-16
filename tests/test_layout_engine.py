import tempfile
import unittest
from pathlib import Path

import _test_path
from config.bar_selection_config import BarSelectionConfig
from config.chart_config import ChartConfig
from core.layout_engine import LayoutEngine
from models.bar_data import BarData


class LayoutEngineTest(unittest.TestCase):
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

    def test_zero_values_do_not_divide_by_zero(self):
        config = ChartConfig(logos_enabled=False)

        sprites = LayoutEngine(config=config).build(
            [
                BarData(name="A", value=0),
                BarData(name="B", value=0),
            ]
        )

        self.assertEqual([sprite.width for sprite in sprites], [0, 0])


if __name__ == "__main__":
    unittest.main()
