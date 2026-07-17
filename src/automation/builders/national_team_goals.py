from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from automation.builder_parameters import (
    NATIONAL_TEAM_GOALS_DUPLICATE_POLICIES,
    NATIONAL_TEAM_GOALS_MODES,
)
from automation.models import DatasetBuildResult


class NationalTeamGoalsDatasetBuilder:
    """Build annual or cumulative national-team goals from a local CSV."""

    builder_id = "national_team_goals"
    builder_version = "1.0.0"

    _REQUIRED_COLUMNS = (
        "date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
    )
    _MATCH_IDENTITY_COLUMNS = (
        "date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "tournament",
        "city",
        "country",
        "neutral",
    )
    _MODES = NATIONAL_TEAM_GOALS_MODES
    _DUPLICATE_POLICIES = NATIONAL_TEAM_GOALS_DUPLICATE_POLICIES

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
    ) -> DatasetBuildResult:
        source_path = Path(source_csv).resolve(strict=True)
        output_path = Path(output_csv).resolve(strict=False)

        if output_path.exists():
            raise FileExistsError(f"Output CSV already exists: {output_path}")

        normalized_start = self._normalize_year(start_year, "start_year")
        normalized_end = self._normalize_year(end_year, "end_year")
        if normalized_start > normalized_end:
            raise ValueError("start_year must be less than or equal to end_year.")

        normalized_mode = self._normalize_choice(mode, "mode", self._MODES)
        normalized_policy = self._normalize_choice(
            duplicate_policy,
            "duplicate_policy",
            self._DUPLICATE_POLICIES,
        )

        source_sha256 = self._sha256(source_path)
        normalized_expected_hash = self._normalize_expected_hash(
            expected_source_sha256
        )
        if (
            normalized_expected_hash is not None
            and source_sha256 != normalized_expected_hash
        ):
            raise ValueError(
                "Source SHA-256 mismatch: "
                f"expected {normalized_expected_hash}, got {source_sha256}."
            )

        source_size_bytes = source_path.stat().st_size
        try:
            source = pd.read_csv(source_path, encoding="utf-8")
        except pd.errors.EmptyDataError as exc:
            raise ValueError("Source CSV has no columns.") from exc
        self._validate_required_columns(source)
        if source.empty:
            raise ValueError("Source CSV contains headers but no match rows.")

        matches = source.copy()
        matches["date"] = self._parse_dates(matches["date"])
        matches["home_score"] = self._parse_scores(
            matches["home_score"], "home_score"
        )
        matches["away_score"] = self._parse_scores(
            matches["away_score"], "away_score"
        )
        self._validate_team_names(matches)

        source_min_date = matches["date"].min().date()
        source_max_date = matches["date"].max().date()
        matches_read = len(matches)
        warnings = []

        identity_columns = tuple(
            column
            for column in self._MATCH_IDENTITY_COLUMNS
            if column in matches.columns
        )
        repeated_rows = int(
            matches.duplicated(subset=list(identity_columns), keep="first").sum()
        )
        if repeated_rows:
            duplicate_message = (
                f"Detected {repeated_rows} repeated match row(s) using identity "
                f"columns: {', '.join(identity_columns)}."
            )
            if normalized_policy == "error":
                raise ValueError(duplicate_message)
            if normalized_policy == "warn":
                warnings.append(duplicate_message + " All rows were retained.")

        if source_max_date.year > normalized_end:
            warnings.append(
                "The source contains matches after end_year; those rows were "
                "excluded by the requested period."
            )

        matches["year"] = matches["date"].dt.year.astype("int64")
        selected = matches.loc[
            matches["year"].between(normalized_start, normalized_end)
        ].copy()
        if selected.empty:
            raise ValueError(
                f"No matches exist between {normalized_start} and "
                f"{normalized_end}, inclusive."
            )

        annual = self._build_annual(selected)
        dataset = (
            annual
            if normalized_mode == "annual"
            else self._build_cumulative(
                annual,
                start_year=normalized_start,
                end_year=normalized_end,
            )
        )
        dataset = self._sort_dataset(dataset)
        publication_warning = self._write_csv_atomically(dataset, output_path)
        if publication_warning:
            warnings.append(publication_warning)

        output_sha256 = self._sha256(output_path)
        effective_parameters = (
            ("source_csv", str(source_path)),
            ("output_csv", str(output_path)),
            ("start_year", normalized_start),
            ("end_year", normalized_end),
            ("mode", normalized_mode),
            ("expected_source_sha256", normalized_expected_hash),
            ("duplicate_policy", normalized_policy),
            ("duplicate_identity_columns", identity_columns),
        )

        return DatasetBuildResult(
            csv_path=output_path,
            builder_id=self.builder_id,
            builder_version=self.builder_version,
            mode=normalized_mode,
            start_year=normalized_start,
            end_year=normalized_end,
            period_column="year",
            category_column="country",
            value_column="value",
            row_count=len(dataset),
            period_count=int(dataset["year"].nunique()),
            category_count=int(dataset["country"].nunique()),
            source_sha256=source_sha256,
            output_sha256=output_sha256,
            source_size_bytes=source_size_bytes,
            output_size_bytes=output_path.stat().st_size,
            source_min_date=source_min_date,
            source_max_date=source_max_date,
            matches_read=matches_read,
            matches_used=len(selected),
            discarded_rows=matches_read - len(selected),
            warnings=tuple(warnings),
            effective_parameters=effective_parameters,
        )

    @staticmethod
    def _normalize_year(value: int, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{label} must be an integer.")
        return value

    @staticmethod
    def _normalize_choice(value: str, label: str, choices: frozenset[str]) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{label} must be one of: {', '.join(sorted(choices))}.")
        normalized = value.strip().casefold()
        if normalized not in choices:
            raise ValueError(f"{label} must be one of: {', '.join(sorted(choices))}.")
        return normalized

    @staticmethod
    def _normalize_expected_hash(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().casefold()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("expected_source_sha256 must be a 64-character hex digest.")
        return normalized

    def _validate_required_columns(self, dataframe: pd.DataFrame) -> None:
        missing = [
            column for column in self._REQUIRED_COLUMNS if column not in dataframe
        ]
        if missing:
            raise ValueError("Missing required columns: " + ", ".join(missing) + ".")

    @staticmethod
    def _parse_dates(values: pd.Series) -> pd.Series:
        parsed = pd.to_datetime(values, errors="coerce", format="mixed")
        invalid = parsed.isna()
        if invalid.any():
            rows = NationalTeamGoalsDatasetBuilder._csv_rows(invalid)
            raise ValueError(f"Invalid date value(s) at CSV row(s): {rows}.")
        return parsed

    @staticmethod
    def _parse_scores(values: pd.Series, column: str) -> pd.Series:
        boolean_values = values.map(
            lambda value: isinstance(value, (bool, np.bool_))
            or (
                isinstance(value, str)
                and value.strip().casefold() in ("true", "false")
            )
        )
        if boolean_values.any():
            rows = NationalTeamGoalsDatasetBuilder._csv_rows(boolean_values)
            raise ValueError(
                f"Column '{column}' contains boolean score(s) at CSV row(s): "
                f"{rows}. Scores must be non-negative integers; boolean values "
                "are not valid."
            )

        parsed = pd.to_numeric(values, errors="coerce")
        invalid = parsed.isna() | parsed.mod(1).ne(0)
        if invalid.any():
            rows = NationalTeamGoalsDatasetBuilder._csv_rows(invalid)
            raise ValueError(
                f"Column '{column}' contains non-integer score(s) at CSV "
                f"row(s): {rows}."
            )
        negative = parsed.lt(0)
        if negative.any():
            rows = NationalTeamGoalsDatasetBuilder._csv_rows(negative)
            raise ValueError(
                f"Column '{column}' contains negative score(s) at CSV "
                f"row(s): {rows}."
            )
        return parsed.astype("int64")

    @staticmethod
    def _validate_team_names(matches: pd.DataFrame) -> None:
        for column in ("home_team", "away_team"):
            invalid = matches[column].isna() | matches[column].astype(str).str.strip().eq("")
            if invalid.any():
                rows = NationalTeamGoalsDatasetBuilder._csv_rows(invalid)
                raise ValueError(
                    f"Column '{column}' contains blank team name(s) at CSV "
                    f"row(s): {rows}."
                )

    @staticmethod
    def _csv_rows(mask: pd.Series) -> str:
        return ", ".join(str(index + 2) for index in mask[mask].index[:5])

    @staticmethod
    def _build_annual(matches: pd.DataFrame) -> pd.DataFrame:
        home = matches.loc[:, ["year", "home_team", "home_score"]].rename(
            columns={"home_team": "country", "home_score": "value"}
        )
        away = matches.loc[:, ["year", "away_team", "away_score"]].rename(
            columns={"away_team": "country", "away_score": "value"}
        )
        annual = pd.concat((home, away), ignore_index=True)
        annual = (
            annual.groupby(["year", "country"], as_index=False, sort=False)["value"]
            .sum()
            .astype({"year": "int64", "value": "int64"})
        )
        return annual

    @staticmethod
    def _build_cumulative(
        annual: pd.DataFrame,
        *,
        start_year: int,
        end_year: int,
    ) -> pd.DataFrame:
        years = pd.Index(range(start_year, end_year + 1), name="year")
        countries = pd.Index(sorted(annual["country"].unique()), name="country")
        complete_index = pd.MultiIndex.from_product((years, countries))
        complete = (
            annual.set_index(["year", "country"])
            .reindex(complete_index, fill_value=0)
            .reset_index()
        )
        complete["value"] = complete.groupby("country", sort=False)["value"].cumsum()
        complete = complete.loc[complete["value"].gt(0)].copy()
        return complete.astype({"year": "int64", "value": "int64"})

    @staticmethod
    def _sort_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
        return dataset.sort_values(
            ["year", "value", "country"],
            ascending=[True, False, True],
            kind="stable",
            ignore_index=True,
        ).loc[:, ["year", "country", "value"]]

    @staticmethod
    def _write_csv_atomically(
        dataset: pd.DataFrame,
        output_path: Path,
    ) -> str | None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                dir=output_path.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                dataset.to_csv(temporary_file, index=False, lineterminator="\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

        except BaseException:
            if temporary_path is not None:
                NationalTeamGoalsDatasetBuilder._remove_temporary_file_best_effort(
                    temporary_path
                )
            raise

        return NationalTeamGoalsDatasetBuilder._publish_without_overwrite(
            temporary_path,
            output_path,
        )

    @staticmethod
    def _publish_without_overwrite(
        temporary_path: Path,
        output_path: Path,
    ) -> str | None:
        try:
            os.link(temporary_path, output_path)
        except FileExistsError as exc:
            cleanup_error = (
                NationalTeamGoalsDatasetBuilder._remove_temporary_file_best_effort(
                    temporary_path
                )
            )
            message = f"Output CSV already exists due to a publication collision: {output_path}"
            if cleanup_error is not None:
                message += (
                    f" Temporary cleanup also failed for {temporary_path}: "
                    f"{cleanup_error}"
                )
            raise FileExistsError(message) from exc
        except OSError as exc:
            cleanup_error = (
                NationalTeamGoalsDatasetBuilder._remove_temporary_file_best_effort(
                    temporary_path
                )
            )
            message = (
                "Safe no-overwrite CSV publication failed while creating a "
                f"hardlink from {temporary_path} to {output_path}. The "
                "filesystem may not support hardlinks."
            )
            if cleanup_error is not None:
                message += (
                    f" Temporary cleanup also failed for {temporary_path}: "
                    f"{cleanup_error}"
                )
            raise OSError(message) from exc

        cleanup_error = (
            NationalTeamGoalsDatasetBuilder._remove_temporary_file_best_effort(
                temporary_path
            )
        )
        if cleanup_error is None:
            return None

        return (
            "The CSV was published successfully, but temporary file cleanup "
            f"failed; residual file: {temporary_path}. Error: {cleanup_error}"
        )

    @staticmethod
    def _remove_temporary_file_best_effort(path: Path) -> OSError | None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            return exc
        return None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
