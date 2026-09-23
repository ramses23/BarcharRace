"""Bounded, causal display transitions, identical for sequential and seek renders.

Filter discrete rank/density targets in video time, never in value distance.
The finite smoothstep kernel reaches its target exactly, including on plateaus.
Only a short rolling cache is retained; seeking needs no replay from frame zero.
"""

from collections import OrderedDict
from functools import lru_cache
from itertools import accumulate
from math import sqrt

from core.motion_engine import MotionEngine
from core.transition_timing import build_transition_timing_plan, sample_timed_sprites


class DisplayTimeline:
    def __init__(self, config, sprite_sets, reference, project_max, width):
        self.config = config
        self.sprite_sets = sprite_sets
        self.plan = build_transition_timing_plan(config, sprite_sets)
        self.motion = MotionEngine(config.animation)
        self.reference, self.project_max, self.width = reference, project_max, width
        self.records = tuple(accumulate((max((s.value for s in bars if s.opacity > 0),
                                            default=0) for bars in sprite_sets), max))
        self.rank_frames = max(1, round(config.fps * .6 * config.animation.rank_movement_duration))
        if self.plan.steps_per_transition:
            # Very short clips must not spend their whole transition catching up.
            self.rank_frames = min(self.rank_frames,
                                   max(1, min(self.plan.steps_per_transition) // 3))
        self.fade_frames = max(1, round(config.fps * .3))
        self.cache = OrderedDict()

    def _targets(self, frame):
        frame = max(0, min(self.plan.frame_count - 1, frame))
        if frame in self.cache:
            self.cache.move_to_end(frame)
            return self.cache[frame]
        bars = (sample_timed_sprites(self.motion, self.sprite_sets, self.plan, frame)
                if self.plan.steps_per_transition else (self.sprite_sets[0] if self.sprite_sets else ()))
        ordered = sorted(bars, key=lambda s: (
            self.config.selection.aggregate_other and s.name == self.config.selection.other_label,
            -s.value, s.name.casefold(), s.name))
        ranks, count = {}, 0.0
        for bar in ordered:
            ranks[bar.name] = count
            count += min(1., max(0., bar.opacity) / .1)
        ticks = {}
        if self.config.value_grid_enabled and self.config.value_grid_mode == 'dynamic':
            from core.value_axis import _continuous_dynamic_axis
            from models.value_axis import SemanticDataScale, ValueAxisState
            index = self.plan.locate(frame)[0] if self.plan.steps_per_transition else 0
            record = max(1., self.records[index] if self.records else 0.,
                         max((s.value for s in bars if s.opacity > 0), default=0.))
            domain = max(record, sqrt(self.reference) * sqrt(record))
            scale = SemanticDataScale(self.config.left_margin, self.width, domain)
            axis = ValueAxisState(scale, (), 1, 0, 1, 0)
            ticks = {t.value: t.label for t in _continuous_dynamic_axis(
                axis, scale, self.config, self.project_max, targets=True).ticks}
        result = ranks, count, ticks
        self.cache[frame] = result
        while len(self.cache) > 2 * max(self.rank_frames, self.fade_frames) + 4:
            self.cache.popitem(last=False)
        return result

    @staticmethod
    @lru_cache(maxsize=128)
    def _kernel(length):
        def smooth(t):
            return t * t * (3 - 2 * t)
        return tuple(smooth((i + 1) / length) - smooth(i / length) for i in range(length))

    def at(self, frame):
        current, _, _ = self._targets(frame)
        ranks = dict.fromkeys(current, 0.)
        for age, weight in enumerate(self._kernel(self.rank_frames)):
            previous, count, _ = self._targets(frame - age)
            for name in ranks:
                ranks[name] += weight * previous.get(name, count)
        ticks = {}
        if self.config.value_grid_enabled and self.config.value_grid_mode == 'dynamic':
            for age, weight in enumerate(self._kernel(self.fade_frames)):
                _, _, targets = self._targets(frame - age)
                for value, label in targets.items():
                    old = ticks.get(value, (label, 0.))
                    ticks[value] = label, old[1] + weight
        return (tuple(sorted(ranks.items())),
                tuple((value, label, opacity) for value, (label, opacity) in sorted(ticks.items()))
                if self.config.value_grid_enabled and self.config.value_grid_mode == 'dynamic' else None)
