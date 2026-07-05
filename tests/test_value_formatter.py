import unittest

import _test_path
from config.value_format_config import get_value_format, list_value_formats
from utils.value_formatter import format_value


class ValueFormatterTest(unittest.TestCase):
    def test_formats_full_value_with_affixes(self):
        result = format_value(
            1234.567,
            decimal_places=2,
            prefix="$",
            suffix=" USD",
        )

        self.assertEqual(result, "$1,234.57 USD")

    def test_formats_compact_values(self):
        self.assertEqual(format_value(1530, compact=True), "1.5K")
        self.assertEqual(format_value(2_500_000, compact=True), "2.5M")
        self.assertEqual(format_value(3_200_000_000, compact=True), "3.2B")

    def test_formats_value_with_named_presets(self):
        self.assertEqual(
            format_value(1234.56, value_format=get_value_format("integer")),
            "1,235",
        )
        self.assertEqual(
            format_value(2500, value_format=get_value_format("money_usd")),
            "$2,500",
        )
        self.assertEqual(
            format_value(0.756, value_format=get_value_format("percentage")),
            "75.6%",
        )
        self.assertEqual(
            format_value(282.2, value_format=get_value_format("population_millions")),
            "282.2M",
        )

    def test_lists_value_formats(self):
        self.assertIn("compact", list_value_formats())
        self.assertIn("percentage", list_value_formats())

    def test_rejects_unknown_value_format(self):
        with self.assertRaises(ValueError):
            get_value_format("unknown")


if __name__ == "__main__":
    unittest.main()
