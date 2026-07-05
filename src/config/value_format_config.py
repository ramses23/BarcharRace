from dataclasses import dataclass


@dataclass(frozen=True)
class ValueFormatConfig:
    decimal_places: int = 1
    compact: bool = False
    prefix: str = ""
    suffix: str = ""
    multiplier: float = 1.0


VALUE_FORMAT_PRESETS = {
    "decimal": ValueFormatConfig(decimal_places=1),
    "integer": ValueFormatConfig(decimal_places=0),
    "population_millions": ValueFormatConfig(decimal_places=1, suffix="M"),
    "money_usd": ValueFormatConfig(decimal_places=0, prefix="$"),
    "percentage": ValueFormatConfig(decimal_places=1, suffix="%", multiplier=100),
    "compact": ValueFormatConfig(decimal_places=1, compact=True),
}


def get_value_format(name):
    try:
        return VALUE_FORMAT_PRESETS[name]
    except KeyError as exc:
        available = ", ".join(sorted(VALUE_FORMAT_PRESETS))
        raise ValueError(
            f"Unknown value format '{name}'. Available formats: {available}"
        ) from exc


def list_value_formats():
    return tuple(sorted(VALUE_FORMAT_PRESETS))
