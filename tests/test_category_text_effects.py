import unittest
import json
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import _test_path
import numpy as np

from config.chart_config import ChartConfig
from config.export_config import ExportConfig
from config.project_file_loader import ProjectFileError, load_project_data
from core.rank_motion import visual_rank_motion_sprite
from models.bar_sprite import BarSprite
from models.scene import Scene
from renderer.bar_renderer import BarRenderer
from pipeline.render_job import RenderJob
from studio.appearance_presets import (
    build_appearance_preset,
    load_appearance_preset,
    save_appearance_preset,
)
from studio.preview import render_project_preview
from studio.project_builder import build_project_data, project_form_values
from studio.project_runtime import resolve_project_preset_paths
from studio.short_export import apply_export_profile
from ui.bar_style_editor import normalize_bar_style, visible_bar_style_fields


class CategoryTextEffectsTest(unittest.TestCase):
    EFFECT_VALUES = {
        "bar_label_border_enabled": True,
        "bar_label_border_color": "#123456",
        "bar_label_border_opacity": 0.65,
        "bar_label_border_width": 2.5,
        "bar_label_shadow_enabled": True,
        "bar_label_shadow_color": "#654321",
        "bar_label_shadow_opacity": 0.35,
        "bar_label_shadow_offset_x": 4,
        "bar_label_shadow_offset_y": -3,
    }

    @staticmethod
    def _config(**values):
        defaults = {
            "width": 480,
            "height": 240,
            "dpi": 72,
            "left_margin": 150,
            "right_margin": 30,
            "label_min_x": 20,
            "label_font_size": 26,
            "bar_label_position": "inside_left",
            "bar_label_alignment": "left",
            "category_labels_enabled": True,
            "rank_labels_enabled": False,
            "value_labels_enabled": False,
            "logos_enabled": False,
            "title_enabled": False,
            "subtitle_enabled": False,
            "time_label_enabled": False,
            "source_label_enabled": False,
            "background_color_override": "#F6F6F6",
            "bar_gradient_enabled": False,
        }
        defaults.update(values)
        return ChartConfig(**defaults)

    @staticmethod
    def _sprite(**values):
        defaults = {
            "name": "United States",
            "value": 100,
            "color": "#4E79A7",
            "x": 150,
            "y": 120,
            "width": 260,
            "height": 44,
            "rank": 1,
        }
        defaults.update(values)
        return BarSprite(**defaults)

    def _render(self, config, sprite=None):
        renderer = BarRenderer(config=config)
        sprite = sprite or self._sprite()
        try:
            rgba = np.frombuffer(
                renderer.render_rgba(Scene(title="", bars=[sprite])),
                dtype=np.uint8,
            ).reshape((config.height, config.width, 4)).copy()
            commands = renderer._text_bar_artist.commands
            command = commands[0] if commands else None
            layout = renderer._bar_label_layout(
                visual_rank_motion_sprite(sprite)
            )
            return rgba, command, layout
        finally:
            renderer.close()

    def test_defaults_are_disabled_and_legacy_pixels_are_unchanged(self):
        defaults = ChartConfig()
        self.assertFalse(defaults.bar_label_border_enabled)
        self.assertFalse(defaults.bar_label_shadow_enabled)
        self.assertFalse(hasattr(defaults, "bar_label_shadow_blur"))

        implicit, _, _ = self._render(self._config())
        explicit, _, _ = self._render(self._config(
            bar_label_border_enabled=False,
            bar_label_shadow_enabled=False,
        ))
        np.testing.assert_array_equal(implicit, explicit)

    def test_border_is_a_glyph_outline_not_a_bbox_rectangle(self):
        plain, plain_command, _ = self._render(self._config(
            label_text_color="#FFFFFF",
        ))
        outlined, outlined_command, _ = self._render(self._config(
            label_text_color="#FFFFFF",
            bar_label_border_enabled=True,
            bar_label_border_color="#FF0000",
            bar_label_border_width=2,
        ))
        plain_sprite = plain_command[0]
        outlined_sprite = outlined_command[0]

        self.assertGreater(
            np.count_nonzero(outlined_sprite[:, :, 3]),
            np.count_nonzero(plain_sprite[:, :, 3]),
        )
        self.assertTrue(all(
            outlined_sprite[y, x, 3] == 0
            for y, x in (
                (0, 0), (0, -1), (-1, 0), (-1, -1),
            )
        ))
        self.assertFalse(np.array_equal(plain, outlined))

    def test_border_color_opacity_width_and_global_alpha(self):
        thin, thin_command, _ = self._render(self._config(
            label_text_color="#FFFFFF",
            label_text_opacity=0.5,
            bar_label_border_enabled=True,
            bar_label_border_color="#FF0000",
            bar_label_border_opacity=0.5,
            bar_label_border_width=1,
        ))
        _, thick_command, _ = self._render(self._config(
            label_text_color="#FFFFFF",
            label_text_opacity=0.5,
            bar_label_border_enabled=True,
            bar_label_border_color="#FF0000",
            bar_label_border_opacity=0.5,
            bar_label_border_width=3,
        ))
        image = thin_command[0]
        red = (
            (image[:, :, 0] > 220)
            & (image[:, :, 1] < 40)
            & (image[:, :, 2] < 40)
        )
        white = np.all(image[:, :, :3] > 220, axis=2)

        self.assertTrue(np.any(red))
        red_alpha = image[:, :, 3][red]
        dominant_red_alpha = int(np.bincount(red_alpha[red_alpha > 0]).argmax())
        self.assertGreaterEqual(dominant_red_alpha, 63)
        self.assertLessEqual(dominant_red_alpha, 65)
        self.assertGreaterEqual(int(image[:, :, 3][white].max()), 125)
        self.assertLessEqual(int(image[:, :, 3][white].max()), 128)
        self.assertGreater(
            np.count_nonzero(thick_command[0][:, :, 3]),
            np.count_nonzero(thin_command[0][:, :, 3]),
        )
        self.assertGreater(np.count_nonzero(thin[:, :, 3]), 0)

    def test_shadow_color_opacity_and_offsets(self):
        _, command, _ = self._render(self._config(
            label_text_color="#FF0000",
            label_text_opacity=0.5,
            bar_label_shadow_enabled=True,
            bar_label_shadow_color="#0000FF",
            bar_label_shadow_opacity=0.4,
            bar_label_shadow_offset_x=8,
            bar_label_shadow_offset_y=6,
        ))
        image = command[0]
        red = (
            (image[:, :, 0] > 220)
            & (image[:, :, 1] < 40)
            & (image[:, :, 2] < 40)
        )
        blue = (
            (image[:, :, 2] > 220)
            & (image[:, :, 0] < 40)
            & (image[:, :, 1] < 40)
        )
        red_y, red_x = np.where(red)
        blue_y, blue_x = np.where(blue)

        self.assertGreater(blue_x.mean(), red_x.mean())
        self.assertLess(blue_y.mean(), red_y.mean())
        blue_alpha = image[:, :, 3][blue]
        dominant_blue_alpha = int(
            np.bincount(blue_alpha[blue_alpha > 0]).argmax()
        )
        self.assertGreaterEqual(dominant_blue_alpha, 50)
        self.assertLessEqual(dominant_blue_alpha, 52)

    def test_border_and_shadow_render_together_without_changing_fill(self):
        _, command, _ = self._render(self._config(
            label_text_color="#00FF00",
            bar_label_border_enabled=True,
            bar_label_border_color="#FF0000",
            bar_label_border_width=2,
            bar_label_shadow_enabled=True,
            bar_label_shadow_color="#0000FF",
            bar_label_shadow_opacity=1,
            bar_label_shadow_offset_x=7,
            bar_label_shadow_offset_y=5,
        ))
        image = command[0]
        colors = {
            "red": (image[:, :, 0] > 220) & (image[:, :, 1] < 40),
            "green": (image[:, :, 1] > 220) & (image[:, :, 0] < 40),
            "blue": (image[:, :, 2] > 220) & (image[:, :, 0] < 40),
        }
        self.assertTrue(all(np.any(mask) for mask in colors.values()))

    def test_disabled_effect_values_are_dormant(self):
        first, _, _ = self._render(self._config(
            bar_label_border_enabled=False,
            bar_label_border_color="#FF0000",
            bar_label_border_width=8,
            bar_label_shadow_enabled=False,
            bar_label_shadow_color="#00FF00",
            bar_label_shadow_offset_x=20,
        ))
        second, _, _ = self._render(self._config(
            bar_label_border_enabled=False,
            bar_label_border_color="#0000FF",
            bar_label_border_width=0,
            bar_label_shadow_enabled=False,
            bar_label_shadow_color="#FFFFFF",
            bar_label_shadow_offset_x=-20,
        ))
        np.testing.assert_array_equal(first, second)

    def test_effects_are_exclusive_to_category_text(self):
        base = self._config(
            category_labels_enabled=False,
            rank_labels_enabled=True,
            value_labels_enabled=True,
            title_enabled=True,
            subtitle_enabled=True,
            time_label_enabled=True,
            source_label_enabled=True,
        )
        effects = replace(
            base,
            bar_label_border_enabled=True,
            bar_label_border_color="#FF0000",
            bar_label_border_width=5,
            bar_label_shadow_enabled=True,
            bar_label_shadow_color="#0000FF",
            bar_label_shadow_opacity=1,
            bar_label_shadow_offset_x=8,
            bar_label_shadow_offset_y=8,
        )
        scene = Scene(
            title="Title",
            subtitle="Subtitle",
            time_label="2026",
            source_label="Source",
            bars=[self._sprite()],
        )
        outputs = []
        for chart in (base, effects):
            renderer = BarRenderer(config=chart)
            try:
                outputs.append(renderer.render_rgba(scene))
            finally:
                renderer.close()
        self.assertEqual(outputs[0], outputs[1])

    def test_effects_follow_font_weight_and_style_cache_keys(self):
        images = []
        keys = []
        for weight, style in (
            ("normal", "normal"),
            ("bold", "normal"),
            ("normal", "italic"),
        ):
            config = self._config(
                label_font_weight=weight,
                label_font_style=style,
                bar_label_border_enabled=True,
                bar_label_shadow_enabled=True,
            )
            _, command, _ = self._render(config)
            images.append(command[0])
            renderer = BarRenderer(config=config)
            try:
                renderer._text_command(
                    "Category", 100, 100,
                    ha="left", va="center",
                    font_size=config.label_font_size,
                    font_family=config.label_font_family,
                    font_weight=weight,
                    font_style=style,
                    color="#FFFFFF",
                    stroke_width=1,
                    stroke_color="#000000",
                    shadow_offset=(1, 1),
                    shadow_color="#000000",
                    shadow_opacity=0.5,
                )
                keys.append(next(iter(renderer._text_sprite_cache)))
            finally:
                renderer.close()
        self.assertEqual(len(set(keys)), 3)
        self.assertNotEqual(images[0].shape, images[1].shape)

    def test_effects_do_not_change_positions_alignment_offsets_or_fitting(self):
        sprite = self._sprite(name="A very long category name")
        positions = (
            "outside_left", "inside_left", "inside_center",
            "inside_right", "outside_right", "above",
        )
        for position in positions:
            for alignment in ("left", "center", "right"):
                with self.subTest(position=position, alignment=alignment):
                    base = self._config(
                        bar_label_position=position,
                        bar_label_alignment=alignment,
                        bar_label_offset_x=7,
                        bar_label_offset_y=-4,
                    )
                    effects = replace(
                        base,
                        bar_label_border_enabled=True,
                        bar_label_shadow_enabled=True,
                    )
                    first = BarRenderer(config=base)
                    second = BarRenderer(config=effects)
                    try:
                        self.assertEqual(
                            first._bar_label_layout(sprite),
                            second._bar_label_layout(sprite),
                        )
                    finally:
                        first.close()
                        second.close()

    def test_primary_and_secondary_logo_geometry_is_unchanged(self):
        sprite = self._sprite(
            logo_path="primary.png",
            secondary_logo_path="secondary.png",
        )
        base = self._config(
            logos_enabled=True,
            bar_logo_position="inside_right",
            bar_secondary_logo_enabled=True,
            bar_secondary_logo_layout="side_by_side",
        )
        effects = replace(
            base,
            bar_label_border_enabled=True,
            bar_label_shadow_enabled=True,
        )
        first = BarRenderer(config=base)
        second = BarRenderer(config=effects)
        try:
            self.assertEqual(first._logo_layout(sprite), second._logo_layout(sprite))
            self.assertEqual(
                first._logo_layout(sprite, slot="secondary"),
                second._logo_layout(sprite, slot="secondary"),
            )
            self.assertEqual(
                first._bar_label_layout(sprite),
                second._bar_label_layout(sprite),
            )
        finally:
            first.close()
            second.close()

    def test_short_bar_and_long_category_remain_safe(self):
        config = self._config(
            bar_label_border_enabled=True,
            bar_label_shadow_enabled=True,
            bar_label_position="inside_right",
            bar_logo_position="inside_left",
            logos_enabled=True,
        )
        _, command, layout = self._render(
            config,
            self._sprite(
                name="United States of America",
                width=32,
                logo_path="missing.png",
            ),
        )
        self.assertEqual(layout["text"], "")
        self.assertIsNone(command)

    def test_rank_motion_states_keep_fill_border_and_shadow_in_one_command(self):
        config = self._config(
            label_text_color="#00FF00",
            bar_label_border_enabled=True,
            bar_label_border_color="#FF0000",
            bar_label_border_width=2,
            bar_label_shadow_enabled=True,
            bar_label_shadow_color="#0000FF",
            bar_label_shadow_opacity=1,
            bar_label_shadow_offset_x=6,
            bar_label_shadow_offset_y=4,
        )
        for state, target in (
            ("rising", 80), ("falling", 160), ("stable", None),
        ):
            sprite = self._sprite(
                y=120,
                rank_motion_state=state,
                rank_motion_progress=0.5,
                rank_motion_target=target,
            )
            with self.subTest(state=state):
                _, command, _ = self._render(config, sprite)
                self.assertIsNotNone(command)
                image = command[0]
                self.assertTrue(np.any(image[:, :, 0] > 220))
                self.assertTrue(np.any(image[:, :, 1] > 220))
                self.assertTrue(np.any(image[:, :, 2] > 220))

    def test_effect_command_is_independent_of_bar_fill_mode(self):
        modes = (
            self._config(
                bar_gradient_enabled=False,
                bar_label_border_enabled=True,
                bar_label_shadow_enabled=True,
            ),
            self._config(
                bar_gradient_enabled=True,
                bar_label_border_enabled=True,
                bar_label_shadow_enabled=True,
            ),
            self._config(
                bar_appearance_mode="advanced",
                bar_fill_type="solid",
                bar_bevel_enabled=True,
                bar_label_border_enabled=True,
                bar_label_shadow_enabled=True,
            ),
        )
        commands = [self._render(config)[1] for config in modes]
        for command in commands[1:]:
            np.testing.assert_array_equal(commands[0][0], command[0])
            self.assertEqual(commands[0][1:], command[1:])

    def test_standard_and_short_render_effects_without_canvas_clipping(self):
        standard = self._config(
            width=1920,
            height=1080,
            dpi=150,
            left_margin=320,
            label_min_x=80,
            label_font_size=28,
            bar_label_border_enabled=True,
            bar_label_shadow_enabled=True,
        )
        short = apply_export_profile(standard, ExportConfig(mode="short"))
        for config in (standard, short):
            sprite = self._sprite(
                x=config.left_margin,
                y=config.height / 2,
                width=max(100, config.width - config.left_margin - 80),
            )
            with self.subTest(size=(config.width, config.height)):
                _, command, _ = self._render(config, sprite)
                image, left, bottom = command
                self.assertGreaterEqual(left, 0)
                self.assertGreaterEqual(bottom, 0)
                self.assertLessEqual(left + image.shape[1], config.width)
                self.assertLessEqual(bottom + image.shape[0], config.height)

    def test_project_loader_roundtrip_and_legacy_defaults(self):
        current = load_project_data({
            "schema_version": 3,
            "name": "effects",
            "chart": dict(self.EFFECT_VALUES),
        }).chart_config
        legacy = load_project_data({
            "schema_version": 3,
            "name": "legacy",
            "chart": {},
        }).chart_config

        for key, value in self.EFFECT_VALUES.items():
            self.assertEqual(getattr(current, key), value)
        self.assertFalse(legacy.bar_label_border_enabled)
        self.assertFalse(legacy.bar_label_shadow_enabled)

    def test_project_loader_rejects_invalid_effect_values(self):
        invalid_cases = (
            ("bar_label_border_enabled", "yes"),
            ("bar_label_border_opacity", 1.1),
            ("bar_label_border_width", -1),
            ("bar_label_shadow_color", ""),
            ("bar_label_shadow_opacity", -0.1),
            ("bar_label_shadow_offset_x", 1.5),
        )
        for field, value in invalid_cases:
            with self.subTest(field=field):
                with self.assertRaises(ProjectFileError):
                    load_project_data({
                        "schema_version": 3,
                        "name": "invalid",
                        "chart": {field: value},
                    })

    def test_editor_conditionals_preserve_hidden_effect_settings(self):
        stored = normalize_bar_style(dict(self.EFFECT_VALUES))
        disabled = normalize_bar_style({
            **stored,
            "bar_label_border_enabled": False,
            "bar_label_shadow_enabled": False,
        })
        hidden_fields = {
            item["field"] for item in visible_bar_style_fields(disabled)
        }
        restored = normalize_bar_style({
            **disabled,
            "bar_label_border_enabled": True,
            "bar_label_shadow_enabled": True,
        })
        visible_fields = {
            item["field"] for item in visible_bar_style_fields(restored)
        }

        self.assertNotIn("bar_label_border_color", hidden_fields)
        self.assertNotIn("bar_label_shadow_color", hidden_fields)
        self.assertEqual(
            disabled["bar_label_border_color"],
            self.EFFECT_VALUES["bar_label_border_color"],
        )
        self.assertEqual(
            disabled["bar_label_shadow_offset_y"],
            self.EFFECT_VALUES["bar_label_shadow_offset_y"],
        )
        self.assertIn("bar_label_border_color", visible_fields)
        self.assertIn("bar_label_shadow_color", visible_fields)

    def test_project_builder_generated_json_and_form_values_roundtrip(self):
        project = self._project_data(bar_style=self.EFFECT_VALUES)
        values = project_form_values(project)

        for key, value in self.EFFECT_VALUES.items():
            self.assertEqual(project["chart"][key], value)
            self.assertEqual(values[key], value)
        json.loads(json.dumps(project))

    def test_appearance_preset_roundtrip_and_v12_migration(self):
        project = self._project_data(bar_style=self.EFFECT_VALUES)
        preset = build_appearance_preset("Category Effects", project)

        with tempfile.TemporaryDirectory() as temp_dir:
            saved = save_appearance_preset(preset, temp_dir)
            loaded = load_appearance_preset(saved.path)
            legacy_data = preset.to_dict()
            legacy_data["schema_version"] = 12
            for key in self.EFFECT_VALUES:
                del legacy_data["bars"][key]
            legacy_path = Path(temp_dir) / "legacy-v12.json"
            legacy_path.write_text(
                json.dumps(legacy_data),
                encoding="utf-8",
            )
            legacy = load_appearance_preset(legacy_path)

        for key, value in self.EFFECT_VALUES.items():
            self.assertEqual(loaded.bars[key], value)
        self.assertFalse(legacy.bars["bar_label_border_enabled"])
        self.assertFalse(legacy.bars["bar_label_shadow_enabled"])

    def test_preview_and_render_job_receive_identical_effect_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "data.csv").write_text(
                "year,name,value\n0,A,100\n1,A,120\n",
                encoding="utf-8",
            )
            project = self._project_data(
                bar_style=self.EFFECT_VALUES,
                steps_per_transition=1,
            )
            project["chart"].update({
                "width": 320,
                "height": 180,
                "dpi": 72,
                "frame_output_mode": "png_sequence",
                "logos_enabled": False,
            })
            preset = resolve_project_preset_paths(
                load_project_data(project),
                project_root=root,
                output_root=root,
            )
            with patch("pipeline.render_job.BarRenderer") as render_renderer:
                with patch("pipeline.render_job.VideoExporter"):
                    with patch("builtins.print"):
                        RenderJob(
                            config=preset.chart_config,
                            data_source_config=preset.data_source_config,
                            dataset_config=preset.dataset_config,
                            fun_fact_config=preset.fun_fact_config,
                            export_config=preset.export_config,
                            project_root=root,
                            output_file_is_effective=True,
                        ).run()
            with patch("studio.preview.BarRenderer") as preview_renderer:
                preview_renderer.return_value.render.return_value = str(
                    root / "preview.png"
                )
                render_project_preview(
                    root / "project.json",
                    output_dir=root / "preview",
                    root_dir=root,
                    project_data=project,
                    year=0,
                )

            render_config = render_renderer.call_args.kwargs["config"]
            preview_config = preview_renderer.call_args.kwargs["config"]
            render_scene = render_renderer.return_value.render.call_args_list[0].args[0]
            preview_scene = preview_renderer.return_value.render.call_args.args[0]

        for key, value in self.EFFECT_VALUES.items():
            self.assertEqual(getattr(render_config, key), value)
            self.assertEqual(getattr(preview_config, key), value)
        self.assertEqual(render_scene.bars, preview_scene.bars)

    @staticmethod
    def _project_data(**overrides):
        values = {
            "name": "category-effects",
            "csv_path": "data.csv",
            "year_column": "year",
            "name_column": "name",
            "value_column": "value",
            "title": "Effects",
            "source_label": "Source",
            "output_file": "out.mp4",
            "frames_dir": "frames",
            "layout_preset": "youtube_1080p",
            "theme": "clean_report",
            "typography_preset": "studio",
            "value_format": "decimal",
            "fps": 30,
            "steps_per_transition": 2,
            "top_n": 2,
            "max_visible_bars": 2,
        }
        values.update(overrides)
        return build_project_data(**values)


if __name__ == "__main__":
    unittest.main()
