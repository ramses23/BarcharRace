import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import _test_path
from PIL import Image
from ui.bar_style_editor import (
    _custom_texture_data,
    bar_style_editor,
    normalize_bar_style,
    visible_bar_style_fields,
)


class BarStyleEditorTest(unittest.TestCase):
    def test_normalizes_shape_colors_and_numeric_ranges(self):
        settings = normalize_bar_style({
            "bar_shape": "lollipop",
            "bar_appearance_mode": "advanced",
            "bar_gradient_enabled": False,
            "bar_border_enabled": True,
            "bar_border_color": "#abc123",
            "bar_border_width": 99,
            "bar_shadow_alpha": -1,
            "bar_shadow_offset_x": 50,
            "bar_texture_preset": "carbon",
            "bar_texture_scale": 20,
            "bar_texture_custom_image": " textures/custom.png ",
        })

        self.assertEqual(settings["bar_shape"], "lollipop")
        self.assertEqual(settings["bar_appearance_mode"], "advanced")
        self.assertFalse(settings["bar_gradient_enabled"])
        self.assertTrue(settings["bar_border_enabled"])
        self.assertEqual(settings["bar_border_color"], "#ABC123")
        self.assertEqual(settings["bar_border_width"], 12.0)
        self.assertEqual(settings["bar_shadow_alpha"], 0.0)
        self.assertEqual(settings["bar_shadow_offset_x"], 40)
        self.assertEqual(settings["bar_texture_preset"], "carbon")
        self.assertEqual(settings["bar_texture_scale"], 8.0)
        self.assertEqual(
            settings["bar_texture_custom_image"],
            "textures/custom.png",
        )

    def test_returns_normalized_component_result(self):
        result_value = {
            "bar_shape": "capsule",
            "bar_border_enabled": True,
            "bar_border_color": "#123456",
        }

        with patch(
            "ui.bar_style_editor.component_state_value",
            return_value=result_value,
        ), patch(
            "ui.bar_style_editor.component_v2_runtime_available",
            return_value=True,
        ), patch(
            "ui.bar_style_editor.component_renderer",
        ) as renderer:
            component = renderer.return_value
            result = bar_style_editor(
                settings={"bar_shape": "rectangle"},
                bar_colors=("#111111", "#222222", "#333333", "#444444"),
                background_color="#FFFFFF",
                key="bars",
            )

        self.assertEqual(result["bar_shape"], "capsule")
        self.assertTrue(result["bar_border_enabled"])
        self.assertEqual(component.call_args.kwargs["data"]["bar_colors"], [
            "#111111",
            "#222222",
            "#333333",
        ])

    def test_normalizes_logo_layout_and_migrates_legacy_positions(self):
        settings = normalize_bar_style({
            "bar_logo_position": "inside_right",
            "bar_logo_shape": "circle",
            "bar_logo_padding": 99,
            "bar_logo_border_enabled": True,
            "bar_logo_border_color": "#aabbcc",
            "bar_logo_border_width": 12,
            "bar_logo_background_enabled": True,
            "bar_logo_background_opacity": -1,
            "bar_label_alignment": "left",
        })
        legacy = normalize_bar_style({"bar_logo_position": "inside"})

        self.assertEqual(settings["bar_logo_position"], "inside_right")
        self.assertEqual(settings["bar_logo_shape"], "circle")
        self.assertEqual(settings["bar_logo_padding"], 20.0)
        self.assertTrue(settings["bar_logo_border_enabled"])
        self.assertEqual(settings["bar_logo_border_color"], "#AABBCC")
        self.assertEqual(settings["bar_logo_border_width"], 8.0)
        self.assertTrue(settings["bar_logo_background_enabled"])
        self.assertEqual(settings["bar_logo_background_opacity"], 0.0)
        self.assertEqual(legacy["bar_logo_position"], "inside_left")
        self.assertEqual(settings["bar_label_alignment"], "left")

    def test_normalizes_secondary_logo_layout_and_style(self):
        settings = normalize_bar_style({
            "bar_secondary_logo_enabled": True,
            "bar_secondary_logo_layout": "side_by_side",
            "bar_secondary_logo_position": "inside_left",
            "bar_secondary_logo_badge_corner": "top_left",
            "bar_secondary_logo_shape": "rounded",
            "bar_secondary_logo_size": 999,
            "bar_secondary_logo_gap": -5,
            "bar_secondary_logo_padding": 99,
            "bar_secondary_logo_border_enabled": True,
            "bar_secondary_logo_border_color": "#123abc",
            "bar_secondary_logo_border_width": 99,
            "bar_secondary_logo_background_enabled": True,
            "bar_secondary_logo_background_opacity": 2,
        })

        self.assertTrue(settings["bar_secondary_logo_enabled"])
        self.assertEqual(settings["bar_secondary_logo_layout"], "side_by_side")
        self.assertEqual(settings["bar_secondary_logo_position"], "inside_left")
        self.assertEqual(settings["bar_secondary_logo_badge_corner"], "top_left")
        self.assertEqual(settings["bar_secondary_logo_shape"], "rounded")
        self.assertEqual(settings["bar_secondary_logo_size"], 160.0)
        self.assertEqual(settings["bar_secondary_logo_gap"], 0.0)
        self.assertEqual(settings["bar_secondary_logo_padding"], 20.0)
        self.assertEqual(settings["bar_secondary_logo_border_color"], "#123ABC")
        self.assertEqual(settings["bar_secondary_logo_border_width"], 8.0)
        self.assertEqual(settings["bar_secondary_logo_background_opacity"], 1.0)

    def test_builds_small_data_url_for_custom_texture_preview(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            texture_path = Path(temp_dir) / "texture.png"
            Image.new("RGB", (24, 24), "#123456").save(texture_path)

            data_url = _custom_texture_data({
                "bar_texture_preset": "custom_image",
                "bar_texture_custom_image": str(texture_path),
            })

        self.assertTrue(data_url.startswith("data:image/png;base64,"))

    def test_contextual_fields_follow_parent_controls(self):
        simple_fields = {
            field["field"]
            for field in visible_bar_style_fields({
                "bar_appearance_mode": "simple",
                "bar_border_enabled": False,
            })
        }
        advanced_fields = {
            field["field"]
            for field in visible_bar_style_fields({
                "bar_appearance_mode": "advanced",
                "bar_fill_type": "texture",
                "bar_texture_enabled": True,
                "bar_secondary_logo_enabled": False,
                "bar_outer_glow_enabled": False,
            })
        }

        self.assertIn("bar_gradient_enabled", simple_fields)
        self.assertNotIn("bar_fill_type", simple_fields)
        self.assertNotIn("bar_border_color", simple_fields)
        self.assertIn("bar_texture_preset", advanced_fields)
        self.assertNotIn("bar_gradient_direction", advanced_fields)
        self.assertNotIn("bar_secondary_logo_layout", advanced_fields)
        self.assertNotIn("bar_glow_color", advanced_fields)

    def test_frontend_has_live_preview_and_four_shape_buttons(self):
        component_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ui"
            / "components"
            / "bar_style_editor"
            / "component.js"
        )
        javascript = component_path.read_text(encoding="utf-8")

        for shape in ("rectangle", "rounded", "capsule", "lollipop"):
            self.assertIn(f'"{shape}"', javascript)

        self.assertIn("renderPreview(state)", javascript)
        self.assertIn("renderFields(state)", javascript)
        self.assertIn('setStateValue("settings"', javascript)
        self.assertIn("export default function (component)", javascript)
        self.assertNotIn("postMessage", javascript)


if __name__ == "__main__":
    unittest.main()
