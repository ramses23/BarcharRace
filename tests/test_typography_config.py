import unittest

import _test_path
from config.chart_config import ChartConfig
from config.typography_config import (
    apply_typography_preset,
    get_typography_preset,
    list_typography_presets,
)


class TypographyConfigTest(unittest.TestCase):
    def test_lists_typography_presets(self):
        self.assertIn("studio", list_typography_presets())
        self.assertIn("editorial", list_typography_presets())
        self.assertIn("compact", list_typography_presets())

    def test_gets_typography_preset(self):
        preset = get_typography_preset("editorial")

        self.assertEqual(preset.name, "editorial")
        self.assertGreater(preset.title_font_size, 34)

    def test_applies_typography_preset_to_chart_config(self):
        chart_config = apply_typography_preset(ChartConfig(), "compact")

        self.assertEqual(chart_config.typography_preset, "compact")
        self.assertEqual(chart_config.title_font_size, 30)
        self.assertEqual(chart_config.subtitle_font_size, 18)
        self.assertEqual(chart_config.source_max_width, 760)

    def test_rejects_unknown_typography_preset(self):
        with self.assertRaises(ValueError):
            get_typography_preset("unknown")


if __name__ == "__main__":
    unittest.main()
