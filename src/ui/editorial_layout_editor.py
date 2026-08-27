from studio.fun_fact_layout import clamp_editorial_rect
from ui.component_v2 import (
    component_renderer,
    component_source,
    component_state_value,
    component_v2_runtime_available,
)


_COMPONENT_HTML = '<div data-component="editorial-layout-editor"></div>'
_COMPONENT_CSS = component_source("editorial_layout_editor", "component.css")
_COMPONENT_JS = component_source("editorial_layout_editor", "component.js")


def editorial_layout_component_state(
    *,
    key,
    rect,
    canvas_width,
    canvas_height,
):
    fallback = {
        "rect": _rect_dict(rect, canvas_width, canvas_height),
        "base_rect": None,
        "event_id": None,
    }
    value = component_state_value(key, "geometry", fallback)
    if not isinstance(value, dict):
        value = fallback
    base_rect = value.get("base_rect")
    return {
        "rect": _rect_dict(
            value.get("rect", fallback["rect"]),
            canvas_width,
            canvas_height,
        ),
        "base_rect": (
            _rect_dict(base_rect, canvas_width, canvas_height)
            if isinstance(base_rect, dict)
            else None
        ),
        "event_id": _event_id(value.get("event_id")),
    }


def reconcile_editorial_geometry(
    *,
    current_rect,
    component_state,
    consumed_event_id,
    canvas_width,
    canvas_height,
):
    """Consume one gesture event without treating component state as authority."""
    current = _rect_dict(current_rect, canvas_width, canvas_height)
    state = component_state if isinstance(component_state, dict) else {}
    event_id = _event_id(state.get("event_id"))

    if event_id is None or event_id == consumed_event_id:
        return current, consumed_event_id, False

    base_rect = state.get("base_rect")
    if not isinstance(base_rect, dict):
        return current, event_id, False
    base_rect = _rect_dict(base_rect, canvas_width, canvas_height)

    if base_rect != current:
        return current, event_id, False

    emitted = _rect_dict(
        state.get("rect", current),
        canvas_width,
        canvas_height,
    )
    return emitted, event_id, True


def editorial_layout_editor(
    *,
    canvas_width,
    canvas_height,
    rect,
    overlay=None,
    theme=None,
    key=None,
):
    rect = _rect_dict(rect, canvas_width, canvas_height)
    if not component_v2_runtime_available():
        return rect
    component = component_renderer(
        "editorial_layout_editor_v2",
        html=_COMPONENT_HTML,
        css=_COMPONENT_CSS,
        js=_COMPONENT_JS,
    )
    component(
        data={
            "canvas_width": int(canvas_width),
            "canvas_height": int(canvas_height),
            "rect": rect,
            "overlay": overlay if isinstance(overlay, dict) else {},
            "theme": theme if isinstance(theme, dict) else {},
            "min_width": min(240, int(canvas_width)),
            "min_height": min(140, int(canvas_height)),
        },
        key=key,
        height="content",
    )
    return rect


def _rect_dict(rect, canvas_width, canvas_height):
    rect = rect if isinstance(rect, dict) else {}
    left, top, width, height = clamp_editorial_rect(
        rect.get("x", 0),
        rect.get("y", 0),
        rect.get("width", canvas_width),
        rect.get("height", canvas_height),
        canvas_width,
        canvas_height,
    )
    return {"x": left, "y": top, "width": width, "height": height}


def _event_id(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None
