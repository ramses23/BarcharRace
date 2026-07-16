import copy
from pathlib import Path

import streamlit as st
from streamlit.components.v2.get_bidi_component_manager import (
    get_bidi_component_manager,
)
from streamlit.runtime import Runtime


_COMPONENTS_DIR = Path(__file__).resolve().parent / "components"
_RENDERERS = {}


def component_source(component_name, filename):
    return (
        _COMPONENTS_DIR / component_name / filename
    ).read_text(encoding="utf-8")


def component_state_value(key, field, fallback):
    if not key:
        return copy.deepcopy(fallback)

    state = st.session_state.get(key)
    if isinstance(state, dict):
        value = state.get(field, fallback)
    else:
        value = getattr(state, field, fallback)

    return copy.deepcopy(value)


def component_v2_runtime_available():
    return Runtime.exists()


def component_renderer(name, *, html, css, js):
    manager = get_bidi_component_manager()
    cached = _RENDERERS.get(name)

    if cached is None or manager.get(name) is None:
        cached = st.components.v2.component(
            name,
            html=html,
            css=css,
            js=js,
        )
        _RENDERERS[name] = cached

    return cached
