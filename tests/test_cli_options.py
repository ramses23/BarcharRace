import sys
import unittest
from unittest.mock import patch

import _test_path
from cli.cli_options import (
    apply_cli_overrides,
    build_preset_from_cli_options,
    parse_cli_args,
)
from config.project_preset import DEFAULT_PRESET_NAME, get_preset


class CliOptionsTest(unittest.TestCase):
    def test_uses_default_preset_without_arguments(self):
        options = parse_cli_args([])

        self.assertEqual(options.preset_name, DEFAULT_PRESET_NAME)

    def test_parses_list_actions(self):
        options = parse_cli_args(["--list-themes"])

        self.assertTrue(options.list_themes)
        self.assertEqual(options.preset_name, DEFAULT_PRESET_NAME)

    def test_parses_list_layouts_action(self):
        options = parse_cli_args(["--list-layouts"])

        self.assertTrue(options.list_layouts)
        self.assertEqual(options.preset_name, DEFAULT_PRESET_NAME)

    def test_parses_list_easings_action(self):
        options = parse_cli_args(["--list-easings"])

        self.assertTrue(options.list_easings)
        self.assertEqual(options.preset_name, DEFAULT_PRESET_NAME)

    def test_parses_list_typographies_action(self):
        options = parse_cli_args(["--list-typographies"])

        self.assertTrue(options.list_typographies)
        self.assertEqual(options.preset_name, DEFAULT_PRESET_NAME)

    def test_parses_project_file(self):
        options = parse_cli_args(["--project", "projects/sample_project.json"])

        self.assertEqual(options.project_file, "projects/sample_project.json")
        self.assertEqual(options.preset_name, DEFAULT_PRESET_NAME)

    def test_rejects_project_file_with_preset_name(self):
        with patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit):
                parse_cli_args(
                    [
                        "csv_sample",
                        "--project",
                        "projects/sample_project.json",
                    ]
                )

    def test_applies_basic_chart_overrides(self):
        preset = get_preset("csv_sample")
        options = parse_cli_args(
            [
                "csv_sample",
                "--output",
                "custom/video.mp4",
                "--frames-dir",
                "custom/frames",
                "--title",
                "Custom Race",
                "--fps",
                "24",
                "--steps",
                "12",
                "--width",
                "1280",
                "--height",
                "720",
                "--video-codec",
                "libx265",
                "--video-pixel-format",
                "yuv444p",
                "--png-compress-level",
                "0",
                "--video-crf",
                "22",
                "--video-bitrate",
                "8M",
                "--ffmpeg-preset",
                "slow",
                "--frame-output-mode",
                "ffmpeg_stream",
            ]
        )

        updated = apply_cli_overrides(preset, options)

        self.assertEqual(updated.chart_config.output_file, "custom/video.mp4")
        self.assertEqual(updated.chart_config.frames_dir, "custom/frames")
        self.assertEqual(updated.chart_config.title, "Custom Race")
        self.assertEqual(updated.chart_config.fps, 24)
        self.assertEqual(updated.chart_config.steps_per_transition, 12)
        self.assertEqual(updated.chart_config.width, 1280)
        self.assertEqual(updated.chart_config.height, 720)
        self.assertEqual(updated.chart_config.video_codec, "libx265")
        self.assertEqual(updated.chart_config.video_pixel_format, "yuv444p")
        self.assertEqual(updated.chart_config.png_compress_level, 0)
        self.assertEqual(updated.chart_config.video_crf, 22)
        self.assertEqual(updated.chart_config.video_bitrate, "8M")
        self.assertEqual(updated.chart_config.ffmpeg_preset, "slow")
        self.assertEqual(updated.chart_config.frame_output_mode, "ffmpeg_stream")
        self.assertEqual(updated.data_source_config, preset.data_source_config)
        self.assertEqual(updated.dataset_config, preset.dataset_config)

    def test_applies_theme_and_value_format_overrides(self):
        preset = get_preset("csv_sample")
        options = parse_cli_args(
            [
                "csv_sample",
                "--theme",
                "midnight_contrast",
                "--value-format",
                "compact",
            ]
        )

        updated = apply_cli_overrides(preset, options)

        self.assertEqual(updated.chart_config.theme.name, "midnight_contrast")
        self.assertTrue(updated.chart_config.value_format.compact)

    def test_applies_typography_override(self):
        preset = get_preset("csv_sample")
        options = parse_cli_args(["csv_sample", "--typography", "compact"])

        updated = apply_cli_overrides(preset, options)

        self.assertEqual(updated.chart_config.typography_preset, "compact")
        self.assertEqual(updated.chart_config.title_font_size, 30)
        self.assertEqual(updated.chart_config.source_max_width, 760)

    def test_applies_layout_override(self):
        preset = get_preset("csv_sample")
        options = parse_cli_args(["csv_sample", "--layout", "square_social"])

        updated = apply_cli_overrides(preset, options)

        self.assertEqual(updated.chart_config.layout_preset, "square_social")
        self.assertEqual(updated.chart_config.width, 1080)
        self.assertEqual(updated.chart_config.height, 1080)
        self.assertEqual(updated.chart_config.left_margin, 260)

    def test_duration_uses_effective_fps(self):
        preset = get_preset("csv_sample")
        options = parse_cli_args(
            [
                "csv_sample",
                "--fps",
                "24",
                "--duration",
                "2.5",
            ]
        )

        updated = apply_cli_overrides(preset, options)

        self.assertEqual(updated.chart_config.fps, 24)
        self.assertEqual(updated.chart_config.steps_per_transition, 60)

    def test_rejects_duration_and_steps_together(self):
        with patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit):
                parse_cli_args(
                    [
                        "csv_sample",
                        "--duration",
                        "2",
                        "--steps",
                        "10",
                    ]
                )

    def test_rejects_invalid_png_compress_level(self):
        with patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit):
                parse_cli_args(["csv_sample", "--png-compress-level", "10"])

    def test_rejects_negative_video_crf(self):
        with patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit):
                parse_cli_args(["csv_sample", "--video-crf", "-1"])

    def test_builds_preset_from_project_file(self):
        options = parse_cli_args(["--project", "projects/sample_project.json"])

        preset = build_preset_from_cli_options(options)

        self.assertEqual(preset.name, "sample_project")
        self.assertIsInstance(preset.chart_config.title, str)
        self.assertTrue(preset.chart_config.title)
        self.assertEqual(preset.chart_config.theme.name, "clean_report")
        self.assertEqual(preset.chart_config.animation.easing, "ease_out_cubic")


if __name__ == "__main__":
    unittest.main()
