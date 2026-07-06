import unittest

import _test_path
from config.chart_config import ChartConfig
from config.layout_config import (
    apply_layout_preset,
    get_layout_preset,
    list_layout_presets,
)


class LayoutConfigTest(unittest.TestCase):
    def test_lists_layout_presets(self):
        self.assertIn("youtube_1080p", list_layout_presets())
        self.assertIn("youtube_4k", list_layout_presets())
        self.assertIn("square_social", list_layout_presets())
        self.assertIn("vertical_shorts", list_layout_presets())
        self.assertIn("compact_dashboard", list_layout_presets())

    def test_gets_layout_preset(self):
        preset = get_layout_preset("vertical_shorts")

        self.assertEqual(preset.name, "vertical_shorts")
        self.assertEqual(preset.width, 1080)
        self.assertEqual(preset.height, 1920)

    def test_applies_layout_preset_to_chart_config(self):
        chart_config = apply_layout_preset(ChartConfig(), "compact_dashboard")

        self.assertEqual(chart_config.layout_preset, "compact_dashboard")
        self.assertEqual(chart_config.width, 1280)
        self.assertEqual(chart_config.height, 720)
        self.assertEqual(chart_config.top_margin, 165)
        self.assertEqual(chart_config.bar_height, 36)
        self.assertEqual(chart_config.source_y, 675)

    def test_rejects_unknown_layout_preset(self):
        with self.assertRaises(ValueError):
            get_layout_preset("unknown")


if __name__ == "__main__":
    unittest.main()
