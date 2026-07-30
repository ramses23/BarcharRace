import unittest

import _test_path
from matplotlib import font_manager
from PIL import ImageFont
from utils.text_fit import (
    estimate_text_width,
    fit_text_to_width,
    measure_text_width,
)


class TextFitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        font_path = font_manager.findfont(
            font_manager.FontProperties(family="DejaVu Sans"),
            fallback_to_default=True,
        )
        cls.small_font = ImageFont.truetype(font_path, 20)
        cls.large_font = ImageFont.truetype(font_path, 40)

    def test_estimates_width_from_text_length_and_font_size(self):
        self.assertEqual(estimate_text_width("abcd", 10, 0.5), 20)

    def test_keeps_short_text_that_fits(self):
        self.assertEqual(
            fit_text_to_width("Toyota", 200, font=self.small_font),
            "Toyota",
        )

    def test_keeps_long_text_when_measured_width_fits(self):
        text = "General Motors"
        available_width = measure_text_width(text, self.small_font)

        self.assertEqual(
            fit_text_to_width(
                text,
                available_width,
                font=self.small_font,
            ),
            text,
        )

    def test_truncates_text_only_when_measured_width_is_exceeded(self):
        text = "United States of America"
        result = fit_text_to_width(
            text,
            max_width=90,
            font=self.small_font,
        )

        self.assertNotEqual(result, text)
        self.assertTrue(result.endswith("..."))
        self.assertLessEqual(
            measure_text_width(result, self.small_font),
            90,
        )

    def test_measurement_changes_with_font_size(self):
        text = "Volkswagen"

        self.assertGreater(
            measure_text_width(text, self.large_font),
            measure_text_width(text, self.small_font),
        )

    def test_handles_accents_and_spaces_using_real_measurement(self):
        text = "Compañía Eléctrica Nacional"
        available_width = measure_text_width("Compañía Eléctrica...", self.small_font)
        result = fit_text_to_width(
            text,
            available_width,
            font=self.small_font,
        )

        self.assertTrue(result.startswith("Compañía"))
        self.assertTrue(result.endswith("..."))
        self.assertLessEqual(
            measure_text_width(result, self.small_font),
            available_width,
        )

    def test_returns_empty_string_when_no_text_can_fit(self):
        self.assertEqual(
            fit_text_to_width("USA", 1, font=self.small_font),
            "",
        )


if __name__ == "__main__":
    unittest.main()
