import unittest

import _test_path
import pandas as pd
from barchart_dataset_factory.validator import DatasetSchema, validate_dataframe


class ValidatorTest(unittest.TestCase):
    def test_accepts_complete_barchartstudio_dataset(self):
        dataframe = pd.DataFrame(
            [
                {"year": 2020, "country": "A", "value": 10},
                {"year": 2020, "country": "B", "value": 8},
                {"year": 2021, "country": "A", "value": 11},
                {"year": 2021, "country": "B", "value": 9},
            ]
        )

        report = validate_dataframe(dataframe)

        self.assertTrue(report.ok)
        self.assertEqual(report.years, (2020, 2021))
        self.assertEqual(report.names, ("A", "B"))
        self.assertEqual(report.warnings, ())

    def test_reports_missing_columns(self):
        dataframe = pd.DataFrame([{"year": 2020, "name": "A"}])

        report = validate_dataframe(dataframe)

        self.assertFalse(report.ok)
        self.assertIn("Missing required column: country", report.errors)
        self.assertIn("Missing required column: value", report.errors)

    def test_warns_about_incomplete_years(self):
        dataframe = pd.DataFrame(
            [
                {"year": 2020, "country": "A", "value": 10},
                {"year": 2020, "country": "B", "value": 8},
                {"year": 2021, "country": "A", "value": 11},
            ]
        )

        report = validate_dataframe(dataframe)

        self.assertTrue(report.ok)
        self.assertEqual(len(report.warnings), 1)

    def test_supports_custom_schema(self):
        dataframe = pd.DataFrame(
            [{"date": 2020, "team": "Brazil", "points": 1800}]
        )

        report = validate_dataframe(
            dataframe,
            schema=DatasetSchema(
                year_column="date",
                name_column="team",
                value_column="points",
            ),
        )

        self.assertTrue(report.ok)
        self.assertEqual(report.names, ("Brazil",))


if __name__ == "__main__":
    unittest.main()
