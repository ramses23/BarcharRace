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
            "ui.bar_style_editor._bar_style_component",
            return_value=result_value,
        ) as component:
            result = bar_style_editor(
                settings={"bar_shape": "rectangle"},
                bar_colors=("#111111", "#222222", "#333333", "#444444"),
                background_color="#FFFFFF",
                key="bars",
            )

        self.assertEqual(result["bar_shape"], "capsule")
        self.assertTrue(result["bar_border_enabled"])
        self.assertEqual(component.call_args.kwargs["bar_colors"], [
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

    def test_frontend_has_live_preview_and_four_shape_buttons(self):
        component_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ui"
            / "components"
            / "bar_style_editor"
            / "index.html"
        )
        html = component_path.read_text(encoding="utf-8")

        for shape in ("rectangle", "rounded", "capsule", "lollipop"):
            self.assertIn(f'data-shape="{shape}"', html)

        self.assertIn('id="preview"', html)
        for tab in (
            "fill",
            "texture",
            "depth",
            "effects",
            "track",
            "content",
            "frame",
        ):
            self.assertIn(f'data-tab="{tab}"', html)

        self.assertIn('data-mode="advanced"', html)
        self.assertIn('data-key="bar_inner_shadow_opacity"', html)
        self.assertIn('data-key="bar_outer_glow_enabled"', html)
        self.assertIn('data-key="bar_track_enabled"', html)
        self.assertIn('data-key="bar_logo_position"', html)
        self.assertIn('<option value="inside_right">Inside right</option>', html)
        self.assertIn('data-key="bar_logo_shape"', html)
        self.assertIn('data-key="bar_logo_border_enabled"', html)
        self.assertIn('data-key="bar_logo_background_enabled"', html)
        self.assertIn('data-key="bar_secondary_logo_enabled"', html)
        self.assertIn('data-key="bar_secondary_logo_layout"', html)
        self.assertIn('<option value="side_by_side">Side by side</option>', html)
        self.assertIn('<option value="independent">Independent positions</option>', html)
        self.assertIn('data-key="bar_secondary_logo_badge_corner"', html)
        self.assertIn('data-key="bar_secondary_logo_shape"', html)
        self.assertIn('data-key="bar_label_alignment"', html)
        self.assertIn('data-key="bar_value_position"', html)
        self.assertIn('update("bar_shape", button.dataset.shape)', html)
        self.assertIn('setComponentValue(clone(state.settings))', html)


if __name__ == "__main__":
    unittest.main()
