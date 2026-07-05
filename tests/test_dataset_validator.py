import unittest

import pandas as pd

import _test_path
from validators.dataset_validator import DatasetValidationError, DatasetValidator


class DatasetValidatorTest(unittest.TestCase):
    def test_valid_dataset_is_normalized(self):
        dataframe = pd.DataFrame(
            {
                "year": ["2000", "2001"],
                "country": [" USA ", "Mexico"],
                "value": ["100.5", "95"],
            }
        )

        result = DatasetValidator().validate(dataframe)

        self.assertEqual(result["year"].tolist(), [2000, 2001])
        self.assertEqual(result["country"].tolist(), ["USA", "Mexico"])
        self.assertEqual(result["value"].tolist(), [100.5, 95.0])

    def test_invalid_dataset_reports_negative_and_duplicate_rows(self):
        dataframe = pd.DataFrame(
            {
                "year": [2000, 2000],
                "country": ["USA", "USA"],
                "value": [100, -1],
            }
        )

        with self.assertRaises(DatasetValidationError) as context:
            DatasetValidator().validate(dataframe)

        message = str(context.exception)
        self.assertIn("negative values", message)
        self.assertIn("Duplicate year/name combinations", message)

    def test_missing_required_column_fails_fast(self):
        dataframe = pd.DataFrame(
            {
                "year": [2000],
                "country": ["USA"],
            }
        )

        with self.assertRaises(DatasetValidationError) as context:
            DatasetValidator().validate(dataframe)

        self.assertIn("Missing required columns: value", str(context.exception))


if __name__ == "__main__":
    unittest.main()
