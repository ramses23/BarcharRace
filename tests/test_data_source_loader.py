import sqlite3
import tempfile
import unittest
from pathlib import Path

import _test_path
from config.data_source_config import DataSourceConfig
from importers.data_source_loader import DataSourceLoader


class DataSourceLoaderTest(unittest.TestCase):
    def test_loads_csv_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "sample.csv"
            csv_path.write_text(
                "year,country,value\n2000,USA,100\n",
                encoding="utf-8",
            )

            dataframe = DataSourceLoader(
                DataSourceConfig(
                    source_type="csv",
                    csv_path=str(csv_path),
                )
            ).load()

            self.assertEqual(len(dataframe), 1)
            self.assertEqual(dataframe.iloc[0]["country"], "USA")

    def test_loads_sqlite_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "sample.db"

            conn = sqlite3.connect(db_path)

            try:
                conn.execute(
                    "CREATE TABLE population (year INTEGER, country TEXT, value REAL)"
                )
                conn.execute("INSERT INTO population VALUES (2000, 'USA', 100.0)")
                conn.commit()
            finally:
                conn.close()

            dataframe = DataSourceLoader(
                DataSourceConfig(
                    source_type="sqlite",
                    sqlite_database_path=str(db_path),
                    sqlite_table_name="population",
                )
            ).load()

            self.assertEqual(len(dataframe), 1)
            self.assertEqual(dataframe.iloc[0]["country"], "USA")

    def test_rejects_unknown_source_type(self):
        with self.assertRaises(ValueError):
            DataSourceLoader(DataSourceConfig(source_type="api")).load()


if __name__ == "__main__":
    unittest.main()
