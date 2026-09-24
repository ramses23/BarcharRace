import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import _test_path
import pandas as pd
from PIL import Image

from config.chart_config import ChartConfig
from config.animation_config import AnimationConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.export_config import ExportConfig
from config.fun_fact_config import FunFactConfig
from config.project_file_loader import ProjectFileError, load_project_data, load_project_file
from core.fun_fact_scheduler import FunFactScheduler
from core.motion_engine import MotionEngine
from core.rank_motion import rank_motion_effective_height
from core.timeline import Timeline
from core.transition_timing import TransitionTimingPlan
from models.bar_sprite import BarSprite
from models.fun_fact import ActiveFunFact, FunFact, FunFactCollection
from models.scene import Scene
from pipeline.render_job import RenderJob
from renderer.bar_renderer import BarRenderer
from studio.fun_fact_loader import FunFactFileError, parse_fun_fact_data


class FunFactDataPulseTest(unittest.TestCase):
    def setUp(self):
        self.chart = ChartConfig(
            width=640, height=360, dpi=72, fps=60,
            left_margin=40, right_margin=200,
            title_enabled=False, subtitle_enabled=False,
            source_label_enabled=False, time_label_enabled=False,
            category_labels_enabled=False, value_labels_enabled=False,
            rank_labels_enabled=False, logos_enabled=False,
        )
        self.fact = FunFact('fact', '2000', '2000', 'Headline', anchor_category='Alpha')
        self.bar = BarSprite('Alpha', 100, '#40A0E0', 40, 120, 180, 30, rank=1)

    def test_rank_swap_keeps_height_but_interpolates_value_width(self):
        start = [
            BarSprite('Alpha', 100, '#40A0E0', 40, 120, 100, 30, rank=2),
            BarSprite('Beta', 150, '#E08040', 40, 80, 150, 30, rank=1),
        ]
        end = [
            BarSprite('Alpha', 200, '#40A0E0', 40, 80, 200, 30, rank=1),
            BarSprite('Beta', 80, '#E08040', 40, 120, 80, 30, rank=2),
        ]
        middle = {bar.name: bar for bar in MotionEngine().interpolate_sprites_at(start, end, .5)}
        self.assertTrue(all(rank_motion_effective_height(bar) == 30 for bar in middle.values()))
        self.assertGreater(middle['Alpha'].width, 100)
        self.assertLess(middle['Alpha'].width, 200)
        self.assertLess(middle['Beta'].width, 150)
        self.assertGreater(middle['Beta'].width, 80)

    def _render(self, data_link='data_pulse', *, fact=None, bars=None, age=30):
        renderer = BarRenderer(
            output_dir=None, config=self.chart,
            fun_fact_config=FunFactConfig(enabled=True, panel_width=180, data_link=data_link),
        )
        scene = Scene(
            title='', bars=[self.bar] if bars is None else bars,
            fun_fact=ActiveFunFact(self.fact if fact is None else fact, 1.0, age_frames=age),
            frame_index=age,
        )
        renderer.render_rgba(scene)
        return renderer

    def test_legacy_off_and_unanchored_fact_have_no_link(self):
        renderer = self._render('off')
        try:
            self.assertIsNone(renderer._fun_fact_link)
            self.assertTrue(renderer._fun_fact_artist.commands)
        finally:
            renderer.close()
        renderer = self._render(fact=FunFact('plain', '2000', '2000', 'Plain'))
        try:
            self.assertFalse(renderer._fun_fact_link.get_visible())
            self.assertTrue(renderer._fun_fact_artist.commands)
        finally:
            renderer.close()

    def test_anchor_tracks_visual_bar_and_hides_outside_visible_set(self):
        renderer = self._render(age=30)
        try:
            self.assertTrue(renderer._fun_fact_link.get_visible())
            self.assertTrue(renderer._fun_fact_pulse.get_visible())
            first_path = renderer._fun_fact_link.get_path().vertices.copy()
            self.assertAlmostEqual(first_path[0, 0], self.bar.x + self.bar.width)
            self.assertAlmostEqual(first_path[0, 1], self.bar.y)
            self.assertAlmostEqual(first_path[-1, 0], 428)
            self.assertTrue(renderer._fun_fact_artist.commands)

            moved = BarSprite('Alpha', 140, '#40A0E0', 40, 200, 240, 30, rank=2)
            renderer.render_rgba(Scene(
                title='', bars=[moved], fun_fact=ActiveFunFact(self.fact, 1.0, age_frames=50),
                frame_index=50,
            ))
            moved_path = renderer._fun_fact_link.get_path().vertices
            self.assertAlmostEqual(moved_path[0, 0], 280)
            self.assertAlmostEqual(moved_path[0, 1], 200)
            self.assertFalse(renderer._fun_fact_pulse.get_visible())

            renderer.render_rgba(Scene(
                title='', bars=[], fun_fact=ActiveFunFact(self.fact, 1.0, age_frames=60),
                frame_index=60,
            ))
            self.assertFalse(renderer._fun_fact_link.get_visible())
            self.assertTrue(renderer._fun_fact_artist.commands)
        finally:
            renderer.close()

    def test_outside_logo_uses_nearer_visual_bar_end(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / 'logo.png'
            Image.new('RGBA', (32, 32), '#40A0E0').save(logo_path)
            bar = replace(self.bar, logo_path=str(logo_path))
            renderer = BarRenderer(
                output_dir=None,
                config=replace(self.chart, logos_enabled=True,
                               bar_logo_position='outside_left'),
                fun_fact_config=FunFactConfig(enabled=True, panel_width=180,
                                              data_link='data_pulse'),
            )
            try:
                renderer.render_rgba(Scene(
                    title='', bars=[bar],
                    fun_fact=ActiveFunFact(self.fact, 1.0, age_frames=30),
                ))
                self.assertAlmostEqual(
                    renderer._fun_fact_link.get_path().vertices[0, 0],
                    bar.x + bar.width,
                )
            finally:
                renderer.close()

    def test_reveal_pulse_and_random_access_are_global_age_deterministic(self):
        renderer = self._render(age=10)
        try:
            entering = renderer._fun_fact_link.get_path().vertices.copy()
            renderer.render_rgba(Scene(
                title='', bars=[self.bar], fun_fact=ActiveFunFact(self.fact, 1.0, age_frames=40),
                frame_index=400,
            ))
            settled = renderer._fun_fact_link.get_path().vertices.copy()
            self.assertLess(len(entering), len(settled))
            self.assertTrue(renderer._fun_fact_pulse.get_visible())
            pulse = renderer._fun_fact_pulse.get_offsets().copy()

            renderer.render_rgba(Scene(
                title='', bars=[self.bar], fun_fact=ActiveFunFact(self.fact, 1.0, age_frames=40),
                frame_index=400,
            ))
            self.assertTrue((renderer._fun_fact_link.get_path().vertices == settled).all())
            self.assertTrue((renderer._fun_fact_pulse.get_offsets() == pulse).all())
        finally:
            renderer.close()

    def test_config_and_anchor_json_are_backward_compatible(self):
        self.assertEqual(load_project_data({'name': 'legacy'}).fun_fact_config.data_link, 'off')
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / 'project.json'
            project.write_text(json.dumps({'name': 'pulse', 'fun_facts': {'data_link': 'data_pulse'}}), encoding='utf-8')
            self.assertEqual(load_project_file(project).fun_fact_config.data_link, 'data_pulse')
            source = {'version': 1, 'fun_facts': [{
                'id': 'fact', 'start': '2000', 'end': '2000', 'headline': 'Headline',
                'anchor_category': 'Alpha',
            }]}
            collection = parse_fun_fact_data(source, project_root=Path(temp_dir))
            self.assertEqual(collection.facts[0].anchor_category, 'Alpha')
            del source['fun_facts'][0]['anchor_category']
            self.assertIsNone(parse_fun_fact_data(source, project_root=Path(temp_dir)).facts[0].anchor_category)
        with self.assertRaises(ProjectFileError):
            load_project_data({'fun_facts': {'data_link': 'invalid'}})
        with self.assertRaises(FunFactFileError):
            parse_fun_fact_data({'version': 1, 'fun_facts': [{
                'id': 'fact', 'start': '2000', 'end': '2000', 'headline': 'Headline',
                'anchor_category': '',
            }]}, project_root=Path('.'))

    def test_scheduler_age_uses_global_frames_and_minimum_duration(self):
        timeline = Timeline(pd.DataFrame({
            'year': [2000, 2001, 2002], 'name': ['Alpha'] * 3, 'value': [1] * 3,
        }), DatasetConfig())
        scheduler = FunFactScheduler(FunFactCollection(1, (self.fact,), ''), timeline,
                                     fade_in=0, fade_out=0)
        plan = TransitionTimingPlan((90, 600), True)
        scheduler.configure_timing(timeline.get_years(), plan, 60, minimum_seconds=6)
        self.assertEqual(scheduler.active_at_frame(30).age_frames, 30)
        self.assertEqual(scheduler.active_at_frame(300).age_frames, 300)
        self.assertEqual(scheduler.active_at_frame(30), scheduler.active_at_frame(30))
        self.assertIsNone(scheduler.active_at_frame(360))

    def test_full_and_partial_render_sample_same_global_pulse_in_both_timing_modes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pd.DataFrame({
                'year': [2000, 2000, 2001, 2001],
                'name': ['Alpha', 'Beta', 'Alpha', 'Beta'],
                'country': ['US'] * 4,
                'value': [100, 80, 120, 90],
            }).to_csv(root / 'data.csv', index=False)
            (root / 'facts.json').write_text(json.dumps({
                'version': 1, 'fun_facts': [{
                    'id': 'fact', 'start': '2000', 'end': '2000',
                    'headline': 'Headline', 'anchor_category': 'Alpha',
                }],
            }), encoding='utf-8')
            for timing in ('uniform', 'activity_weighted'):
                with self.subTest(timing=timing):
                    chart = ChartConfig(
                        width=640, height=360, dpi=72, fps=30,
                        steps_per_transition=90,
                        left_margin=40, right_margin=200,
                        top_margin=60, bottom_margin=30,
                        bar_height=30, auto_fit_bar_count=False,
                        output_file=str(root / 'out.mp4'),
                        frames_dir=str(root / 'frames'),
                        animation=AnimationConfig(transition_duration_mode=timing),
                    )
                    facts = FunFactConfig(
                        enabled=True, source='facts.json', data_link='data_pulse',
                        panel_width=180, fade_in=0, fade_out=0,
                    )

                    def sample(export):
                        captured = {}
                        def consume(scene, renderer):
                            renderer.render_rgba(scene)
                            self.assertTrue(renderer._fun_fact_link.get_visible(),
                                            f'fact={scene.fun_fact!r} bars={[(b.name, b.opacity) for b in scene.bars]}')
                            captured[scene.frame_index] = (
                                renderer._fun_fact_link.get_path().vertices.copy(),
                                renderer._fun_fact_pulse.get_offsets().copy(),
                            )
                        RenderJob(
                            config=chart,
                            data_source_config=DataSourceConfig(csv_path=str(root / 'data.csv')),
                            dataset_config=DatasetConfig(name_column='name'),
                            fun_fact_config=facts,
                            export_config=export,
                            project_root=root,
                        ).run(frame_sampler=lambda _start, _end: (15, 30), frame_consumer=consume)
                        return captured

                    full = sample(ExportConfig())
                    partial = sample(ExportConfig(render_start_frame=10, render_end_frame=40))
                    self.assertEqual(set(full), {15, 30})
                    for frame in full:
                        self.assertTrue((full[frame][0] == partial[frame][0]).all())
                        self.assertTrue((full[frame][1] == partial[frame][1]).all())


if __name__ == '__main__':
    unittest.main()
