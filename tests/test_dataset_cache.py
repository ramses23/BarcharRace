import tempfile
import unittest
from pathlib import Path

import _test_path
from ui.dataset_cache import _load_csv_dataset, load_csv_dataset


class DatasetCacheTest(unittest.TestCase):
    def setUp(self):
        _load_csv_dataset.clear()

    def tearDown(self):
        _load_csv_dataset.clear()

    def test_loads_csv_dataset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "dataset.csv"
            csv_path.write_text("year,name,value\n2020,A,1\n", encoding="utf-8")

            dataset = load_csv_dataset(csv_path)

        self.assertEqual(list(dataset.columns), ["year", "name", "value"])
        self.assertEqual(dataset.iloc[0].to_dict(), {"year": 2020, "name": "A", "value": 1})

    def test_invalidates_cache_when_same_path_is_replaced(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "dataset.csv"
            csv_path.write_text("year,name,value\n2020,A,1\n", encoding="utf-8")
            first = load_csv_dataset(csv_path)

            csv_path.write_text(
                "year,name,value\n2020,A,1\n2021,B,200\n",
                encoding="utf-8",
            )
            second = load_csv_dataset(csv_path)

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 2)
        self.assertEqual(second.iloc[-1]["value"], 200)


if __name__ == "__main__":
    unittest.main()
