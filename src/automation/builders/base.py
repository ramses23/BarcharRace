from pathlib import Path
from typing import Protocol

from automation.models import DatasetBuildResult


class DatasetBuilder(Protocol):
    """Common contract for deterministic local dataset builders."""

    builder_id: str
    builder_version: str

    def build(
        self,
        *,
        source_csv: str | Path,
        output_csv: str | Path,
        start_year: int,
        end_year: int,
        mode: str,
        expected_source_sha256: str | None = None,
        duplicate_policy: str = "error",
    ) -> DatasetBuildResult: ...
