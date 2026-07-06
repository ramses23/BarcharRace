import unittest

import _test_path
from config.animation_config import AnimationConfig
from core.motion_engine import MotionEngine
from models.bar_sprite import BarSprite


class MotionEngineTest(unittest.TestCase):
    def test_uses_configured_easing_for_motion(self):
        start = [
            BarSprite(
                name="USA",
                value=0,
                color="#123456",
                x=0,
                y=0,
                width=0,
                height=40,
            )
        ]
        end = [
            BarSprite(
                name="USA",
                value=100,
                color="#123456",
                x=0,
                y=100,
                width=100,
                height=40,
            )
        ]

        frames = MotionEngine(
            animation_config=AnimationConfig(easing="ease_in_cubic")
        ).interpolate_sprites(start, end, steps=3)

        self.assertAlmostEqual(frames[1][0].y, 12.5)
        self.assertAlmostEqual(frames[1][0].width, 12.5)

    def test_can_keep_value_interpolation_linear(self):
        start = [
            BarSprite(
                name="USA",
                value=0,
                color="#123456",
                x=0,
                y=0,
                width=0,
                height=40,
            )
        ]
        end = [
            BarSprite(
                name="USA",
                value=100,
                color="#123456",
                x=0,
                y=0,
                width=100,
                height=40,
            )
        ]

        frames = MotionEngine(
            animation_config=AnimationConfig(
                easing="ease_in_cubic",
                value_smoothing=False,
            )
        ).interpolate_sprites(start, end, steps=3)

        self.assertAlmostEqual(frames[1][0].value, 50)
        self.assertAlmostEqual(frames[1][0].width, 12.5)

    def test_fades_entering_and_exiting_sprites(self):
        start = [
            BarSprite(
                name="USA",
                value=100,
                color="#123456",
                x=0,
                y=0,
                width=100,
                height=40,
            )
        ]
        end = [
            BarSprite(
                name="Mexico",
                value=100,
                color="#654321",
                x=0,
                y=0,
                width=100,
                height=40,
            )
        ]

        frames = MotionEngine().interpolate_sprites(start, end, steps=3)
        middle = {sprite.name: sprite for sprite in frames[1]}
        final = {sprite.name: sprite for sprite in frames[-1]}

        self.assertAlmostEqual(middle["USA"].opacity, 0.5)
        self.assertAlmostEqual(middle["Mexico"].opacity, 0.5)
        self.assertAlmostEqual(final["USA"].opacity, 0.0)
        self.assertAlmostEqual(final["Mexico"].opacity, 1.0)

    def test_can_disable_enter_exit_fades(self):
        end = [
            BarSprite(
                name="Mexico",
                value=100,
                color="#654321",
                x=0,
                y=0,
                width=100,
                height=40,
            )
        ]

        frames = MotionEngine(
            animation_config=AnimationConfig(enter_exit=False)
        ).interpolate_sprites([], end, steps=2)

        self.assertAlmostEqual(frames[0][0].opacity, 1.0)
        self.assertAlmostEqual(frames[1][0].opacity, 1.0)

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
