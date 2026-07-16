from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date
import math
from pathlib import Path
from typing import TypeAlias


EffectiveParameterValue: TypeAlias = str | int | bool | None | tuple[str, ...]
JsonScalar: TypeAlias = str | int | float | bool | None


@dataclass(frozen=True)
class FrozenParameters(Mapping[str, JsonScalar]):
    """Deterministically ordered, deeply immutable scalar parameters."""

    _items: tuple[tuple[str, JsonScalar], ...]

    def __post_init__(self) -> None:
        normalized = tuple(self._items)
        keys = [key for key, _value in normalized]
        if any(not isinstance(key, str) for key in keys):
            raise TypeError("Parameter keys must be strings.")
        if len(keys) != len(set(keys)):
            raise ValueError("Parameter keys must be unique.")
        if keys != sorted(keys):
            raise ValueError("Parameter keys must be sorted.")
        for _key, value in normalized:
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise TypeError("Parameter values must be JSON scalars.")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Float parameter values must be finite.")
        object.__setattr__(self, "_items", normalized)

    @classmethod
    def from_mapping(cls, values: Mapping[str, JsonScalar]) -> "FrozenParameters":
        return cls(tuple(sorted(values.items(), key=lambda item: item[0])))

    def __getitem__(self, key: str) -> JsonScalar:
        for item_key, value in self._items:
            if item_key == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _value in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def to_dict(self) -> dict[str, JsonScalar]:
        return dict(self._items)


@dataclass(frozen=True)
class DatasetBrief:
    builder_id: str
    source_csv: Path
    expected_source_sha256: str | None
    parameters: FrozenParameters


@dataclass(frozen=True)
class ProductionBrief:
    schema_version: int
    job_id: str
    dataset: DatasetBrief


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
