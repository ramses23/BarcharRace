import unittest
from dataclasses import replace

import _test_path
import numpy as np
import pandas as pd

from config.chart_config import ChartConfig
from config.dataset_config import DatasetConfig
from config.project_file_loader import load_project_data, ProjectFileError
from core.bar_value_scale import BarValueScaleResolver
from core.layout_engine import LayoutEngine
from core.timeline import Timeline
from core.value_ranking import position_bars_by_value
from models.bar_data import BarData
from models.bar_sprite import BarSprite
from models.scene import Scene
from renderer.bar_renderer import BarRenderer
from studio.project_builder import project_form_values


class RaceBehaviorControlsTest(unittest.TestCase):
    def test_grid_uses_whole_viewport_and_fades_continuously_across_step_changes(self):
        from core.value_axis import align_axis_to_bar_scale
        from models.bar_value_scale import BarValueScale
        from models.value_axis import SemanticDataScale, ValueAxisState
        config = ChartConfig(value_grid_enabled=True, value_grid_mode='dynamic',
                             value_grid_tick_value_format='compact')
        axis = ValueAxisState(SemanticDataScale(20, 900, 100), (), 10, 100, 900, 80)
        previous = {}
        for domain in np.geomspace(1e8, 2e9, 2000):
            scale = BarValueScale(20, 900, domain, tick_label_domain=2e9)
            state = align_axis_to_bar_scale(axis, scale, config)
            ticks = {t.value:t for t in state.ticks}
            self.assertTrue(any(t.x > 470 for t in ticks.values()))
            for value in ticks.keys() | previous.keys():
                old, new = previous.get(value), ticks.get(value)
                if previous:
                    self.assertLess(abs((new.opacity if new else 0) - (old.opacity if old else 0)), .08)
                if old and new:
                    self.assertLessEqual(new.x, old.x + 1e-8)
                    self.assertAlmostEqual(new.x, scale.x_for_value(value))
            previous = ticks

    def test_full_width_point_sets_initial_domain_using_effective_timing(self):
        from core.motion_engine import MotionEngine
        from core.transition_timing import sample_timed_sprites
        from core.opening_intro import opening_intro_frames
        base = ChartConfig(value_grid_enabled=True, value_grid_mode='dynamic',
                           start_bars_at_zero=True, fps=10, steps_per_transition=100)
        endpoints = [[BarSprite('A', v, '#000000', 20, 100, 600, 54,
                                bar_available_width=600)] for v in (100, 300, 900)]
        for mode in ('uniform', 'activity_weighted'):
            initial_widths = []
            for point in (.25, .75, 1.0):
                config = replace(base, leader_full_width_point=point,
                                 animation=replace(base.animation, transition_duration_mode=mode,
                                                   motion_mode='continuous'))
                resolver = BarValueScaleResolver.from_config(config, endpoints)
                plan = resolver.timing_plan
                intro = opening_intro_frames(config)
                target = round(point * (plan.frame_count + intro - 1)) - intro
                motion = MotionEngine(config.animation)
                at_target = sample_timed_sprites(motion, endpoints, plan, target)
                self.assertAlmostEqual(resolver.domain_max, at_target[0].value)
                scale = resolver.for_sprites(at_target, frame_index=target)
                self.assertAlmostEqual(scale.width_for_value(at_target[0].value), 600)
                initial_widths.append(resolver.for_sprites(endpoints[0]).width_for_value(100))
                last_x = float('inf')
                for frame in range(plan.frame_count):
                    bars = sample_timed_sprites(motion, endpoints, plan, frame)
                    scale = resolver.for_sprites(bars, frame_index=frame)
                    self.assertLessEqual(scale.x_for_value(50), last_x + 1e-8)
                    last_x = scale.x_for_value(50)
                    if frame < target:
                        self.assertLessEqual(scale.domain_max, resolver.domain_max)
                self.assertLess(resolver.for_sprites(endpoints[0]).domain_max, resolver.domain_max)
            self.assertGreater(initial_widths[0], initial_widths[1])
            self.assertGreater(initial_widths[1], initial_widths[2])

    def test_controls_load_and_restore_without_touching_other_settings(self):
        data = {'chart': {'bar_visibility_mode': 'all'},
                'fun_facts': {'minimum_duration_seconds': 12.5}}
        preset = load_project_data(data)
        self.assertEqual(preset.chart_config.bar_visibility_mode, 'all')
        self.assertEqual(preset.fun_fact_config.minimum_duration_seconds, 12.5)
        form = project_form_values(data)
        self.assertEqual(form['bar_visibility_mode'], 'all')
        self.assertEqual(form['fun_facts_minimum_duration_seconds'], 12.5)
        for value in (-1, 121, True, float('inf'), float('nan')):
            with self.assertRaises(ProjectFileError):
                load_project_data({'fun_facts': {'minimum_duration_seconds': value}})

    def test_all_mode_includes_missing_categories_but_progressive_does_not(self):
        df = pd.DataFrame({'year': [2000, 2001, 2001], 'name': ['A', 'A', 'B'], 'value': [10, 20, 5]})
        timeline = Timeline(df, DatasetConfig(name_column='name'), include_missing_categories=True)
        bars = timeline.get_frame(2000)
        self.assertEqual([(b.name, b.value) for b in bars], [('A', 10), ('B', 0)])
        config = ChartConfig(logos_enabled=False)
        self.assertEqual(len(LayoutEngine(config).build(bars)), 1)
        self.assertEqual(len(LayoutEngine(replace(config, bar_visibility_mode='all')).build(bars)), 2)
        self.assertEqual(len(Timeline(df, DatasetConfig(name_column='name')).get_frame(2000)), 1)

    def test_entrant_never_outranks_a_larger_value_and_enters_from_bottom(self):
        config = ChartConfig(bar_vertical_layout_mode='fill_available')
        blade = BarSprite('Blade', 131, '#000000', 20, 700, 100, 54, rank=2)
        xmen = BarSprite('X-Men', 13, '#FFFFFF', 20, 200, 10, 54, rank=1, opacity=.2)
        rows = {b.name: b for b in position_bars_by_value([blade, xmen], config)}
        self.assertGreater(rows['X-Men'].y, rows['Blade'].y)
        for value in (20, 60, 100, 130):
            rows = {b.name: b for b in position_bars_by_value([blade, replace(xmen, value=value, opacity=1)], config)}
            self.assertGreater(rows['X-Men'].y, rows['Blade'].y)
        rows = {b.name: b for b in position_bars_by_value([blade, replace(xmen, value=200, opacity=1)], config)}
        self.assertLess(rows['X-Men'].y, rows['Blade'].y)
        rows = {b.name: b for b in position_bars_by_value([blade, replace(xmen, value=200, opacity=.58)], config)}
        self.assertLess(rows['X-Men'].y + rows['X-Men'].height / 2,
                        rows['Blade'].y - rows['Blade'].height / 2)

    def test_dynamic_scale_never_moves_a_fixed_tick_right_and_keeps_bar_ratios(self):
        config = ChartConfig(value_grid_enabled=True, value_grid_mode='dynamic', steps_per_transition=20)
        endpoints = [[BarSprite('A', v, '#000000', 20, 100, 600, 54, bar_available_width=600)] for v in (100, 300, 150)]
        resolver = BarValueScaleResolver.from_config(config, endpoints)
        previous = float('inf')
        for f in range(resolver.frame_count):
            i, _, p = resolver.timing_plan.locate(f)
            value = endpoints[i][0].value * (1-p) + endpoints[i+1][0].value * p
            scale = resolver.for_sprites([replace(endpoints[i][0], value=value)], frame_index=f)
            x = scale.x_for_value(50)
            self.assertLessEqual(x, previous + 1e-8)
            self.assertAlmostEqual(scale.width_for_value(25) / scale.width_for_value(50), .5)
            previous = x

    def test_translucent_gradient_has_no_vertical_alpha_seams(self):
        config = ChartConfig(width=320, height=240, dpi=72, background_color_override='#000000',
                             bar_appearance_mode='simple', bar_shape='rectangle', bar_gradient_enabled=True,
                             logos_enabled=False, rank_labels_enabled=False, category_labels_enabled=False,
                             value_labels_enabled=False, title_enabled=False, source_label_enabled=False,
                             time_label_enabled=False, bar_shadow_enabled=False, bar_border_enabled=False)
        renderer = BarRenderer(config=config)
        try:
            for opacity in (.1, .3, .5, .8, 1):
                bar = BarSprite('A', 1, '#CC3300', 50.3, 80.2, 180.7, 32.4, opacity=opacity)
                pixels = np.frombuffer(renderer.render_rgba(Scene(title='', bars=[bar])), dtype=np.uint8).reshape(240, 320, 4)
                self.assertLessEqual(np.abs(np.diff(pixels[80, 60:220, 0].astype(float))).max(), 3)
        finally:
            renderer.close()


if __name__ == '__main__':
    unittest.main()
