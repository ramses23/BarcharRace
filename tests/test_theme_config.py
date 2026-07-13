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

    def test_chart_background_color_can_override_theme(self):
        config = ChartConfig(
            theme=get_theme("midnight_contrast"),
            background_color_override="#123456",
        )

        self.assertEqual(config.background_color, "#123456")

    def test_chart_text_colors_inherit_theme_and_allow_individual_overrides(self):
        theme = get_theme("midnight_contrast")
        inherited = ChartConfig(theme=theme)

        self.assertEqual(inherited.resolved_title_text_color, theme.text_color)
        self.assertEqual(inherited.resolved_label_text_color, theme.text_color)
        self.assertEqual(
            inherited.resolved_subtitle_text_color,
            theme.muted_text_color,
        )
        self.assertEqual(inherited.resolved_value_text_color, theme.muted_text_color)

        overridden = ChartConfig(
            theme=theme,
            title_text_color="#112233",
            subtitle_text_color="#223344",
            label_text_color="#334455",
            value_text_color="#445566",
            time_label_text_color="#556677",
            source_text_color="#667788",
            rank_label_text_color="#778899",
        )

        self.assertEqual(overridden.resolved_title_text_color, "#112233")
        self.assertEqual(overridden.resolved_subtitle_text_color, "#223344")
        self.assertEqual(overridden.resolved_label_text_color, "#334455")
        self.assertEqual(overridden.resolved_value_text_color, "#445566")
        self.assertEqual(overridden.resolved_time_label_text_color, "#556677")
        self.assertEqual(overridden.resolved_source_text_color, "#667788")
        self.assertEqual(overridden.resolved_rank_label_text_color, "#778899")

    def test_direct_ffmpeg_stream_is_the_default_frame_output_mode(self):
        self.assertEqual(ChartConfig().frame_output_mode, "ffmpeg_stream")


if __name__ == "__main__":
    unittest.main()
