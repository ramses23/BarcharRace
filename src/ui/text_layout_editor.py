from ui.component_v2 import (
    component_renderer,
    component_source,
    component_state_value,
    component_v2_runtime_available,
)

_COMPONENT_HTML = """
<div data-component="text-layout-editor"></div>
"""
_COMPONENT_CSS = component_source("text_layout_editor", "component.css")
_COMPONENT_JS = component_source("text_layout_editor", "component.js")

_ELEMENT_NAMES = ("title", "subtitle", "date", "source")


def text_layout_editor(
    *,
    canvas_width,
    canvas_height,
    dpi,
    positions,
    preset_positions=None,
    elements,
    theme,
    layout,
    key=None,
):
    normalized_positions = _normalize_positions(positions)
    normalized_preset_positions = _normalize_positions(
        preset_positions,
        fallback=normalized_positions,
    )
    current_positions = _normalize_positions(
        component_state_value(key, "positions", normalized_positions),
        fallback=normalized_positions,
    )
    if not component_v2_runtime_available():
        return current_positions

    component = component_renderer(
        "text_layout_editor_v2",
        html=_COMPONENT_HTML,
        css=_COMPONENT_CSS,
        js=_COMPONENT_JS,
    )
    component(
        data={
            "canvas_width": int(canvas_width),
            "canvas_height": int(canvas_height),
            "dpi": int(dpi),
            "positions": current_positions,
            "preset_positions": normalized_preset_positions,
            "elements": elements,
            "theme": theme,
            "layout": layout,
        },
        key=key,
        height="content",
    )
    return current_positions


def _normalize_positions(positions, fallback=None):
    positions = positions if isinstance(positions, dict) else {}
    fallback = fallback if isinstance(fallback, dict) else {}
    normalized = {}

    for name in _ELEMENT_NAMES:
        value = positions.get(name)
        fallback_value = fallback.get(name, {"x": 0, "y": 0})

        if not isinstance(value, dict):
            value = fallback_value

        normalized[name] = {
            "x": _coordinate(value.get("x"), fallback_value.get("x", 0)),
            "y": _coordinate(value.get("y"), fallback_value.get("y", 0)),
        }

    return normalized


def _coordinate(value, fallback):
    try:
        return max(0, int(round(float(value))))
    except (TypeError, ValueError):
        return max(0, int(round(float(fallback))))
