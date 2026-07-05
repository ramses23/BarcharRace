import unittest

import _test_path
from utils.color_palette import ColorPalette


class ColorPaletteTest(unittest.TestCase):
    def test_assigns_stable_colors_by_key(self):
        palette = ColorPalette(["red", "blue"])

        self.assertEqual(palette.get("USA"), "red")
        self.assertEqual(palette.get("Mexico"), "blue")
        self.assertEqual(palette.get("USA"), "red")

    def test_cycles_when_keys_exceed_colors(self):
        palette = ColorPalette(["red", "blue"])

        self.assertEqual(palette.get("A"), "red")
        self.assertEqual(palette.get("B"), "blue")
        self.assertEqual(palette.get("C"), "red")

    def test_rejects_empty_palette(self):
        with self.assertRaises(ValueError):
            ColorPalette([])


if __name__ == "__main__":
    unittest.main()
