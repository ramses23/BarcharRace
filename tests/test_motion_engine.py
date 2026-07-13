import unittest

import _test_path
from config.animation_config import AnimationConfig
from core.motion_engine import MotionEngine
from models.bar_sprite import BarSprite


class MotionEngineTest(unittest.TestCase):
    def test_continuous_motion_preserves_velocity_across_period_boundary(self):
        def sprite(value, y):
            return BarSprite(
                name="USA",
                value=value,
                color="#123456",
                x=0,
                y=y,
                width=value,
                height=40,
                rank=1,
            )

        year_a = [sprite(0, 0)]
        year_b = [sprite(100, 100)]
        year_c = [sprite(300, 300)]
        year_d = [sprite(600, 600)]
        engine = MotionEngine(
            animation_config=AnimationConfig(motion_mode="continuous")
        )

        first_transition = engine.interpolate_sprites_continuous(
            year_a,
            year_a,
            year_b,
            year_c,
            steps=100,
            include_start=True,
        )
        second_transition = engine.interpolate_sprites_continuous(
            year_a,
            year_b,
            year_c,
            year_d,
            steps=100,
            include_start=False,
        )

        velocity_before = (
            first_transition[-1][0].y - first_transition[-2][0].y
        )
        velocity_after = second_transition[0][0].y - year_b[0].y

        self.assertEqual(len(first_transition), 101)
        self.assertEqual(len(second_transition), 100)
        self.assertNotEqual(second_transition[0][0].y, year_b[0].y)
        self.assertAlmostEqual(velocity_before, velocity_after, delta=0.05)

    def test_continuous_motion_hits_yearly_keyframes_without_overshoot(self):
        previous = [BarSprite("A", 50, "#123456", 0, 0, 50, 40)]
        start = [BarSprite("A", 100, "#123456", 0, 100, 100, 40)]
        end = [BarSprite("A", 80, "#123456", 0, 80, 80, 40)]
        next_sprites = [BarSprite("A", 200, "#123456", 0, 200, 200, 40)]

        frames = MotionEngine(
            animation_config=AnimationConfig(motion_mode="continuous")
        ).interpolate_sprites_continuous(
            previous,
            start,
            end,
            next_sprites,
            steps=20,
        )

        self.assertEqual(frames[0][0].value, 100)
        self.assertEqual(frames[-1][0].value, 80)
        self.assertTrue(all(80 <= frame[0].value <= 100 for frame in frames))

    def test_interpolates_rank(self):
        start = [
            BarSprite(
                name="USA",
                value=100,
                color="#123456",
                x=0,
                y=0,
                width=100,
                height=40,
                rank=1,
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
                rank=3,
            )
        ]

        frames = MotionEngine().interpolate_sprites(start, end, steps=3)

        self.assertAlmostEqual(frames[0][0].rank, 1)
        self.assertAlmostEqual(frames[1][0].rank, 2)
        self.assertAlmostEqual(frames[2][0].rank, 3)

    def test_keeps_missing_rank_as_none(self):
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
                name="USA",
                value=100,
                color="#123456",
                x=0,
                y=100,
                width=100,
                height=40,
            )
        ]

        frames = MotionEngine().interpolate_sprites(start, end, steps=2)

        self.assertIsNone(frames[0][0].rank)
        self.assertIsNone(frames[1][0].rank)

    def test_sorts_frames_by_current_y_position(self):
        start = [
            BarSprite(
                name="A",
                value=100,
                color="#123456",
                x=0,
                y=100,
                width=100,
                height=40,
                rank=2,
            ),
            BarSprite(
                name="B",
                value=90,
                color="#654321",
                x=0,
                y=0,
                width=90,
                height=40,
                rank=1,
            ),
        ]
        end = [
            BarSprite(
                name="A",
                value=100,
                color="#123456",
                x=0,
                y=0,
                width=100,
                height=40,
                rank=1,
            ),
            BarSprite(
                name="B",
                value=90,
                color="#654321",
                x=0,
                y=100,
                width=90,
                height=40,
                rank=2,
            ),
        ]

        frames = MotionEngine().interpolate_sprites(start, end, steps=2)

        self.assertEqual([sprite.name for sprite in frames[0]], ["B", "A"])
        self.assertEqual([sprite.name for sprite in frames[1]], ["A", "B"])

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
