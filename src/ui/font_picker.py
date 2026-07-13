from pathlib import Path

import streamlit.components.v1 as components
from matplotlib import font_manager


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

_COMPONENT_DIR = Path(__file__).resolve().parent / "components" / "font_picker"
_font_picker_component = components.declare_component(
    "font_family_picker",
    path=str(_COMPONENT_DIR),
)


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
    selected = _font_picker_component(
        label=label,
        options=available_common_font_families(current_value),
        value=current_value or "",
        theme_default_label="Project default",
        default=current_value or "",
        key=key,
    )
    return selected or None
