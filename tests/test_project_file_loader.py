import json
import tempfile
import unittest
from pathlib import Path

import _test_path
from config.project_file_loader import ProjectFileError, load_project_file


class ProjectFileLoaderTest(unittest.TestCase):
    def test_migrates_legacy_nested_animation_and_logo_position(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "legacy_project.json"
            project_path.write_text(
                json.dumps({
                    "chart": {
                        "bar_logo_position": "inside",
                        "animation": {"motion_mode": "continuous"},
                        "selection": {"top_n": 4},
                    }
                }),
                encoding="utf-8",
            )

            preset = load_project_file(project_path)

        self.assertEqual(preset.chart_config.bar_logo_position, "inside_left")
        self.assertEqual(preset.chart_config.animation.motion_mode, "continuous")
        self.assertEqual(preset.chart_config.selection.top_n, 4)

    def test_rejects_project_from_newer_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "future_project.json"
            project_path.write_text(
                json.dumps({"schema_version": 999}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ProjectFileError,
                "newer than supported",
            ):
                load_project_file(project_path)

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
                            "background_mode": "image",
                            "background_color_override": "#102030",
                            "background_image_path": "backgrounds/studio.png",
                            "background_image_fit": "contain",
                            "value_format": "compact",
                            "typography_preset": "compact",
                            "fps": 24,
                            "steps_per_transition": 12,
                            "logo_file_extensions": [".png", ".webp"],
                            "rank_labels_enabled": False,
                            "rank_label_prefix": "No.",
                            "rank_label_min_x": 64,
                            "rank_label_label_gap": 12,
                            "label_min_x": 56,
                            "value_label_gap": 20,
                            "value_label_min_x": 72,
                            "auto_fit_bar_count": False,
                            "max_visible_bars": 7,
                            "title_font_weight": "heavy",
                            "subtitle_font_weight": "light",
                            "time_label_font_weight": "bold",
                            "source_font_weight": "normal",
                            "title_max_width": 900,
                            "subtitle_max_width": 800,
                            "source_max_width": 700,
                            "bar_shape": "capsule",
                            "bar_border_enabled": True,
                            "bar_border_color": "#EFEFEF",
                            "bar_border_width": 2.5,
                            "bar_appearance_mode": "advanced",
                            "bar_fill_type": "texture",
                            "bar_gradient_direction": "diagonal",
                            "bar_gradient_color_count": 3,
                            "bar_fill_use_category_color": False,
                            "bar_fill_color_start": "#112233",
                            "bar_fill_color_center": "#445566",
                            "bar_fill_color_end": "#778899",
                            "bar_highlight_position": 0.4,
                            "bar_edge_darkening": 0.2,
                            "bar_texture_enabled": True,
                            "bar_texture_preset": "carbon",
                            "bar_texture_intensity": 0.3,
                            "bar_texture_scale": 1.5,
                            "bar_texture_contrast": 1.2,
                            "bar_texture_blend_mode": "soft_light",
                            "bar_bevel_enabled": True,
                            "bar_bevel_size": 0.15,
                            "bar_inner_shadow_opacity": 0.2,
                            "bar_outer_glow_enabled": True,
                            "bar_glow_color": "#55AAFF",
                            "bar_glow_opacity": 0.3,
                            "bar_glow_blur": 8,
                            "bar_shine_enabled": True,
                            "bar_track_enabled": True,
                            "bar_track_color": "#111111",
                            "bar_track_opacity": 0.2,
                            "bar_logo_position": "inside_right",
                            "bar_logo_shape": "circle",
                            "bar_logo_padding": 5,
                            "bar_logo_border_enabled": True,
                            "bar_logo_border_color": "#FFFFFF",
                            "bar_logo_border_width": 2,
                            "bar_logo_background_enabled": True,
                            "bar_logo_background_color": "#101010",
                            "bar_logo_background_opacity": 0.8,
                            "bar_secondary_logo_enabled": True,
                            "bar_secondary_logo_layout": "side_by_side",
                            "bar_secondary_logo_position": "inside_left",
                            "bar_secondary_logo_badge_corner": "top_left",
                            "bar_secondary_logo_shape": "rounded",
                            "bar_secondary_logo_size": 26,
                            "bar_secondary_logo_gap": 4,
                            "bar_secondary_logo_padding": 2,
                            "bar_secondary_logo_border_enabled": True,
                            "bar_secondary_logo_border_color": "#EEEEEE",
                            "bar_secondary_logo_border_width": 1,
                            "bar_secondary_logo_background_enabled": True,
                            "bar_secondary_logo_background_color": "#202020",
                            "bar_secondary_logo_background_opacity": 0.7,
                            "bar_label_position": "inside",
                            "bar_label_alignment": "left",
                            "bar_value_position": "above",
                            "bar_value_border_enabled": True,
                            "bar_value_shadow_enabled": True,
                            "bar_shadow_enabled": True,
                            "bar_shadow_color": "#222222",
                            "bar_shadow_alpha": 0.2,
                            "bar_shadow_offset_x": 8,
                            "bar_shadow_offset_y": 5,
                            "bar_gradient_enabled": True,
                            "bar_gradient_lighten": 0.3,
                            "video_codec": "libx265",
                            "video_pixel_format": "yuv444p",
                            "png_compress_level": 0,
                            "video_crf": 22,
                            "video_bitrate": "8M",
                            "ffmpeg_preset": "slow",
                            "frame_output_mode": "ffmpeg_stream",
                            "title_font_family": "DejaVu Serif",
                            "subtitle_font_family": "DejaVu Sans Mono",
                            "label_font_family": "DejaVu Serif",
                            "value_font_family": "DejaVu Sans Mono",
                            "time_label_font_family": "DejaVu Serif",
                            "source_font_family": "DejaVu Sans Mono",
                            "rank_label_font_family": "DejaVu Serif",
                            "title_text_color": "#101112",
                            "subtitle_text_color": "#202122",
                            "label_text_color": "#303132",
                            "value_text_color": "#404142",
                            "time_label_text_color": "#505152",
                            "source_text_color": "#606162",
                            "rank_label_text_color": "#707172",
                            "title_font_size": 42,
                            "subtitle_font_size": 24,
                            "label_font_size": 21,
                            "value_font_size": 19,
                            "time_label_font_size": 128,
                            "source_font_size": 15,
                            "rank_label_font_size": 17,
                            "title_x": 300,
                            "title_y": 90,
                            "subtitle_x": 310,
                            "subtitle_y": 160,
                            "time_label_x": 1500,
                            "time_label_y": 900,
                            "source_x": 300,
                            "source_y": 1000,
                        },
                        "animation": {
                            "easing": "ease_out_cubic",
                            "enter_exit": False,
                            "value_smoothing": False,
                            "motion_mode": "continuous",
                        },
                        "selection": {
                            "top_n": 5,
                            "aggregate_other": True,
                            "other_label": "Rest",
                            "other_color": "#999999",
                        },
                        "categories": {
                            "Coal": {
                                "label": "Carbon",
                                "color": "#333333",
                                "logo": "logos/coal.png",
                                "secondary_logo": "logos_secondary/coal.png",
                            },
                            "Solar": {
                                "color": "#F2C94C",
                            },
                        },
                        "data_source": {
                            "source_type": "csv",
                            "csv_path": "data/custom.csv",
                            "source_label_override": "Source: Custom data",
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
        self.assertEqual(preset.chart_config.background_mode, "image")
        self.assertEqual(preset.chart_config.background_color, "#102030")
        self.assertEqual(
            preset.chart_config.background_image_path,
            "backgrounds/studio.png",
        )
        self.assertEqual(preset.chart_config.background_image_fit, "contain")
        self.assertTrue(preset.chart_config.value_format.compact)
        self.assertEqual(preset.chart_config.typography_preset, "compact")
        self.assertEqual(preset.chart_config.fps, 24)
        self.assertEqual(preset.chart_config.steps_per_transition, 12)
        self.assertEqual(preset.chart_config.logo_file_extensions, (".png", ".webp"))
        self.assertFalse(preset.chart_config.rank_labels_enabled)
        self.assertEqual(preset.chart_config.rank_label_prefix, "No.")
        self.assertEqual(preset.chart_config.rank_label_min_x, 64)
        self.assertEqual(preset.chart_config.rank_label_label_gap, 12)
        self.assertEqual(preset.chart_config.label_min_x, 56)
        self.assertEqual(preset.chart_config.value_label_gap, 20)
        self.assertEqual(preset.chart_config.value_label_min_x, 72)
        self.assertFalse(preset.chart_config.auto_fit_bar_count)
        self.assertEqual(preset.chart_config.max_visible_bars, 7)
        self.assertEqual(preset.chart_config.title_font_weight, "heavy")
        self.assertEqual(preset.chart_config.subtitle_font_weight, "light")
        self.assertEqual(preset.chart_config.time_label_font_weight, "bold")
        self.assertEqual(preset.chart_config.source_font_weight, "normal")
        self.assertEqual(preset.chart_config.subtitle_font_size, 24)
        self.assertEqual(preset.chart_config.title_max_width, 900)
        self.assertEqual(preset.chart_config.subtitle_max_width, 800)
        self.assertEqual(preset.chart_config.source_max_width, 700)
        self.assertEqual(preset.chart_config.bar_shape, "capsule")
        self.assertTrue(preset.chart_config.bar_border_enabled)
        self.assertEqual(preset.chart_config.bar_border_color, "#EFEFEF")
        self.assertEqual(preset.chart_config.bar_border_width, 2.5)
        self.assertEqual(preset.chart_config.bar_appearance_mode, "advanced")
        self.assertEqual(preset.chart_config.bar_fill_type, "texture")
        self.assertEqual(preset.chart_config.bar_gradient_direction, "diagonal")
        self.assertEqual(preset.chart_config.bar_gradient_color_count, 3)
        self.assertFalse(preset.chart_config.bar_fill_use_category_color)
        self.assertEqual(preset.chart_config.bar_fill_color_center, "#445566")
        self.assertTrue(preset.chart_config.bar_texture_enabled)
        self.assertEqual(preset.chart_config.bar_texture_preset, "carbon")
        self.assertEqual(preset.chart_config.bar_texture_blend_mode, "soft_light")
        self.assertTrue(preset.chart_config.bar_bevel_enabled)
        self.assertEqual(preset.chart_config.bar_inner_shadow_opacity, 0.2)
        self.assertTrue(preset.chart_config.bar_outer_glow_enabled)
        self.assertEqual(preset.chart_config.bar_glow_blur, 8)
        self.assertTrue(preset.chart_config.bar_track_enabled)
        self.assertEqual(preset.chart_config.bar_logo_position, "inside_right")
        self.assertEqual(preset.chart_config.bar_logo_shape, "circle")
        self.assertEqual(preset.chart_config.bar_logo_padding, 5)
        self.assertTrue(preset.chart_config.bar_logo_border_enabled)
        self.assertEqual(preset.chart_config.bar_logo_border_width, 2)
        self.assertTrue(preset.chart_config.bar_logo_background_enabled)
        self.assertEqual(preset.chart_config.bar_logo_background_opacity, 0.8)
        self.assertTrue(preset.chart_config.bar_secondary_logo_enabled)
        self.assertEqual(preset.chart_config.bar_secondary_logo_layout, "side_by_side")
        self.assertEqual(preset.chart_config.bar_secondary_logo_position, "inside_left")
        self.assertEqual(preset.chart_config.bar_secondary_logo_badge_corner, "top_left")
        self.assertEqual(preset.chart_config.bar_secondary_logo_shape, "rounded")
        self.assertEqual(preset.chart_config.bar_secondary_logo_size, 26)
        self.assertEqual(preset.chart_config.bar_secondary_logo_gap, 4)
        self.assertEqual(preset.chart_config.bar_secondary_logo_border_color, "#EEEEEE")
        self.assertEqual(preset.chart_config.bar_secondary_logo_background_opacity, 0.7)
        self.assertEqual(preset.chart_config.bar_label_position, "inside")
        self.assertEqual(preset.chart_config.bar_label_alignment, "left")
        self.assertEqual(preset.chart_config.bar_value_position, "above")
        self.assertTrue(preset.chart_config.bar_value_border_enabled)
        self.assertTrue(preset.chart_config.bar_value_shadow_enabled)
        self.assertTrue(preset.chart_config.bar_shadow_enabled)
        self.assertEqual(preset.chart_config.bar_shadow_color, "#222222")
        self.assertEqual(preset.chart_config.bar_shadow_alpha, 0.2)
        self.assertEqual(preset.chart_config.bar_shadow_offset_x, 8)
        self.assertEqual(preset.chart_config.bar_shadow_offset_y, 5)
        self.assertTrue(preset.chart_config.bar_gradient_enabled)
        self.assertEqual(preset.chart_config.bar_gradient_lighten, 0.3)
        self.assertEqual(preset.chart_config.video_codec, "libx265")
        self.assertEqual(preset.chart_config.video_pixel_format, "yuv444p")
        self.assertEqual(preset.chart_config.png_compress_level, 0)
        self.assertEqual(preset.chart_config.video_crf, 22)
        self.assertEqual(preset.chart_config.video_bitrate, "8M")
        self.assertEqual(preset.chart_config.ffmpeg_preset, "slow")
        self.assertEqual(preset.chart_config.frame_output_mode, "ffmpeg_stream")
        self.assertEqual(preset.chart_config.title_font_family, "DejaVu Serif")
        self.assertEqual(preset.chart_config.subtitle_font_family, "DejaVu Sans Mono")
        self.assertEqual(preset.chart_config.label_font_family, "DejaVu Serif")
        self.assertEqual(preset.chart_config.value_font_family, "DejaVu Sans Mono")
        self.assertEqual(preset.chart_config.time_label_font_family, "DejaVu Serif")
        self.assertEqual(preset.chart_config.source_font_family, "DejaVu Sans Mono")
        self.assertEqual(preset.chart_config.rank_label_font_family, "DejaVu Serif")
        self.assertEqual(preset.chart_config.title_text_color, "#101112")
        self.assertEqual(preset.chart_config.subtitle_text_color, "#202122")
        self.assertEqual(preset.chart_config.label_text_color, "#303132")
        self.assertEqual(preset.chart_config.value_text_color, "#404142")
        self.assertEqual(preset.chart_config.time_label_text_color, "#505152")
        self.assertEqual(preset.chart_config.source_text_color, "#606162")
        self.assertEqual(preset.chart_config.rank_label_text_color, "#707172")
        self.assertEqual(preset.chart_config.title_font_size, 42)
        self.assertEqual(preset.chart_config.rank_label_font_size, 17)
        self.assertEqual(preset.chart_config.title_x, 300)
        self.assertEqual(preset.chart_config.title_y, 90)
        self.assertEqual(preset.chart_config.subtitle_x, 310)
        self.assertEqual(preset.chart_config.subtitle_y, 160)
        self.assertEqual(preset.chart_config.time_label_x, 1500)
        self.assertEqual(preset.chart_config.time_label_y, 900)
        self.assertEqual(preset.chart_config.source_x, 300)
        self.assertEqual(preset.chart_config.source_y, 1000)
        self.assertEqual(preset.chart_config.animation.easing, "ease_out_cubic")
        self.assertFalse(preset.chart_config.animation.enter_exit)
        self.assertFalse(preset.chart_config.animation.value_smoothing)
        self.assertEqual(preset.chart_config.animation.motion_mode, "continuous")
        self.assertEqual(preset.chart_config.selection.top_n, 5)
        self.assertTrue(preset.chart_config.selection.aggregate_other)
        self.assertEqual(preset.chart_config.selection.other_label, "Rest")
        self.assertEqual(preset.chart_config.selection.other_color, "#999999")
        self.assertEqual(preset.data_source_config.csv_path, "data/custom.csv")
        self.assertEqual(
            preset.data_source_config.source_label_override,
            "Source: Custom data",
        )
        self.assertEqual(
            preset.data_source_config.source_label,
            "Source: Custom data",
        )
        self.assertEqual(preset.dataset_config.year_column, "date")
        self.assertEqual(preset.dataset_config.name_column, "name")
        self.assertEqual(preset.dataset_config.value_column, "amount")
        self.assertTrue(preset.dataset_config.allow_negative_values)
        self.assertEqual(preset.dataset_config.category_labels["Coal"], "Carbon")
        self.assertEqual(preset.dataset_config.category_colors["Coal"], "#333333")
        self.assertEqual(preset.dataset_config.category_logos["Coal"], "logos/coal.png")
        self.assertEqual(
            preset.dataset_config.category_secondary_logos["Coal"],
            "logos_secondary/coal.png",
        )
        self.assertEqual(preset.dataset_config.category_colors["Solar"], "#F2C94C")

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

    def test_rejects_invalid_categories_section(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"categories": []}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_unknown_category_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"categories": {"Coal": {"unknown": "value"}}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_blank_category_label(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"categories": {"Coal": {"label": ""}}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_blank_category_logo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"categories": {"Coal": {"logo": ""}}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_blank_category_secondary_logo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"categories": {"Coal": {"secondary_logo": ""}}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_blank_source_label_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"data_source": {"source_label_override": ""}}),
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

    def test_rejects_unknown_motion_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"animation": {"motion_mode": "unknown"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_unknown_bar_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"bar_shape": "triangle"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_invalid_bar_appearance_values(self):
        invalid_values = (
            {"bar_border_enabled": "yes"},
            {"bar_border_width": -1},
            {"bar_shadow_alpha": 1.5},
            {"bar_appearance_mode": "expert"},
            {"bar_fill_type": "image"},
            {"bar_gradient_color_count": 4},
            {"bar_texture_preset": "marble"},
            {"bar_texture_scale": 0},
            {"bar_glow_opacity": 2},
            {"bar_value_position": "center"},
        )

        for chart in invalid_values:
            with self.subTest(chart=chart), tempfile.TemporaryDirectory() as temp_dir:
                project_path = Path(temp_dir) / "bad.json"
                project_path.write_text(
                    json.dumps({"chart": chart}),
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

    def test_rejects_invalid_png_compress_level(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"png_compress_level": 10}}),
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

    def test_rejects_blank_element_font_family(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"title_font_family": " "}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_invalid_element_font_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"title_font_size": 0}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_negative_element_position(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"title_x": -1}}),
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

    def test_rejects_invalid_rank_label_spacing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"rank_label_label_gap": -1}}),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFileError):
                load_project_file(project_path)

    def test_rejects_invalid_value_label_min_x(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "bad.json"
            project_path.write_text(
                json.dumps({"chart": {"value_label_min_x": -1}}),
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
