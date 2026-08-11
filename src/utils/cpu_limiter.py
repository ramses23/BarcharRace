import os
from dataclasses import dataclass
from time import monotonic, sleep

import psutil


DEFAULT_CPU_LIMIT_PERCENT = 95
MIN_CPU_LIMIT_PERCENT = 50
MAX_CPU_LIMIT_PERCENT = 100


@dataclass(frozen=True)
class CpuLimitConfig:
    enabled: bool = True
    percent: int = DEFAULT_CPU_LIMIT_PERCENT
    sample_interval: float = 0.35
    hysteresis: float = 4.0
    yield_seconds: float = 0.04

    @property
    def active(self):
        return bool(self.enabled and self.percent < MAX_CPU_LIMIT_PERCENT)


@dataclass(frozen=True)
class CpuLimitStats:
    throttle_events: int = 0
    max_observed_percent: float = 0.0


class SoftCpuLimiter:
    """Cooperatively yields while total system CPU is above a soft ceiling."""

    def __init__(
        self,
        config=None,
        *,
        cpu_sampler=None,
        clock=None,
        sleeper=None,
        cancel_event=None,
    ):
        self.config = config or CpuLimitConfig()
        self._cpu_sampler = cpu_sampler or psutil.cpu_percent
        self._clock = clock or monotonic
        self._sleeper = sleeper or sleep
        self._cancel_event = cancel_event
        self._last_sample_at = None
        self._throttled = False
        self._throttle_events = 0
        self._max_observed_percent = 0.0

    @property
    def active(self):
        return self.config.active

    @property
    def ffmpeg_threads(self):
        if not self.active:
            return None
        logical_cpus = psutil.cpu_count(logical=True) or os.cpu_count() or 1
        return max(1, int(logical_cpus * (self.config.percent / 100.0)))

    @property
    def stats(self):
        return CpuLimitStats(
            throttle_events=self._throttle_events,
            max_observed_percent=self._max_observed_percent,
        )

    def checkpoint(self):
        if not self.active or self._cancelled():
            return False

        now = self._clock()
        should_sample = (
            self._last_sample_at is None
            or now - self._last_sample_at >= self.config.sample_interval
        )
        if should_sample:
            observed = float(self._cpu_sampler(interval=None))
            self._last_sample_at = now
            self._max_observed_percent = max(
                self._max_observed_percent,
                observed,
            )
            if not self._throttled and observed >= self.config.percent:
                self._throttled = True
                self._throttle_events += 1
            elif self._throttled and observed <= (
                self.config.percent - self.config.hysteresis
            ):
                self._throttled = False

        if not self._throttled or self._cancelled():
            return False

        self._yield()
        return True

    def _yield(self):
        if self._cancel_event is not None:
            self._cancel_event.wait(self.config.yield_seconds)
        else:
            self._sleeper(self.config.yield_seconds)

    def _cancelled(self):
        return bool(
            self._cancel_event is not None
            and self._cancel_event.is_set()
        )


def normalized_cpu_limit_percent(value, default=DEFAULT_CPU_LIMIT_PERCENT):
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(MIN_CPU_LIMIT_PERCENT, min(MAX_CPU_LIMIT_PERCENT, parsed))
