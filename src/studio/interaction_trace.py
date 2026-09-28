"""Temporary, opt-in JSONL diagnostics for a physical Studio interaction."""

import contextlib
import contextvars
import itertools
import json
import os
import tempfile
import threading
import time
from pathlib import Path


ENABLED = os.environ.get("BCS_TRACE_STUDIO") == "1"
TRACE_PATH = Path(tempfile.gettempdir()) / "bcs_studio_interaction_trace.jsonl"
_START = time.perf_counter()
_SEQUENCE = itertools.count(1)
_LOCK = threading.RLock()
_CONTEXT = contextvars.ContextVar("bcs_studio_trace_context", default={})
_PREVIOUS_DEPENDENCIES = {}
_CACHE_CONTRACTS = {
    "studio_layout_preview": "selected-frame editorial/layout geometry and visual config",
    "value_axis_bundle": "dataset, periods, visible-row and numeric axis layout",
    "value_axis_resolver": "numeric sprites, axis settings and transition timing",
    "preview_scale_resolver": "numeric/visual sprite sets, scale, motion and ranking settings",
    "podium_rank_history": "numeric ranks/values, timeline, motion, visibility and podium settings; not editorial style",
}


def set_context(**fields):
    if ENABLED:
        _CONTEXT.set({**_CONTEXT.get(), **fields})


def begin_rerun(session_state):
    if not ENABLED:
        return
    rerun = int(session_state.get("_bcs_trace_rerun", 0)) + 1
    session_state["_bcs_trace_rerun"] = rerun
    current = {}
    for key, value in session_state.items():
        if (key.startswith(("fun_facts_", "preview_", "studio_editor_section"))
                and isinstance(value, (str, int, float, bool, type(None)))):
            current[key] = value
    previous = session_state.get("_bcs_trace_widgets", {})
    changed = {key: {"old": previous.get(key), "new": value}
               for key, value in current.items() if previous.get(key) != value}
    session_state["_bcs_trace_widgets"] = current
    source = ", ".join(changed) if changed else "rerun/no scalar widget change"
    _CONTEXT.set({"rerun_id": rerun, "event_source": source,
                  "preview_requested": False, "active_fun_fact_id": None,
                  "layout": None, "composition": None})
    emit("rerun_start", changed_controls=changed)


def emit(event, **fields):
    if not ENABLED:
        return
    with _LOCK:
        record = {
            "sequence": next(_SEQUENCE), "rerun_id": _CONTEXT.get().get("rerun_id"),
            "elapsed_seconds": round(time.perf_counter() - _START, 6),
            "event": event, **_CONTEXT.get(), **fields,
        }
        try:
            with TRACE_PATH.open("a", encoding="utf-8") as output:
                output.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError:
            # A diagnostic log must not interrupt a real Studio session.
            pass


@contextlib.contextmanager
def stage(name):
    if not ENABLED:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        emit("stage", stage=name, duration_seconds=round(time.perf_counter() - started, 6))


def cache(name, key, dependencies, *, hit):
    if not ENABLED:
        return
    key_hex = key.hex() if isinstance(key, bytes) else str(key)
    key_short = key_hex[:16]
    with _LOCK:
        previous = _PREVIOUS_DEPENDENCIES.get(name)
        changes = (
            _changed_fields(previous[1], dependencies)
            if previous is not None else {"initial": "no previous dependency payload"}
        )
        reason = None if hit else (
            "cold" if previous is None else
            "key_changed" if previous[0] != key_hex else "evicted_or_restarted"
        )
        _PREVIOUS_DEPENDENCIES[name] = (key_hex, dependencies)
    emit("cache", cache=name, key=key_short, result="HIT" if hit else "MISS",
         miss_reason=reason, changed_dependencies=changes if not hit else {},
         logical_dependency_contract=_CACHE_CONTRACTS.get(name))


def _changed_fields(old, new, prefix=""):
    if isinstance(old, dict) and isinstance(new, dict):
        result = {}
        for key in old.keys() | new.keys():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(_changed_fields(old.get(key), new.get(key), path))
        return result
    if old != new:
        return {prefix: {"old": old, "new": new}}
    return {}


def rect(source):
    if not isinstance(source, dict):
        return None
    return {key: source.get(key) for key in ("x", "y", "width", "height")}


def project_rect(project_data, block="card"):
    facts = (project_data or {}).get("fun_facts") or {}
    return {field: facts.get(f"editorial_{block}_{field}")
            for field in ("x", "y", "width", "height")}


def geometry_write(source, before, after, **fields):
    if ENABLED:
        emit("geometry_write", writer=source, old=rect(before), new=rect(after),
             changed=rect(before) != rect(after), **fields)
