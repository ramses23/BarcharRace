import pandas as pd

from config.dataset_config import DatasetConfig


class DatasetValidationError(ValueError):
    pass


class DatasetValidator:
    def __init__(self, config=None):
        self.config = config or DatasetConfig()

    def validate(self, dataframe):
        errors = []

        if dataframe is None:
            raise DatasetValidationError("Dataset is None.")

        if dataframe.empty:
            raise DatasetValidationError("Dataset is empty.")

        missing_columns = [
            column
            for column in self.config.required_columns
            if column not in dataframe.columns
        ]

        if missing_columns:
            raise DatasetValidationError(
                "Missing required columns: " + ", ".join(missing_columns)
            )

        normalized = dataframe.copy()

        self._validate_nulls(normalized, errors)
        self._normalize_names(normalized, errors)
        self._normalize_years(normalized, errors)
        self._normalize_values(normalized, errors)
        self._validate_duplicates(normalized, errors)

        if errors:
            raise DatasetValidationError(
                "Dataset validation failed:\n- " + "\n- ".join(errors)
            )

        return normalized

    def _validate_nulls(self, dataframe, errors):
        for column in self.config.required_columns:
            null_count = int(dataframe[column].isna().sum())

            if null_count > 0:
                errors.append(f"Column '{column}' has {null_count} empty values.")

    def _normalize_names(self, dataframe, errors):
        name_column = self.config.name_column

        dataframe[name_column] = dataframe[name_column].astype(str).str.strip()
        empty_names = dataframe[name_column].eq("")

        if empty_names.any():
            errors.append(
                f"Column '{name_column}' has {int(empty_names.sum())} blank names."
            )

    def _normalize_years(self, dataframe, errors):
        year_column = self.config.year_column
        years = pd.to_numeric(dataframe[year_column], errors="coerce")
        invalid_years = years.isna()

        if invalid_years.any():
            rows = self._sample_rows(invalid_years)
            errors.append(
                f"Column '{year_column}' has non-numeric years at rows: {rows}."
            )
            return

        non_integer_years = years.mod(1).ne(0)

        if non_integer_years.any():
            rows = self._sample_rows(non_integer_years)
            errors.append(
                f"Column '{year_column}' has non-integer years at rows: {rows}."
            )
            return

        dataframe[year_column] = years.astype(int)

    def _normalize_values(self, dataframe, errors):
        value_column = self.config.value_column
        values = pd.to_numeric(dataframe[value_column], errors="coerce")
        invalid_values = values.isna()

        if invalid_values.any():
            rows = self._sample_rows(invalid_values)
            errors.append(
                f"Column '{value_column}' has non-numeric values at rows: {rows}."
            )
            return

        if not self.config.allow_negative_values:
            negative_values = values.lt(0)

            if negative_values.any():
                rows = self._sample_rows(negative_values)
                errors.append(
                    f"Column '{value_column}' has negative values at rows: {rows}."
                )

        dataframe[value_column] = values.astype(float)

    def _validate_duplicates(self, dataframe, errors):
        if not self.config.require_unique_names_per_year:
            return

        duplicate_rows = dataframe.duplicated(
            subset=[
                self.config.year_column,
                self.config.name_column,
            ],
            keep=False,
        )

        if duplicate_rows.any():
            rows = self._sample_rows(duplicate_rows)
            errors.append(
                "Duplicate year/name combinations found at rows: " + rows + "."
            )

    def _sample_rows(self, mask, limit=5):
        row_numbers = [str(index + 2) for index in mask[mask].index[:limit]]
        return ", ".join(row_numbers)
