from dataclasses import replace
from pathlib import Path

from config.export_config import ExportConfig
from config.layout_config import apply_layout_preset
from models.scene import ShortOverlay
from utils.video_duration import estimate_video_duration


SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920


def resolve_export_output_path(output_file, export_config=None):
    output_path = Path(output_file)
    export_config = export_config or ExportConfig()
    if not export_config.is_short or output_path.stem.casefold().endswith("_short"):
        return output_path
    return output_path.with_name(
        f"{output_path.stem}_short{output_path.suffix}"
    )


def apply_export_profile(chart_config, export_config=None):
    export_config = export_config or ExportConfig()
    if not export_config.is_short:
        return chart_config

    x_scale = SHORT_WIDTH / max(1, chart_config.width)
    short_config = apply_layout_preset(chart_config, "vertical_shorts")

    def scaled_x(value):
        return None if value is None else int(round(value * x_scale))

    return replace(
        short_config,
        title_x=scaled_x(chart_config.title_x),
        subtitle_x=scaled_x(chart_config.subtitle_x),
        title_max_width=scaled_x(chart_config.title_max_width),
        subtitle_max_width=max(1, scaled_x(chart_config.subtitle_max_width)),
        source_max_width=max(1, scaled_x(chart_config.source_max_width)),
        value_label_gap=max(1, scaled_x(chart_config.value_label_gap)),
        value_label_min_x=scaled_x(chart_config.value_label_min_x),
        value_label_inside_padding=max(
            1, scaled_x(chart_config.value_label_inside_padding)
        ),
    )


def resolve_export_periods(periods, export_config=None):
    periods = tuple(periods)
    export_config = export_config or ExportConfig()
    if not export_config.is_short:
        return periods
    if not periods:
        return periods

    start = (
        periods[0]
        if export_config.short_from_period is None
        else export_config.short_from_period
    )
    end = (
        periods[-1]
        if export_config.short_to_period is None
        else export_config.short_to_period
    )
    try:
        start_index = periods.index(start)
        end_index = periods.index(end)
    except ValueError as exc:
        raise ValueError("Short export range must use available timeline periods.") from exc
    if start_index > end_index:
        raise ValueError("Short export From period cannot be after To period.")
    return periods[start_index : end_index + 1]


def estimate_export_duration(periods, chart_config, export_config=None):
    selected_periods = resolve_export_periods(periods, export_config)
    return estimate_video_duration(
        period_count=len(selected_periods),
        steps_per_transition=chart_config.steps_per_transition,
        fps=chart_config.fps,
        continuous_motion=chart_config.animation.continuous_motion,
    )


def short_fun_fact_config(fun_fact_config, export_config=None):
    export_config = export_config or ExportConfig()
    if (
        export_config.is_short
        and not export_config.short_include_fun_facts
        and fun_fact_config.enabled
    ):
        return replace(fun_fact_config, enabled=False)
    return fun_fact_config


def short_overlay_for_frame(
    export_config,
    *,
    frame_index,
    total_frames,
    fps,
):
    export_config = export_config or ExportConfig()
    if not export_config.is_short or total_frames <= 0:
        return None

    fps = max(1, int(fps))
    frame_index = max(0, min(int(frame_index), total_frames - 1))
    elapsed = frame_index / fps
    duration = total_frames / fps
    intro_duration = min(duration, max(0.0, export_config.short_intro_duration))
    outro_duration = min(duration, max(0.0, export_config.short_outro_duration))

    if export_config.short_intro_enabled and elapsed < intro_duration:
        return ShortOverlay(
            kind="intro",
            title=export_config.short_intro_text,
            opacity=_window_opacity(elapsed, 0.0, intro_duration),
        )

    outro_start = max(intro_duration, duration - outro_duration)
    if export_config.short_outro_enabled and elapsed >= outro_start:
        return ShortOverlay(
            kind="outro",
            title=export_config.short_outro_text,
            opacity=_window_opacity(elapsed, outro_start, duration),
        )

    if export_config.short_context_enabled:
        context_start = intro_duration if export_config.short_intro_enabled else 0.0
        context_end = (
            outro_start if export_config.short_outro_enabled else duration
        )
        return ShortOverlay(
            kind="context",
            title=export_config.short_context_title,
            subtitle=export_config.short_context_subtitle,
            opacity=_window_opacity(elapsed, context_start, context_end),
        )

    return None


def _window_opacity(elapsed, start, end, fade_seconds=0.25):
    if end <= start:
        return 1.0
    fade = min(fade_seconds, (end - start) / 2)
    if fade <= 0:
        return 1.0
    fade_in = (elapsed - start) / fade
    fade_out = (end - elapsed) / fade
    return max(0.12, min(1.0, fade_in, fade_out))
