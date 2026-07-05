from importers.csv_importer import CSVImporter
from importers.sqlite_importer import SQLiteImporter


class DataSourceLoader:
    def __init__(self, config):
        self.config = config

    def load(self):
        if self.config.source_type == "csv":
            return CSVImporter(self.config.csv_path).load()

        if self.config.source_type == "sqlite":
            return SQLiteImporter(self.config.sqlite_database_path).load(
                self.config.sqlite_table_name
            )

        raise ValueError(f"Unsupported data source type: {self.config.source_type}")
