from dataclasses import dataclass


MIN_TOP_N = 1
MAX_TOP_N = None


@dataclass(frozen=True)
class BarSelectionConfig:
    top_n: int | None = None
    aggregate_other: bool = False
    other_label: str = "Other"
    other_color: str | None = "#A0A0A0"
