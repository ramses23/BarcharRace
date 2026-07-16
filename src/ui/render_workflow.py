import pandas as pd
import streamlit as st

from studio.render_preflight import run_render_preflight
from ui.render_controller import render_result_from_status, start_background_render


BACKGROUND_RENDER_STATE = "background_render"
LAST_RENDER_STATUS_STATE = "last_render_status"
LAST_PREFLIGHT_STATE = "last_render_preflight"


def start_render_with_preflight(project_file, *, root_dir):
    project_path = root_dir / project_file
    preflight = run_render_preflight(project_path, root_dir=root_dir)
    st.session_state[LAST_PREFLIGHT_STATE] = preflight.as_dict()

    if not preflight.ready:
        st.error("Render preflight found errors. Review the checks below.")
        return

    try:
        background_render = start_background_render(
            project_path,
            root_dir=root_dir,
        )
    except OSError as exc:
        st.error(f"Could not start the render process: {exc}")
        return

    st.session_state[BACKGROUND_RENDER_STATE] = background_render
    st.session_state[LAST_RENDER_STATUS_STATE] = None
    st.rerun()


def render_workflow_panel():
    _show_preflight_results()
    background_render = st.session_state.get(BACKGROUND_RENDER_STATE)

    if background_render is not None:
        status = background_render.status()
        if status.get("state") not in {"completed", "failed", "canceled"}:
            _active_render_fragment()
            return

        _finish_background_render(status)

    _show_last_render_status()


@st.fragment(run_every=1.0)
def _active_render_fragment():
    background_render = st.session_state.get(BACKGROUND_RENDER_STATE)
    if background_render is None:
        return

    status = background_render.status()
    state = status.get("state", "starting")
    if state in {"completed", "failed", "canceled"}:
        _finish_background_render(status)
        st.rerun()

    with st.container(border=True):
        st.subheader("Video render")
        progress = max(0.0, min(1.0, float(status.get("progress", 0.0))))
        st.progress(progress)
        message = status.get("message", "Rendering video")
        current = int(status.get("current", 0))
        total = int(status.get("total", 0))

        if total:
            message = f"{message}: {current:,}/{total:,}"

        st.caption(message)
        status_column, cancel_column = st.columns([3, 1])
        status_column.caption(
            f"Isolated process {background_render.pid} · "
            f"log: {background_render.log_path}"
        )
        if cancel_column.button(
            "Cancel render",
            icon=":material/cancel:",
            width="stretch",
            key="cancel_background_render",
        ):
            canceled_status = background_render.cancel()
            _finish_background_render(canceled_status)
            st.rerun()


def _finish_background_render(status):
    st.session_state[LAST_RENDER_STATUS_STATE] = status
    st.session_state[BACKGROUND_RENDER_STATE] = None


def _show_preflight_results():
    preflight = st.session_state.get(LAST_PREFLIGHT_STATE)
    if not isinstance(preflight, dict):
        return

    label = "Render preflight passed" if preflight.get("ready") else "Render preflight"
    with st.expander(label, expanded=not preflight.get("ready", False)):
        for check in preflight.get("checks", []):
            level = check.get("level")
            icon = {"ok": "✓", "warning": "⚠", "error": "✕"}.get(level, "•")
            st.markdown(
                f"{icon} **{check.get('label', 'Check')}** — "
                f"{check.get('message', '')}"
            )


def _show_last_render_status():
    status = st.session_state.get(LAST_RENDER_STATUS_STATE)
    if not isinstance(status, dict):
        return

    state = status.get("state")
    with st.container(border=True):
        if state == "completed":
            output_file = status.get("output_file") or status.get("result", {}).get(
                "output_file",
                "",
            )
            st.success(f"Rendered {output_file}")
            result = render_result_from_status(status)
            if result is not None:
                show_render_profile(result)
        elif state == "canceled":
            st.warning(status.get("message", "Render canceled."))
        else:
            st.error(status.get("error") or status.get("message", "Render failed."))
            if status.get("log_path"):
                st.caption(f"Log: {status['log_path']}")

        if st.button(
            "Dismiss render status",
            icon=":material/close:",
            key="dismiss_render_status",
        ):
            st.session_state[LAST_RENDER_STATUS_STATE] = None
            st.rerun()


def show_render_profile(result):
    profile = result.profile
    total_seconds = profile.total_seconds

    st.subheader("Render profile")
    total_column, frames_column, average_column, transitions_column = st.columns(4)
    total_column.metric("Total", _format_seconds(total_seconds))
    frames_column.metric("Frames", f"{result.frames_rendered:,}")
    average_column.metric("Avg / frame", _format_seconds(result.average_frame_seconds))
    transitions_column.metric("Transitions", f"{result.transitions_rendered:,}")

    render_overhead_seconds = max(
        0.0,
        profile.render_frames_seconds
        - profile.draw_frames_seconds
        - profile.save_frames_seconds,
    )
    rows = (
        _profile_row("Load data", profile.load_data_seconds, total_seconds),
        _profile_row("Validate data", profile.validate_data_seconds, total_seconds),
        _profile_row("Build timeline", profile.build_timeline_seconds, total_seconds),
        _profile_row("Clean frames", profile.cleanup_seconds, total_seconds),
        _profile_row("Precompute sprites", profile.precompute_sprites_seconds, total_seconds),
        _profile_row("Draw frames", profile.draw_frames_seconds, total_seconds),
        _profile_row("Extract / save frames", profile.save_frames_seconds, total_seconds),
        _profile_row("Render overhead", render_overhead_seconds, total_seconds),
        _profile_row("Export MP4", profile.export_video_seconds, total_seconds),
    )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _profile_row(stage, seconds, total_seconds):
    share = (seconds / total_seconds * 100) if total_seconds else 0.0

    return {
        "Stage": stage,
        "Seconds": round(seconds, 3),
        "Share": f"{share:.1f}%",
    }


def _format_seconds(seconds):
    return f"{seconds:.3f}s"
