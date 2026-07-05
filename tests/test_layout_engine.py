import tempfile
import unittest
from pathlib import Path

import _test_path
from config.chart_config import ChartConfig
from core.layout_engine import LayoutEngine
from models.bar_data import BarData


class LayoutEngineTest(unittest.TestCase):
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
