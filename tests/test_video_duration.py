import unittest

import _test_path
from utils.video_duration import estimate_video_duration, format_video_duration


class VideoDurationTest(unittest.TestCase):
    def test_estimates_transition_easing_frames_and_duration(self):
        estimate = estimate_video_duration(
            period_count=20,
            steps_per_transition=24,
            fps=30,
        )

        self.assertEqual(estimate.transition_count, 19)
        self.assertEqual(estimate.frame_count, 456)
        self.assertAlmostEqual(estimate.duration_seconds, 15.2)

    def test_continuous_motion_adds_the_single_boundary_frame(self):
        estimate = estimate_video_duration(
            period_count=20,
            steps_per_transition=24,
            fps=30,
            continuous_motion=True,
        )

        self.assertEqual(estimate.frame_count, 457)
        self.assertAlmostEqual(estimate.duration_seconds, 457 / 30)

    def test_single_period_has_no_video_frames(self):
        estimate = estimate_video_duration(
            period_count=1,
            steps_per_transition=24,
            fps=30,
        )

        self.assertEqual(estimate.transition_count, 0)
        self.assertEqual(estimate.frame_count, 0)
        self.assertEqual(estimate.duration_seconds, 0)

    def test_formats_subminute_and_hour_durations(self):
        self.assertEqual(format_video_duration(15.2), "00:15.2")
        self.assertEqual(format_video_duration(3723.4), "1:02:03.4")


if __name__ == "__main__":
    unittest.main()
