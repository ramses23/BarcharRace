from pathlib import Path

import streamlit.components.v1 as components


_COMPONENT_DIR = Path(__file__).resolve().parent / "components" / "text_layout_editor"
_text_layout_component = components.declare_component(
    "text_layout_editor",
    path=str(_COMPONENT_DIR),
)

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
    result = _text_layout_component(
        canvas_width=int(canvas_width),
        canvas_height=int(canvas_height),
        dpi=int(dpi),
        positions=normalized_positions,
        preset_positions=normalized_preset_positions,
        elements=elements,
        theme=theme,
        layout=layout,
        default=normalized_positions,
        key=key,
    )
    return _normalize_positions(result, fallback=normalized_positions)


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
