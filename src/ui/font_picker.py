import streamlit as st
from matplotlib import font_manager

from ui.component_v2 import (
    component_renderer,
    component_source,
    component_state_value,
    component_v2_runtime_available,
)


COMMON_FONT_FAMILIES = (
    "Arial",
    "Arial Narrow",
    "Bahnschrift",
    "Book Antiqua",
    "Calibri",
    "Cambria",
    "Candara",
    "Century Gothic",
    "Comic Sans MS",
    "Consolas",
    "Constantia",
    "Corbel",
    "Courier New",
    "DejaVu Sans",
    "DejaVu Sans Mono",
    "DejaVu Serif",
    "Franklin Gothic Medium",
    "Garamond",
    "Georgia",
    "Impact",
    "Lucida Console",
    "Lucida Sans Unicode",
    "Microsoft Sans Serif",
    "Palatino Linotype",
    "Rockwell",
    "Segoe UI",
    "Tahoma",
    "Times New Roman",
    "Trebuchet MS",
    "Verdana",
)

_COMPONENT_HTML = """
<div data-component="font-family-picker"></div>
"""
_COMPONENT_CSS = component_source("font_picker", "component.css")
_COMPONENT_JS = component_source("font_picker", "component.js")


def available_common_font_families(current_value=None):
    installed = {
        entry.name.strip()
        for entry in font_manager.fontManager.ttflist
        if entry.name and entry.name.strip()
    }
    options = [
        family
        for family in COMMON_FONT_FAMILIES
        if family in installed
    ]

    if current_value and current_value not in options:
        options = [current_value, *options[:29]]

    return tuple(options[:30])


def font_family_picker(label, current_value=None, key=None):
    selected = component_state_value(key, "value", current_value or "")
    options = available_common_font_families(selected)

    if not component_v2_runtime_available():
        fallback_options = ("", *options)
        return st.selectbox(
            label,
            fallback_options,
            index=(
                fallback_options.index(selected)
                if selected in fallback_options
                else 0
            ),
            format_func=lambda value: value or "Project default",
            key=key,
        ) or None

    component = component_renderer(
        "font_family_picker_v2",
        html=_COMPONENT_HTML,
        css=_COMPONENT_CSS,
        js=_COMPONENT_JS,
    )
    component(
        data={
            "label": label,
            "options": options,
            "value": selected,
            "theme_default_label": "Project default",
        },
        key=key,
        height="content",
    )
    return selected or None
