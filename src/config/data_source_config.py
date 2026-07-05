from dataclasses import dataclass


@dataclass(frozen=True)
class DataSourceConfig:
    source_type: str = "csv"

    csv_path: str = "data/datasets/sample_dynamic.csv"

    sqlite_database_path: str = "data/database/barchart.db"
    sqlite_table_name: str = "population"

    @property
    def source_label(self):
        if self.source_type == "csv":
            return f"Source: {self.csv_path}"

        if self.source_type == "sqlite":
            return f"Source: {self.sqlite_database_path} :: {self.sqlite_table_name}"

        return f"Source: {self.source_type}"
