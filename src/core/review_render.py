"""Review output sampling; never changes production timing or scene layout."""
from dataclasses import replace
from fractions import Fraction
from math import ceil


def review_frame_plan(start, end, fps, mode):
    span = end - start
    if span <= 0 or fps <= 0 or mode not in ("quick", "motion"):
        raise ValueError("Invalid review frame range, FPS or mode.")
    count = span if mode == "motion" else min(span, max(1, ceil(span * 15 / fps)))
    frames = tuple(start + round(i * (span - 1) / (count - 1)) for i in range(count)) if count > 1 else (start,)
    # Exact playback duration, including odd ranges and non-divisible FPS.
    return frames, Fraction(count * fps, span)


def review_output_size(config):
    ratio = min(1.0, 960 / max(config.width, config.height))
    return tuple(max(2, int(v * ratio) // 2 * 2) for v in (config.width, config.height))


def review_renderer_config(config, detail):
    changes = dict(bar_shadow_enabled=False, bar_gradient_enabled=False,
                   bar_fill_type="solid", bar_texture_enabled=False,
                   bar_bevel_enabled=False, bar_outer_glow_enabled=False,
                   bar_shine_enabled=False, bar_inner_shadow_opacity=0.,
                   bar_top_highlight_opacity=0., bar_bottom_shade_opacity=0.,
                   bar_inner_glow_opacity=0., bar_edge_darkening=0.)
    if detail == "draft":
        changes["bar_shape"] = "rectangle"
    return replace(config, **changes)
