from ui.component_v2 import (
    component_renderer,
    component_source,
    component_v2_runtime_available,
)


_COMPONENT_HTML = """
<span data-floating-preview-controller hidden></span>
"""
_COMPONENT_CSS = component_source("floating_preview", "component.css")
_COMPONENT_JS = component_source("floating_preview", "component.js")


def floating_preview_controller(
    *,
    target_selector=".st-key-latest_preview",
    breakpoint=900,
    top_offset=80,
    key=None,
):
    if not component_v2_runtime_available():
        return

    component = component_renderer(
        "floating_preview_controller_v2",
        html=_COMPONENT_HTML,
        css=_COMPONENT_CSS,
        js=_COMPONENT_JS,
    )
    component(
        data={
            "target_selector": target_selector,
            "breakpoint": int(breakpoint),
            "top_offset": int(top_offset),
        },
        key=key,
        height="content",
    )
