import unittest

import _test_path
from config.data_source_config import DataSourceConfig


class DataSourceConfigTest(unittest.TestCase):
    def test_uses_source_label_override(self):
        config = DataSourceConfig(
            source_type="csv",
            csv_path="data/datasets/sample.csv",
            source_label_override="Source: Custom label",
        )

        self.assertEqual(config.source_label, "Source: Custom label")

    def test_builds_csv_source_label_from_path(self):
        config = DataSourceConfig(
            source_type="csv",
            csv_path="data/datasets/sample.csv",
        )

        self.assertEqual(config.source_label, "Source: data/datasets/sample.csv")

    def test_builds_sqlite_source_label_from_database_and_table(self):
        config = DataSourceConfig(
            source_type="sqlite",
            sqlite_database_path="data/database/sample.db",
            sqlite_table_name="population",
        )

        self.assertEqual(
            config.source_label,
            "Source: data/database/sample.db :: population",
        )


if __name__ == "__main__":
    unittest.main()
