from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DatasetSchema:
    year_column: str = "year"
    name_column: str = "country"
    value_column: str = "value"
    require_complete_years: bool = True


@dataclass(frozen=True)
class ValidationReport:
    rows: int
    years: tuple[int, ...]
    names: tuple[str, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self):
        return not self.errors


def inspect_csv(path, schema=None):
    schema = schema or DatasetSchema()
    dataframe = pd.read_csv(path)
    return validate_dataframe(dataframe, schema=schema)


def validate_dataframe(dataframe, schema=None):
    schema = schema or DatasetSchema()
    errors = []
    warnings = []

    required_columns = (
        schema.year_column,
        schema.name_column,
        schema.value_column,
    )
    missing_columns = [column for column in required_columns if column not in dataframe]

    if missing_columns:
        return ValidationReport(
            rows=len(dataframe),
            years=(),
            names=(),
            errors=tuple(f"Missing required column: {column}" for column in missing_columns),
            warnings=(),
        )

    if dataframe.empty:
        errors.append("Dataset is empty.")

    working = dataframe.loc[:, required_columns].copy()

    if working.isna().any().any():
        null_counts = working.isna().sum()
        for column, count in null_counts.items():
            if count:
                errors.append(f"Column '{column}' has {int(count)} null values.")

    working[schema.name_column] = working[schema.name_column].astype(str).str.strip()

    blank_names = working[schema.name_column].eq("")
    if blank_names.any():
        errors.append(f"Column '{schema.name_column}' has {int(blank_names.sum())} blank names.")

    years = pd.to_numeric(working[schema.year_column], errors="coerce")
    if years.isna().any():
        errors.append(f"Column '{schema.year_column}' has non-numeric years.")
    elif (years % 1 != 0).any():
        errors.append(f"Column '{schema.year_column}' has non-integer years.")

    values = pd.to_numeric(working[schema.value_column], errors="coerce")
    if values.isna().any():
        errors.append(f"Column '{schema.value_column}' has non-numeric values.")

    duplicates = working.duplicated([schema.year_column, schema.name_column]).sum()
    if duplicates:
        errors.append(
            f"Dataset has {int(duplicates)} duplicate year/name combinations."
        )

    parsed_years = tuple(sorted(int(year) for year in years.dropna().unique()))
    names = tuple(sorted(working[schema.name_column].dropna().unique()))

    if schema.require_complete_years and parsed_years and names:
        expected_rows = len(parsed_years) * len(names)
        actual_pairs = working.drop_duplicates(
            [schema.year_column, schema.name_column]
        ).shape[0]

        if actual_pairs != expected_rows:
            warnings.append(
                "Not every name appears in every year. "
                f"Expected {expected_rows} year/name pairs, found {actual_pairs}."
            )

    return ValidationReport(
        rows=len(dataframe),
        years=parsed_years,
        names=names,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
