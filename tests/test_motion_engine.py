import unittest

import _test_path
from core.motion_engine import MotionEngine
from models.bar_sprite import BarSprite


class MotionEngineTest(unittest.TestCase):
    def test_preserves_logo_path_during_interpolation(self):
        start = [
            BarSprite(
                name="USA",
                value=100,
                color="#123456",
                x=0,
                y=0,
                width=100,
                height=40,
                logo_path="logos/USA.png",
            )
        ]
        end = [
            BarSprite(
                name="USA",
                value=200,
                color="#123456",
                x=0,
                y=50,
                width=200,
                height=40,
                logo_path="logos/USA.png",
            )
        ]

        frames = MotionEngine().interpolate_sprites(start, end, steps=2)

        self.assertEqual(frames[0][0].logo_path, "logos/USA.png")
        self.assertEqual(frames[1][0].logo_path, "logos/USA.png")


if __name__ == "__main__":
    unittest.main()
