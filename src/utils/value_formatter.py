def format_value(
    value,
    value_format=None,
    decimal_places=1,
    compact=False,
    prefix="",
    suffix="",
    multiplier=1.0,
):
    if value_format is not None:
        decimal_places = value_format.decimal_places
        compact = value_format.compact
        prefix = value_format.prefix
        suffix = value_format.suffix
        multiplier = value_format.multiplier

    value = value * multiplier

    number = _format_compact(value, decimal_places) if compact else _format_full(
        value,
        decimal_places,
    )

    return f"{prefix}{number}{suffix}"


def _format_full(value, decimal_places):
    return f"{value:,.{decimal_places}f}"


def _format_compact(value, decimal_places):
    abs_value = abs(value)

    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.{decimal_places}f}B"

    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:,.{decimal_places}f}M"

    if abs_value >= 1_000:
        return f"{value / 1_000:,.{decimal_places}f}K"

    return f"{value:,.{decimal_places}f}"
