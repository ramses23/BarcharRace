import unittest

import _test_path
from utils.text_fit import estimate_text_width, fit_text_to_width


class TextFitTest(unittest.TestCase):
    def test_estimates_width_from_text_length_and_font_size(self):
        self.assertEqual(estimate_text_width("abcd", 10, 0.5), 20)

    def test_keeps_text_that_fits(self):
        self.assertEqual(fit_text_to_width("Canada", 200, 20), "Canada")

    def test_truncates_text_that_does_not_fit(self):
        result = fit_text_to_width(
            "United States of America",
            max_width=90,
            font_size=20,
            average_char_width=0.5,
        )

        self.assertEqual(result, "United...")

    def test_returns_empty_string_when_no_text_can_fit(self):
        self.assertEqual(fit_text_to_width("USA", 1, 20), "")


if __name__ == "__main__":
    unittest.main()
