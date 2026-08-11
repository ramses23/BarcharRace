import unittest

import _test_path
from utils.cpu_limiter import CpuLimitConfig, SoftCpuLimiter


class CpuLimiterTest(unittest.TestCase):
    def test_limit_is_inactive_at_one_hundred_percent(self):
        limiter = SoftCpuLimiter(CpuLimitConfig(enabled=True, percent=100))
        self.assertFalse(limiter.active)
        self.assertIsNone(limiter.ffmpeg_threads)

    def test_uses_hysteresis_and_cooperative_yields(self):
        values = iter((96.0, 94.0, 90.0))
        clock = iter((0.0, 0.4, 0.8))
        sleeps = []
        limiter = SoftCpuLimiter(
            CpuLimitConfig(percent=95, sample_interval=0.3, hysteresis=4, yield_seconds=0.01),
            cpu_sampler=lambda interval=None: next(values),
            clock=lambda: next(clock),
            sleeper=sleeps.append,
        )
        self.assertTrue(limiter.checkpoint())
        self.assertTrue(limiter.checkpoint())
        self.assertFalse(limiter.checkpoint())
        self.assertEqual(sleeps, [0.01, 0.01])
        self.assertEqual(limiter.stats.throttle_events, 1)
        self.assertEqual(limiter.stats.max_observed_percent, 96.0)


if __name__ == "__main__":
    unittest.main()
