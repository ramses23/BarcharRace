import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import _test_path
from ui.font_picker import (
    COMMON_FONT_FAMILIES,
    available_common_font_families,
    font_family_picker,
)


class FontPickerTest(unittest.TestCase):
    def test_limits_options_to_thirty_common_installed_fonts(self):
        options = available_common_font_families()

        self.assertLessEqual(len(options), 30)
        self.assertTrue(set(options).issubset(COMMON_FONT_FAMILIES))
        self.assertIn("DejaVu Sans", options)

    def test_preserves_existing_custom_font_without_exceeding_limit(self):
        installed_entries = [
            SimpleNamespace(name=family)
            for family in COMMON_FONT_FAMILIES
        ]

        with patch("ui.font_picker.font_manager.fontManager.ttflist", installed_entries):
            options = available_common_font_families("Custom Project Font")

        self.assertEqual(options[0], "Custom Project Font")
        self.assertEqual(len(options), 30)

    def test_component_receives_curated_options_and_returns_selection(self):
        with patch(
            "ui.font_picker.component_state_value",
            return_value="Georgia",
        ), patch(
            "ui.font_picker.component_v2_runtime_available",
            return_value=True,
        ), patch(
            "ui.font_picker.component_renderer",
        ) as renderer:
            component = renderer.return_value
            selected = font_family_picker(
                "Title font",
                current_value="Arial",
                key="title_font",
            )

        self.assertEqual(selected, "Georgia")
        data = component.call_args.kwargs["data"]
        self.assertLessEqual(len(data["options"]), 30)
        self.assertEqual(data["value"], "Georgia")

    def test_frontend_renders_font_name_and_sample_with_option_family(self):
        component_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ui"
            / "components"
            / "font_picker"
            / "component.js"
        )
        javascript = component_path.read_text(encoding="utf-8")

        self.assertIn("export default function (component)", javascript)
        self.assertIn("button.style.fontFamily = fontStyle(value)", javascript)
        self.assertIn('sample.textContent = "Aa 123"', javascript)
        self.assertIn('setStateValue("value", value)', javascript)
        self.assertNotIn("postMessage", javascript)


if __name__ == "__main__":
    unittest.main()
