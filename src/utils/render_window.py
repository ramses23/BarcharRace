"""Frame-authoritative half-open render windows and deterministic UI timecodes."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def resolve_render_window(total_frames, export_config):
    start = export_config.render_start_frame
    end = export_config.render_end_frame
    start = 0 if start is None else start
    end = total_frames if end is None else end
    for name, value in (("start", start), ("end", end)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Render {name} frame must be a non-negative integer.")
    if not 0 <= start < end <= total_frames:
        raise ValueError(
            f"Render window must satisfy 0 <= start < end <= {total_frames}; "
            f"received [{start}, {end})."
        )
    return start, end


def timecode_to_frame(text, fps):
    """Round seconds/MM:SS/HH:MM:SS to the nearest frame, ties upwards."""
    try:
        parts = [Decimal(part) for part in text.strip().split(":")]
        if not 1 <= len(parts) <= 3 or any(not p.is_finite() or p < 0 for p in parts):
            raise ValueError
        if any(p != p.to_integral_value() for p in parts[:-1]):
            raise ValueError
        if len(parts) > 1 and any(p >= 60 for p in parts[1:]):
            raise ValueError
        seconds = sum(p * (Decimal(60) ** i) for i, p in enumerate(reversed(parts)))
        return int((seconds * fps).to_integral_value(rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError("Use a non-negative time: HH:MM:SS.mmm, MM:SS.mmm or seconds.") from None


def frame_to_timecode(frame, fps):
    # Extra decimal places preserve frame identity even at high supported FPS.
    seconds = Decimal(frame) / Decimal(fps)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remainder = seconds % 60
    return f"{hours:02}:{minutes:02}:{remainder:012.9f}"
