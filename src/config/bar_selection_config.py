from dataclasses import dataclass


@dataclass(frozen=True)
class BarSelectionConfig:
    top_n: int | None = None
    aggregate_other: bool = False
    other_label: str = "Other"
    other_color: str | None = "#A0A0A0"
