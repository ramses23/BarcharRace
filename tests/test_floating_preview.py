import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from ui.floating_preview import floating_preview_controller


class FloatingPreviewTest(unittest.TestCase):
    def test_mounts_invisible_viewport_controller(self):
        with patch(
            "ui.floating_preview.component_v2_runtime_available",
            return_value=True,
        ), patch(
            "ui.floating_preview.component_renderer",
        ) as renderer:
            component = renderer.return_value
            floating_preview_controller(key="preview-controller")

        self.assertEqual(
            component.call_args.kwargs["data"]["target_selector"],
            ".st-key-latest_preview",
        )
        self.assertEqual(
            component.call_args.kwargs["data"]["breakpoint"],
            900,
        )
        self.assertEqual(
            component.call_args.kwargs["data"]["top_offset"],
            80,
        )
        self.assertEqual(
            component.call_args.kwargs["key"],
            "preview-controller",
        )

    def test_frontend_anchors_to_viewport_and_cleans_up(self):
        component_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ui"
            / "components"
            / "floating_preview"
            / "component.js"
        )
        javascript = component_path.read_text(encoding="utf-8")

        self.assertIn('target.style.position = "fixed"', javascript)
        self.assertIn('window.addEventListener("scroll"', javascript)
        self.assertIn('window.addEventListener("resize"', javascript)
        self.assertIn("window.innerWidth <= state.breakpoint", javascript)
        self.assertIn("ResizeObserver", javascript)
        self.assertIn("MutationObserver", javascript)
        self.assertIn("state.placeholder.getBoundingClientRect()", javascript)
        self.assertIn('window.removeEventListener("scroll"', javascript)
        self.assertNotIn("postMessage", javascript)


if __name__ == "__main__":
    unittest.main()
