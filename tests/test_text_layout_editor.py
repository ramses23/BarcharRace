import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from ui.text_layout_editor import _normalize_positions, text_layout_editor


POSITIONS = {
    "title": {"x": 320, "y": 95},
    "subtitle": {"x": 320, "y": 165},
    "date": {"x": 1580, "y": 910},
    "source": {"x": 320, "y": 1005},
}


class TextLayoutEditorTest(unittest.TestCase):
    def test_normalizes_positions_and_rejects_negative_coordinates(self):
        normalized = _normalize_positions({
            **POSITIONS,
            "title": {"x": 280.6, "y": -5},
        })

        self.assertEqual(normalized["title"], {"x": 281, "y": 0})
        self.assertEqual(normalized["date"], POSITIONS["date"])

    def test_returns_component_positions(self):
        moved = {
            **POSITIONS,
            "title": {"x": 240, "y": 80},
        }

        with patch(
            "ui.text_layout_editor.component_state_value",
            return_value=moved,
        ), patch(
            "ui.text_layout_editor.component_v2_runtime_available",
            return_value=True,
        ), patch(
            "ui.text_layout_editor.component_renderer",
        ) as renderer:
            component = renderer.return_value
            result = text_layout_editor(
                canvas_width=1920,
                canvas_height=1080,
                dpi=150,
                positions=POSITIONS,
                preset_positions=POSITIONS,
                elements={},
                theme={},
                layout={},
                key="layout",
            )

        self.assertEqual(result["title"], {"x": 240, "y": 80})
        data = component.call_args.kwargs["data"]
        self.assertEqual(data["positions"], moved)
        self.assertEqual(data["preset_positions"], POSITIONS)

    def test_frontend_supports_drag_keyboard_alignment_and_reset(self):
        component_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ui"
            / "components"
            / "text_layout_editor"
            / "component.js"
        )
        javascript = component_path.read_text(encoding="utf-8")

        self.assertIn("export default function (component)", javascript)
        self.assertIn("node.onpointerdown", javascript)
        self.assertIn("state.stage.onkeydown", javascript)
        self.assertIn('["center", "Center X"]', javascript)
        self.assertIn('["reset", "Reset preset"]', javascript)
        self.assertIn('setStateValue("positions"', javascript)
        self.assertNotIn("postMessage", javascript)


if __name__ == "__main__":
    unittest.main()
