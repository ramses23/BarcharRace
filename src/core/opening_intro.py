"""Presentation-only opening; the data timeline and its allocation stay intact."""
from dataclasses import replace


def opening_intro_frames(config):
    return max(1, round(2 * config.fps)) if (
        config.start_bars_at_zero and config.value_grid_enabled
        and config.value_grid_mode == "dynamic"
    ) else 0


def opening_intro_bars(sprites, progress):
    t = max(0.0, min(1.0, progress))
    t = t * t * (3 - 2 * t)
    # Keep the prepared row positions and logo sizes, changing only the
    # displayed quantity and numeric body length against the fixed first scale.
    return [replace(s, value=s.value * t, width=s.width * t) for s in sprites]
