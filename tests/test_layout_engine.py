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
                    BarData(name="USA", value=100),
                ]
            )

            self.assertIsNone(sprites[0].logo_path)


if __name__ == "__main__":
    unittest.main()
