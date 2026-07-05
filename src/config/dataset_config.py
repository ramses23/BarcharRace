from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetConfig:
    year_column: str = "year"
    name_column: str = "country"
    value_column: str = "value"

    allow_negative_values: bool = False
    require_unique_names_per_year: bool = True

    @property
    def required_columns(self):
        return (
            self.year_column,
            self.name_column,
            self.value_column,
        )
