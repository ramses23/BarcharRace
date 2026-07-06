import unittest

import _test_path
from config.animation_config import AnimationConfig, list_easings


class AnimationConfigTest(unittest.TestCase):
    def test_returns_named_easing_function(self):
        config = AnimationConfig(easing="ease_out_cubic")

        self.assertAlmostEqual(config.easing_function()(0.5), 0.875)

    def test_lists_easings(self):
        self.assertIn("smoothstep", list_easings())
        self.assertIn("ease_out_cubic", list_easings())

    def test_rejects_unknown_easing_when_resolved(self):
        config = AnimationConfig(easing="unknown")

        with self.assertRaises(ValueError):
            config.easing_function()


if __name__ == "__main__":
    unittest.main()
