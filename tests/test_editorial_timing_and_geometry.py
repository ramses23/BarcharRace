import unittest
from dataclasses import replace

import _test_path
import pandas as pd

from config.chart_config import ChartConfig
from config.dataset_config import DatasetConfig
from core.bar_value_scale import BarValueScaleResolver, scale_bar_sprites
from core.fun_fact_scheduler import FunFactScheduler
from core.layout_engine import LayoutEngine, structural_race_vertical_bounds
from core.logo_geometry import final_visual_bar_sprite, resolved_primary_logo_size
from core.motion_engine import MotionEngine
from core.timeline import Timeline
from core.transition_timing import TransitionTimingPlan
from core.value_axis import ValueAxisTracker, align_axis_to_bar_scale
from models.bar_data import BarData
from models.fun_fact import FunFact, FunFactCollection


class EditorialTimingAndGeometryTest(unittest.TestCase):
    def scheduler(self, facts, steps=(90, 600, 90, 600), continuous=True):
        timeline = Timeline(pd.DataFrame({
            'year': [2000, 2001, 2002, 2003, 2004],
            'name': ['A'] * 5, 'value': [1] * 5,
        }), DatasetConfig())
        scheduler = FunFactScheduler(FunFactCollection(1, tuple(facts), ''), timeline,
                                     fade_in=0, fade_out=0)
        plan = TransitionTimingPlan(steps, continuous)
        scheduler.configure_timing(timeline.get_years(), plan, 60)
        return scheduler, plan

    def test_short_year_card_survives_year_boundary_for_six_seconds(self):
        scheduler, _ = self.scheduler([FunFact('a', '2000', '2000', 'A')])
        self.assertEqual(scheduler.active_at_frame(90).fact.id, 'a')
        self.assertEqual(scheduler.active_at_frame(359).fact.id, 'a')
        self.assertIsNone(scheduler.active_at_frame(360))
        self.assertGreater(scheduler.display_end_index(scheduler.facts[0]), 1)

    def test_next_card_preempts_hold_without_overlap(self):
        scheduler, _ = self.scheduler([
            FunFact('a', '2000', '2000', 'A'), FunFact('b', '2001', '2001', 'B')])
        self.assertEqual(scheduler.active_at_frame(89).fact.id, 'a')
        self.assertEqual(scheduler.active_at_frame(90).fact.id, 'b')
        self.assertEqual(scheduler.active_at_frame(359).fact.id, 'b')

    def test_configurable_minimum_and_preemption(self):
        scheduler, plan = self.scheduler([FunFact('a', '2000', '2000', 'A')])
        scheduler.configure_timing([2000, 2001, 2002, 2003, 2004], plan, 60,
                                   minimum_seconds=12)
        self.assertEqual(scheduler.active_at_frame(719).fact.id, 'a')
        self.assertIsNone(scheduler.active_at_frame(720))
        scheduler, plan = self.scheduler([
            FunFact('a', '2000', '2000', 'A'), FunFact('b', '2001', '2001', 'B')])
        scheduler.configure_timing([2000, 2001, 2002, 2003, 2004], plan, 60,
                                   minimum_seconds=12)
        self.assertEqual(scheduler.active_at_frame(89).fact.id, 'a')
        self.assertEqual(scheduler.active_at_frame(90).fact.id, 'b')

    def test_random_access_matches_full_schedule_including_noncontinuous(self):
        for continuous in (False, True):
            scheduler, plan = self.scheduler([
                FunFact('a', '2000', '2000', 'A'), FunFact('b', '2003', '2004', 'B')],
                continuous=continuous)
            full = [scheduler.active_at_frame(f) for f in range(plan.frame_count)]
            for frame in (359, 90, 0, 780, plan.frame_count - 1, 200, 359):
                self.assertEqual(full[frame], scheduler.active_at_frame(frame))
            self.assertIsNone(scheduler.active_at_frame(plan.frame_count))

    def test_long_window_is_not_shortened_and_fades_use_extended_duration(self):
        scheduler, _ = self.scheduler([FunFact('a', '2001', '2001', 'A')])
        self.assertIsNotNone(scheduler.active_at_frame(689))
        self.assertIsNone(scheduler.active_at_frame(690))
        scheduler, _ = self.scheduler([FunFact('a', '2000', '2000', 'A')])
        scheduler.fade_in, scheduler.fade_out = .12, .2
        self.assertIsNone(scheduler.active_at_frame(0))
        self.assertEqual(scheduler.active_at_frame(90).opacity, 1)
        self.assertGreater(scheduler.active_at_frame(359).opacity, 0)

    def test_logo_floor_preserves_numeric_endpoints_above_the_badge_size(self):
        config = ChartConfig(logos_enabled=True, bar_logo_position='inside_right',
                             logo_size=100, primary_logo_min_size=85,
                             value_grid_enabled=True, value_grid_mode='dynamic', start_bars_at_zero=True,
                             leader_full_width_point=.5)
        sprites = LayoutEngine(config).build([BarData('Leader', 824), BarData('Blade', 285)])
        sprites = [replace(s, logo_path='test.png') for s in sprites]
        resolver = BarValueScaleResolver.from_config(config, [sprites, sprites])
        tracker = ValueAxisTracker.from_config(config, [sprites, sprites])
        for progress in (0, .01, .2, .5, 1):
            scale = resolver.for_sprites(sprites, timeline_progress=progress)
            axis = align_axis_to_bar_scale(tracker.next(sprites), scale)
            for bar in scale_bar_sprites(sprites, scale):
                visual = final_visual_bar_sprite(config, bar, primary_logo_available=True)
                logo_width = resolved_primary_logo_size(config, visual, 100)
                self.assertEqual(visual.width, max(bar.width, logo_width))
                self.assertGreater(logo_width, 0)
                self.assertAlmostEqual(bar.x + bar.width, axis.scale.x_for_value(bar.value))
                if bar.width >= logo_width:
                    self.assertAlmostEqual(visual.x + visual.width, axis.scale.x_for_value(bar.value))

    def test_fill_rows_stay_inside_viewport_during_motion(self):
        config = ChartConfig(bar_vertical_layout_mode='fill_available', bar_height=54,
                             value_grid_enabled=True, value_grid_tick_labels_enabled=True)
        config = replace(config, animation=replace(config.animation, rank_movement_duration=.15))
        layout = LayoutEngine(config)
        start = layout.build([BarData('A', 100), BarData('B', 50)])
        end = layout.build([BarData('B', 150), BarData('A', 100), BarData('C', 20)])
        top, bottom = structural_race_vertical_bounds(config)
        for count in (1, 2, 10):
            rows = layout.build([BarData(str(i), 100 - i) for i in range(count)])
            self.assertEqual(len(rows), count)
            self.assertAlmostEqual(rows[0].y - rows[0].height / 2, top)
            self.assertAlmostEqual(rows[-1].y + rows[-1].height / 2, bottom)
        motion = MotionEngine(config.animation)
        for i in range(101):
            bars = motion.interpolate_sprites_continuous_at(start, start, end, end, i / 100)
            for bar in bars:
                visual = final_visual_bar_sprite(config, bar)
                self.assertGreaterEqual(visual.y - visual.height / 2, top - 1e-8)
                self.assertLessEqual(visual.y + visual.height / 2, bottom + 1e-8)


if __name__ == '__main__':
    unittest.main()
