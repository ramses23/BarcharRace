import unittest
from dataclasses import replace

import _test_path
from config.chart_config import ChartConfig
from core.bar_value_scale import BarValueScaleResolver, scale_bar_sprites
from core.motion_engine import MotionEngine
from core.transition_timing import build_transition_timing_plan, sample_timed_sprites
from core.value_axis import align_axis_to_bar_scale
from models.bar_sprite import BarSprite
from models.value_axis import SemanticDataScale, ValueAxisState


class DisplaySettlingTest(unittest.TestCase):
    def fixture(self, mode='uniform', fps=30):
        config = ChartConfig(fps=fps, steps_per_transition=fps * 3,
            value_grid_enabled=True, value_grid_mode='dynamic',
            value_grid_tick_value_format='compact', bar_vertical_layout_mode='fill_available')
        config = replace(config, animation=replace(config.animation,
            transition_duration_mode=mode))
        endpoints = [[BarSprite(name, value, '#111111', 20, 100 + i * 60,
                               900, 54, bar_available_width=900)
                      for i, (name, value) in enumerate(zip(('Leader', 'A', 'B'), values))]
                     for values in ((1e9, 770e6, 790e6), (2.5e9, 791e6, 790e6),
                                    (2.5e9, 791e6, 790e6))]
        return config, endpoints

    def test_close_values_settle_into_separate_rows_after_crossing(self):
        for mode in ('uniform', 'activity_weighted'):
            for fps in (15, 30, 60):
                config, endpoints = self.fixture(mode, fps)
                resolver = BarValueScaleResolver.from_config(config, endpoints)
                plan = build_transition_timing_plan(config, endpoints)
                motion = MotionEngine(config.animation)
                start = plan.prefix_offsets[1] + round(fps * .6)
                for frame in range(start, plan.frame_count):
                    bars = sample_timed_sprites(motion, endpoints, plan, frame)
                    scaled = scale_bar_sprites(bars, resolver.for_sprites(bars, frame_index=frame), config)
                    a, b = ({s.name: s for s in scaled}[name] for name in ('A', 'B'))
                    self.assertLessEqual(a.y + a.height / 2, b.y - b.height / 2 + 1e-8)
                    self.assertEqual((a.value, b.value), (791e6, 790e6))

    def test_grid_fades_finish_on_plateau_and_positions_keep_compressing(self):
        config, endpoints = self.fixture()
        resolver = BarValueScaleResolver.from_config(config, endpoints)
        plan = build_transition_timing_plan(config, endpoints)
        motion = MotionEngine(config.animation)
        axis = ValueAxisState(SemanticDataScale(20, 900, 1e9), (), 1, 10, 900, 80)
        previous = {}
        faded = False
        for frame in range(plan.frame_count):
            bars = sample_timed_sprites(motion, endpoints, plan, frame)
            scale = resolver.for_sprites(bars, frame_index=frame)
            state = align_axis_to_bar_scale(axis, scale, config)
            ticks = {t.value: t for t in state.ticks}
            faded |= any(0 < t.opacity < .99 for t in ticks.values())
            for value, tick in ticks.items():
                self.assertAlmostEqual(tick.x, scale.origin_x + value / scale.domain_max * scale.width)
                if value in previous:
                    self.assertLessEqual(tick.x, previous[value].x + 1e-7)
            if frame >= plan.prefix_offsets[1] + round(config.fps * .3):
                self.assertTrue(all(abs(t.opacity - 1) < 1e-10 for t in ticks.values()))
            previous = ticks
        self.assertTrue(faded)

    def test_seek_and_skipped_frames_match_sequential_frames(self):
        config, endpoints = self.fixture('activity_weighted')
        plan = build_transition_timing_plan(config, endpoints)
        motion = MotionEngine(config.animation)
        sequential = BarValueScaleResolver.from_config(config, endpoints)
        scales = [sequential.for_sprites(sample_timed_sprites(motion, endpoints, plan, f), frame_index=f)
                  for f in range(plan.frame_count)]
        seek = BarValueScaleResolver.from_config(config, endpoints)
        for frame in (plan.frame_count - 1, 0, 80, 10, 81, 90, 40):
            bars = sample_timed_sprites(motion, endpoints, plan, frame)
            actual = seek.for_sprites(bars, frame_index=frame)
            self.assertEqual(actual, scales[frame])
            self.assertEqual(actual.display_ticks, scales[frame].display_ticks)

    def test_ties_and_static_close_values_have_no_initial_overlap(self):
        config, endpoints = self.fixture()
        for value in (790e6, 790e6 + 1):
            bars = [replace(endpoints[0][1], value=value), endpoints[0][2]]
            resolver = BarValueScaleResolver.from_config(config, [bars, bars])
            positioned = sorted(scale_bar_sprites(bars, resolver.for_sprites(bars), config), key=lambda s: s.y)
            self.assertGreaterEqual(positioned[1].y - positioned[0].y, positioned[0].height)


if __name__ == '__main__':
    unittest.main()
