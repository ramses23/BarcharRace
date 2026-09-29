import unittest
import base64
import shutil
import subprocess
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
    @unittest.skipUnless(shutil.which("node"), "Node.js required for component test")
    def test_frontend_mount_props_and_consumed_event_do_not_emit_again(self):
        javascript = (
            Path(__file__).resolve().parents[1]
            / "src/ui/components/editorial_layout_editor/component.js"
        ).read_text(encoding="utf-8")
        script = r"""
class Element {
  constructor() {
    this.children = []
    this.className = ""
    this.dataset = {}
    this.clientWidth = 720
    this.style = { setProperty() {} }
  }
  append(...nodes) { this.children.push(...nodes) }
  appendChild(node) { this.append(node) }
  replaceChildren(...nodes) { this.children = nodes }
  setAttribute() {}
  setPointerCapture() {}
  remove() {}
  querySelector(selector) {
    if (this.className.split(" ").includes(selector.slice(1))) return this
    for (const child of this.children) {
      const found = child.querySelector(selector)
      if (found) return found
    }
    return null
  }
}
globalThis.document = { createElement: () => new Element() }
globalThis.ResizeObserver = class { observe() {} disconnect() {} }
const { default: render } = await import('data:text/javascript;base64,__SOURCE__')
const parentElement = new Element()
const emitted = []
const setStateValue = (key, value) => emitted.push([key, value])
const data = {
  canvas_width: 1920, canvas_height: 1080,
  min_width: 240, min_height: 140, block_min_width: 160, block_min_height: 100,
  rect: { x: 960, y: 583, width: 883, height: 367 },
  rects: {}, composition: 'card', overlay: {}, theme: {},
}
render({ data, parentElement, setStateValue })
render({ data, parentElement, setStateValue })
render({ data: { ...data, rect: { ...data.rect, x: 1021 } }, parentElement, setStateValue })
if (emitted.length !== 0) throw new Error('Mount or props emitted geometry')
let card = parentElement.querySelector('.editorial-card-editor')
card.onpointerdown({ target: { dataset: {} }, pointerId: 1, clientX: 0, clientY: 0,
                     preventDefault() {} })
card.onpointerup({ pointerId: 1 })
if (emitted.length !== 0) throw new Error('No-op drag emitted geometry')
card.onkeydown({ key: 'ArrowLeft', shiftKey: false, preventDefault() {} })
if (emitted.length !== 1 || emitted[0][0] !== 'geometry')
  throw new Error('Real gesture did not emit exactly once')
const accepted = emitted[0][1].rect
render({ data: { ...data, rect: accepted }, parentElement, setStateValue })
render({ data: { ...data, rect: accepted }, parentElement, setStateValue })
if (emitted.length !== 1) throw new Error('Consumed event emitted again')
"""
        script = script.replace(
            "__SOURCE__", base64.b64encode(javascript.encode("utf-8")).decode("ascii"),
        )
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

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
                "block": "card",
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

    def test_independent_block_event_and_mount_keep_separate_rects(self):
        text = {"x": 620, "y": 120, "width": 300, "height": 180}
        image = {"x": 420, "y": 370, "width": 220, "height": 160}
        with patch("ui.editorial_layout_editor.component_state_value", return_value={
            "block": "image", "rect": {**image, "x": 450},
            "base_rect": image, "event_id": "blocks:1",
        }):
            state = editorial_layout_component_state(
                key="blocks", rect=text, canvas_width=1000, canvas_height=600,
            )
        self.assertEqual(state["block"], "image")
        moved, _, accepted = reconcile_editorial_geometry(
            current_rect=image, component_state=state, consumed_event_id=None,
            canvas_width=1000, canvas_height=600, min_width=160, min_height=100,
        )
        self.assertTrue(accepted)
        self.assertEqual(moved["x"], 450)
        self.assertEqual(text["x"], 620)
        with patch("ui.editorial_layout_editor.component_v2_runtime_available", return_value=True), patch(
            "ui.editorial_layout_editor.component_renderer",
        ) as renderer:
            editorial_layout_editor(
                canvas_width=1000, canvas_height=600, rect=text,
                rects={"text": text, "image": moved}, composition="independent",
                key="blocks",
            )
        data = renderer.return_value.call_args.kwargs["data"]
        self.assertEqual(data["rects"], {"text": text, "image": moved})
        self.assertEqual(data["block_min_width"], 160)

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
        self.assertIn('"text", "image"', javascript)
        self.assertIn("state.rects[block] = next", javascript)
        self.assertNotIn('setStateValue("trace"', javascript)
        self.assertEqual(javascript.count('setStateValue("geometry"'), 1)
        self.assertIn('if (JSON.stringify(current) !== JSON.stringify(baseRect)) emit', javascript)
        self.assertIn('if (JSON.stringify(resolved) !== JSON.stringify(baseRect)) emit', javascript)
        self.assertNotIn("postMessage", javascript)


if __name__ == "__main__":
    unittest.main()
