from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TypeAlias


EffectiveParameterValue: TypeAlias = str | int | bool | None | tuple[str, ...]


@dataclass(frozen=True)
class DatasetBuildResult:
    """Immutable record of one completed dataset build.

    ``csv_path`` is the absolute path of the published final CSV.
    ``source_min_date`` and ``source_max_date`` describe the complete validated
    source, not only the requested interval. ``matches_used`` counts source
    rows inside that interval, including allowed duplicates and 0-0 matches;
    ``discarded_rows`` counts rows outside it. ``period_count`` and
    ``category_count`` count values actually present in the generated output.
    """

    csv_path: Path
    builder_id: str
    builder_version: str
    mode: str
    start_year: int
    end_year: int
    period_column: str
    category_column: str
    value_column: str
    row_count: int
    period_count: int
    category_count: int
    source_sha256: str
    output_sha256: str
    source_size_bytes: int
    output_size_bytes: int
    source_min_date: date
    source_max_date: date
    matches_read: int
    matches_used: int
    discarded_rows: int
    warnings: tuple[str, ...]
    effective_parameters: tuple[tuple[str, EffectiveParameterValue], ...]
