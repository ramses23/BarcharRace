import unittest

import _test_path
from config.chart_config import ChartConfig
from config.theme_config import get_theme, list_themes


class ThemeConfigTest(unittest.TestCase):
    def test_gets_named_theme(self):
        theme = get_theme("clean_report")

        self.assertEqual(theme.name, "clean_report")
        self.assertEqual(theme.background_color, "#FFFFFF")

    def test_lists_themes(self):
        self.assertIn("studio_light", list_themes())
        self.assertIn("midnight_contrast", list_themes())

    def test_rejects_unknown_theme(self):
        with self.assertRaises(ValueError):
            get_theme("unknown")

    def test_chart_config_proxies_visual_values_from_theme(self):
        theme = get_theme("midnight_contrast")
        config = ChartConfig(theme=theme)

        self.assertEqual(config.background_color, theme.background_color)
        self.assertEqual(config.text_color, theme.text_color)
        self.assertEqual(config.muted_text_color, theme.muted_text_color)
        self.assertEqual(config.font_family, theme.font_family)
        self.assertEqual(config.color_palette, theme.bar_palette)


if __name__ == "__main__":
    unittest.main()
