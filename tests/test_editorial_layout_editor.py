import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from studio.fun_fact_layout import clamp_editorial_rect
from ui.editorial_layout_editor import (
    editorial_layout_component_state,
    editorial_layout_editor,
    reconcile_editorial_geometry,
)


class EditorialLayoutEditorTest(unittest.TestCase):
    def test_clamp_preserves_minimum_size_and_canvas_bounds(self):
        self.assertEqual(
            clamp_editorial_rect(900, 520, 120, 80, 1000, 600),
            (760, 460, 240, 140),
        )
        self.assertEqual(
            clamp_editorial_rect(-20, -30, 1400, 900, 1000, 600),
            (0, 0, 1000, 600),
        )

    def test_component_state_normalizes_emitted_geometry(self):
        with patch(
            "ui.editorial_layout_editor.component_state_value",
            return_value={
                "rect": {"x": 950, "y": 570, "width": 300, "height": 200},
                "base_rect": {"x": 0, "y": 0, "width": 400, "height": 200},
                "event_id": "instance-a:4",
            },
        ):
            state = editorial_layout_component_state(
                key="editor",
                rect={"x": 0, "y": 0, "width": 400, "height": 200},
                canvas_width=1000,
                canvas_height=600,
            )

        self.assertEqual(
            state,
            {
                "rect": {"x": 700, "y": 400, "width": 300, "height": 200},
                "base_rect": {"x": 0, "y": 0, "width": 400, "height": 200},
                "event_id": "instance-a:4",
            },
        )

    def test_mount_is_controlled_by_python_rect(self):
        rect = {"x": 500, "y": 300, "width": 400, "height": 220}
        with patch(
            "ui.editorial_layout_editor.component_v2_runtime_available",
            return_value=True,
        ), patch(
            "ui.editorial_layout_editor.component_renderer",
        ) as renderer:
            component = renderer.return_value
            result = editorial_layout_editor(
                canvas_width=1000,
                canvas_height=600,
                rect=rect,
                overlay={"bar_rects": []},
                theme={"background_color": "#112233"},
                key="editor",
            )

        self.assertEqual(result, rect)
        data = component.call_args.kwargs["data"]
        self.assertEqual(data["rect"], rect)
        self.assertEqual(data["min_width"], 240)
        self.assertEqual(data["min_height"], 140)

    def test_reconciliation_accepts_events_after_component_remounts(self):
        current = {"x": 100, "y": 80, "width": 400, "height": 220}
        consumed = None
        events = (
            ("instance-a:1", {"x": 120, "y": 90, "width": 400, "height": 220}),
            ("instance-a:2", {"x": 120, "y": 90, "width": 460, "height": 240}),
            ("instance-b:1", {"x": 140, "y": 100, "width": 460, "height": 240}),
            ("instance-c:1", {"x": 160, "y": 110, "width": 500, "height": 260}),
        )
        for event_id, emitted in events:
            current, consumed, accepted = reconcile_editorial_geometry(
                current_rect=current,
                component_state={
                    "rect": emitted,
                    "base_rect": current,
                    "event_id": event_id,
                },
                consumed_event_id=consumed,
                canvas_width=1000,
                canvas_height=600,
            )
            self.assertTrue(accepted)
            self.assertEqual(current, emitted)
            self.assertEqual(consumed, event_id)

    def test_reconciliation_rejects_replayed_and_stale_base_geometry(self):
        current = {"x": 300, "y": 180, "width": 420, "height": 240}
        replayed, consumed, accepted = reconcile_editorial_geometry(
            current_rect=current,
            component_state={
                "rect": {"x": 100, "y": 80, "width": 400, "height": 220},
                "base_rect": {"x": 80, "y": 70, "width": 400, "height": 220},
                "event_id": "instance-a:4",
            },
            consumed_event_id="instance-a:4",
            canvas_width=1000,
            canvas_height=600,
        )
        self.assertFalse(accepted)
        self.assertEqual(replayed, current)

        stale, consumed, accepted = reconcile_editorial_geometry(
            current_rect=current,
            component_state={
                "rect": {"x": 120, "y": 90, "width": 460, "height": 240},
                "base_rect": {"x": 100, "y": 80, "width": 400, "height": 220},
                "event_id": "instance-b:1",
            },
            consumed_event_id=consumed,
            canvas_width=1000,
            canvas_height=600,
        )
        self.assertFalse(accepted)
        self.assertEqual(stale, current)
        self.assertEqual(consumed, "instance-b:1")

    def test_reconciliation_stress_survives_reruns_numeric_updates_and_sections(self):
        current = {"x": 80, "y": 60, "width": 400, "height": 220}
        consumed = None

        def consume(event_id, emitted, base):
            return reconcile_editorial_geometry(
                current_rect=current,
                component_state={
                    "rect": emitted,
                    "base_rect": base,
                    "event_id": event_id,
                },
                consumed_event_id=consumed,
                canvas_width=1200,
                canvas_height=700,
            )

        moved = {"x": 120, "y": 90, "width": 400, "height": 220}
        current, consumed, accepted = consume("drag-instance:1", moved, current)
        self.assertTrue(accepted)

        replay, replay_consumed, accepted = consume("drag-instance:1", moved, current)
        self.assertFalse(accepted)
        self.assertEqual(replay, current)
        self.assertEqual(replay_consumed, consumed)

        resized = {"x": 120, "y": 90, "width": 520, "height": 280}
        current, consumed, accepted = consume("drag-instance:2", resized, current)
        self.assertTrue(accepted)

        numeric = {"x": 300, "y": 140, "width": 480, "height": 260}
        previous = current
        current = numeric
        stale, consumed, accepted = consume(
            "drag-instance:3",
            {"x": 160, "y": 100, "width": 540, "height": 300},
            previous,
        )
        self.assertFalse(accepted)
        self.assertEqual(stale, numeric)

        after_section_return = {
            "x": 320, "y": 160, "width": 500, "height": 280,
        }
        current, consumed, accepted = consume(
            "remounted-instance:1",
            after_section_return,
            numeric,
        )
        self.assertTrue(accepted)
        self.assertEqual(current, after_section_return)

    def test_frontend_has_eight_handles_pointerup_and_keyboard_support(self):
        javascript = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ui"
            / "components"
            / "editorial_layout_editor"
            / "component.js"
        ).read_text(encoding="utf-8")

        self.assertIn('["n", "s", "e", "w", "ne", "nw", "se", "sw"]', javascript)
        self.assertIn("card.onpointerup", javascript)
        self.assertIn("card.onkeydown", javascript)
        self.assertIn('setStateValue("geometry"', javascript)
        self.assertIn("ResizeObserver", javascript)
        self.assertIn("base_rect", javascript)
        self.assertIn("event_id", javascript)
        self.assertIn("if (state.drag) return", javascript)
        self.assertIn("onlostpointercapture", javascript)
        self.assertNotIn("postMessage", javascript)


if __name__ == "__main__":
    unittest.main()
