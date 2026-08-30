import math
import unittest

import _test_path
from config.animation_config import AnimationConfig
from core.motion_engine import MotionEngine
from models.bar_sprite import BarSprite


class MotionEngineTest(unittest.TestCase):
    @staticmethod
    def _sprite(value, *, name="A", y=0, rank=1):
        return BarSprite(
            name=name,
            value=value,
            color="#123456",
            x=0,
            y=y,
            width=max(0, value),
            height=40,
            rank=rank,
        )

    def _continuous_values(self, points, *, steps=140, value_smoothing=True):
        engine = MotionEngine(
            AnimationConfig(
                motion_mode="continuous",
                value_smoothing=value_smoothing,
            )
        )
        frames = engine.interpolate_sprites_continuous(
            [self._sprite(points[0])],
            [self._sprite(points[1])],
            [self._sprite(points[2])],
            [self._sprite(points[3])],
            steps=steps,
            include_start=True,
        )
        return [frame[0].value for frame in frames]

    def assertMonotoneSegment(self, values, start, end):
        self.assertEqual(values[0], start)
        self.assertEqual(values[-1], end)
        lower, upper = sorted((start, end))
        self.assertTrue(all(lower <= value <= upper for value in values))
        if end > start:
            self.assertTrue(all(a <= b for a, b in zip(values, values[1:])))
        elif end < start:
            self.assertTrue(all(a >= b for a, b in zip(values, values[1:])))
        else:
            self.assertTrue(all(value == start for value in values))

    def test_real_ie_values_start_moving_immediately_without_overshoot(self):
        values = self._continuous_values(
            (1_012_073_100, 999_017_500, 999_188_800, 1_009_314_166)
        )

        self.assertMonotoneSegment(values, 999_017_500, 999_188_800)
        self.assertGreater(values[1], values[0])
        self.assertEqual(sum(value == values[0] for value in values), 1)

    def test_monotone_cubic_values_increase_smoothly(self):
        values = self._continuous_values((100, 120, 150, 180))

        self.assertMonotoneSegment(values, 120, 150)
        self.assertGreater(values[1], values[0])

    def test_monotone_cubic_values_decrease_smoothly(self):
        values = self._continuous_values((180, 150, 120, 100))

        self.assertMonotoneSegment(values, 150, 120)
        self.assertLess(values[1], values[0])

    def test_monotone_cubic_values_leave_local_maximum_immediately(self):
        values = self._continuous_values((100, 200, 180, 160))

        self.assertMonotoneSegment(values, 200, 180)
        self.assertLess(values[1], values[0])

    def test_monotone_cubic_values_leave_local_minimum_immediately(self):
        values = self._continuous_values((200, 100, 120, 150))

        self.assertMonotoneSegment(values, 100, 120)
        self.assertGreater(values[1], values[0])

    def test_monotone_cubic_values_preserve_equal_endpoints_exactly(self):
        values = self._continuous_values((50, 100, 100, 150))

        self.assertMonotoneSegment(values, 100, 100)

    def test_monotone_cubic_values_handle_timeline_boundaries(self):
        first = self._continuous_values((100, 100, 120, 150))
        last = self._continuous_values((100, 120, 150, 150))

        self.assertMonotoneSegment(first, 100, 120)
        self.assertMonotoneSegment(last, 120, 150)
        self.assertGreater(first[1], first[0])
        self.assertLess(last[-2], last[-1])

    def test_monotone_cubic_values_handle_small_negative_and_large_values(self):
        cases = (
            ((1e12, 1e12 - 1, 1e12 - 0.999, 1e12 + 100), 1e12 - 1, 1e12 - 0.999),
            ((-20, -10, 0, 15), -10, 0),
            ((1e300, 1.1e300, 1.2e300, 1.3e300), 1.1e300, 1.2e300),
        )

        for points, start, end in cases:
            with self.subTest(points=points):
                values = self._continuous_values(points)
                self.assertMonotoneSegment(values, start, end)
                self.assertTrue(all(math.isfinite(value) for value in values))

    def test_continuous_entering_and_exiting_values_remain_finite(self):
        engine = MotionEngine(AnimationConfig(motion_mode="continuous"))
        entering = self._sprite(10, name="entering")
        exiting = self._sprite(20, name="exiting")

        frames = engine.interpolate_sprites_continuous(
            [exiting],
            [exiting],
            [entering],
            [entering],
            steps=10,
        )

        self.assertTrue(all(
            math.isfinite(sprite.value)
            for frame in frames
            for sprite in frame
        ))

    def test_continuous_value_smoothing_false_remains_linear(self):
        values = self._continuous_values(
            (200, 100, 120, 150),
            steps=4,
            value_smoothing=False,
        )

        self.assertEqual(values, [100, 105, 110, 115, 120])

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
                secondary_logo_path="flags/USA.png",
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
                secondary_logo_path="flags/USA.png",
            )
        ]

        frames = MotionEngine().interpolate_sprites(start, end, steps=2)

        self.assertEqual(frames[0][0].logo_path, "logos/USA.png")
        self.assertEqual(frames[1][0].logo_path, "logos/USA.png")
        self.assertEqual(frames[0][0].secondary_logo_path, "flags/USA.png")
        self.assertEqual(frames[1][0].secondary_logo_path, "flags/USA.png")


if __name__ == "__main__":
    unittest.main()
