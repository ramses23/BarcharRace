import json
import tempfile
import unittest
from pathlib import Path

import _test_path
from config.project_file_loader import ProjectFileError, load_project_file


class ProjectFileLoaderTest(unittest.TestCase):
    def test_loads_project_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "custom_project.json"
            project_path.write_text(
                json.dumps(
                    {
                        "name": "custom_project",
                        "chart": {
                            "title": "Custom Project",
                            "output_file": "output/custom.mp4",
                            "layout_preset": "compact_dashboard",
                            "theme": "midnight_contrast",
                            "value_format": "compact",
                            "typography_preset": "compact",
                            "fps": 24,
                            "steps_per_transition": 12,
                            "logo_file_extensions": [".png", ".webp"],
                            "rank_labels_enabled": False,
                            "rank_label_prefix": "No.",
                            "label_min_x": 56,
                            "value_label_gap": 20,
                            "auto_fit_bar_count": False,
                            "max_visible_bars": 7,
                            "title_font_weight": "heavy",
                            "subtitle_font_weight": "light",
                            "time_label_font_weight": "bold",
                            "source_font_weight": "normal",
                            "title_max_width": 900,
                            "subtitle_max_width": 800,
                            "source_max_width": 700,
                            "bar_shadow_enabled": True,
                            "bar_shadow_color": "#222222",
                            "bar_shadow_alpha": 0.2,
                            "bar_shadow_offset_x": 8,
                            "bar_shadow_offset_y": 5,
                            "bar_gradient_enabled": True,
                            "bar_gradient_lighten": 0.3,
                            "video_codec": "libx265",
                            "video_pixel_format": "yuv444p",
                            "video_crf": 22,
                            "video_bitrate": "8M",
                            "ffmpeg_preset": "slow",
                        },
                        "animation": {
                            "easing": "ease_out_cubic",
                            "enter_exit": False,
                            "value_smoothing": False,
                        },
                        "selection": {
                            "top_n": 5,
                            "aggregate_other": True,
                            "other_label": "Rest",
                            "other_color": "#999999",
                        },
                        "data_source": {
                            "source_type": "csv",
                            "csv_path": "data/custom.csv",
                        },
                        "dataset": {
                            "year_column": "date",
                            "name_column": "name",
                            "value_column": "amount",
                            "allow_negative_values": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            preset = load_project_file(project_path)

        self.assertEqual(preset.name, "custom_project")
        self.assertEqual(preset.chart_config.title, "Custom Project")
        self.assertEqual(preset.chart_config.output_file, "output/custom.mp4")
        self.assertEqual(preset.chart_config.layout_preset, "compact_dashboard")
        self.assertEqual(preset.chart_config.width, 1280)
        self.assertEqual(preset.chart_config.height, 720)
        self.assertEqual(preset.chart_config.top_margin, 165)
        self.assertEqual(preset.chart_config.theme.name, "midnight_contrast")
        self.assertTrue(preset.chart_config.value_format.compact)
        self.assertEqual(preset.chart_config.typography_preset, "compact")
        self.assertEqual(preset.chart_config.fps, 24)
        self.assertEqual(preset.chart_config.steps_per_transition, 12)
        self.assertEqual(preset.chart_config.logo_file_extensions, (".png", ".webp"))
        self.assertFalse(preset.chart_config.rank_labels_enabled)
        self.assertEqual(preset.chart_config.rank_label_prefix, "No.")
        self.assertEqual(preset.chart_config.label_min_x, 56)
        self.assertEqual(preset.chart_config.value_label_gap, 20)
        self.assertFalse(preset.chart_config.auto_fit_bar_count)
        self.assertEqual(preset.chart_config.max_visible_bars, 7)
        self.assertEqual(preset.chart_config.title_font_weight, "heavy")
        self.assertEqual(preset.chart_config.subtitle_font_weight, "light")
        self.assertEqual(preset.chart_config.time_label_font_weight, "bold")
        self.assertEqual(preset.chart_config.source_font_weight, "normal")
        self.assertEqual(preset.chart_config.subtitle_font_size, 18)
        self.assertEqual(preset.chart_config.title_max_width, 900)
        self.assertEqual(preset.chart_config.subtitle_max_width, 800)
        self.assertEqual(preset.chart_config.source_max_width, 700)
        self.assertTrue(preset.chart_config.bar_shadow_enabled)
        self.assertEqual(preset.chart_config.bar_shadow_color, "#222222")
        self.assertEqual(preset.chart_config.bar_shadow_alpha, 0.2)
        self.assertEqual(preset.chart_config.bar_shadow_offset_x, 8)
        self.assertEqual(preset.chart_config.bar_shadow_offset_y, 5)
        self.assertTrue(preset.chart_config.bar_gradient_enabled)
        self.assertEqual(preset.chart_config.bar_gradient_lighten, 0.3)
        self.assertEqual(preset.chart_config.video_codec, "libx265")
        self.assertEqual(preset.chart_config.video_pixel_format, "yuv444p")
        self.assertEqual(preset.chart_config.video_crf, 22)
        self.assertEqual(preset.chart_config.video_bitrate, "8M")
        self.assertEqual(preset.chart_config.ffmpeg_preset, "slow")
        self.assertEqual(preset.chart_config.animation.easing, "ease_out_cubic")
        self.assertFalse(preset.chart_config.animation.enter_exit)
        self.assertFalse(preset.chart_config.animation.value_smoothing)
        self.assertEqual(preset.chart_config.selection.top_n, 5)
        self.assertTrue(preset.chart_config.selection.aggregate_other)
        self.assertEqual(preset.chart_config.selection.other_label, "Rest")
        self.assertEqual(preset.chart_config.selection.other_color, "#999999")
        self.assertEqual(preset.data_source_config.csv_path, "data/custom.csv")
        self.assertEqual(preset.dataset_config.year_column, "date")
        self.assertEqual(preset.dataset_config.name_column, "name")
        self.assertEqual(preset.dataset_config.value_column, "amount")
        self.assertTrue(preset.dataset_config.allow_negative_values)

    def test_uses_file_stem_as_default_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "stem_name.json"
            project_path.write_text("{}", encoding="utf-8")

            preset = load_project_file(project_path)

        self.assertEqual(preset.name, "stem_name")

    def test_extends_base_preset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "youtube_custom.json"
            project_path.write_text(
                json.dumps(
                    {
                        "base_preset": "youtube_1080p",
                        "chart": {
                            "title": "Extended",
                            "theme": "clean_report",
                        },
                    }
                ),
                encoding="utf-8",
            )

            preset = load_project_file(project_path)

        self.assertEqual(preset.name, "youtube_custom")
        self.assertEqual(preset.chart_config.title, "Extended")
        self.assertEqual(preset.chart_config.theme.name, "clean_report")
        self.assertEqual(preset.chart_config.steps_per_transition, 45)

    def test_rejects_unknown_project_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"unknown": {}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_unknown_section_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"unknown": "value"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_unknown_animation_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"animation": {"unknown": "value"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_unknown_selection_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"selection": {"unknown": "value"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_invalid_top_n(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"selection": {"top_n": 0}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_boolean_top_n(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"selection": {"top_n": True}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_unknown_easing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"animation": {"easing": "unknown"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_unknown_typography_preset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"typography_preset": "unknown"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_unknown_layout_preset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"layout_preset": "unknown"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_invalid_video_crf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"video_crf": -1}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_blank_video_codec(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"video_codec": ""}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_invalid_max_visible_bars(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"max_visible_bars": -1}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_non_boolean_auto_fit_bar_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"auto_fit_bar_count": "yes"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_invalid_json_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text("[]", encoding="utf-8")

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)


if __name__ == "__main__":
    unittest.main()
