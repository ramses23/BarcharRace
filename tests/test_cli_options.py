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

    def test_builds_preset_from_project_file(self):
        options = parse_cli_args(["--project", "projects/sample_project.json"])

        preset = build_preset_from_cli_options(options)

        self.assertEqual(preset.name, "sample_project")
        self.assertEqual(preset.chart_config.title, "External Project Demo")
        self.assertEqual(preset.chart_config.theme.name, "clean_report")


if __name__ == "__main__":
    unittest.main()
