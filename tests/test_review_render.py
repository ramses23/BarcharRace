import json
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import _test_path
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.export_config import ExportConfig
from config.project_file_loader import load_project_data, ProjectFileError
from core.review_render import review_frame_plan, review_renderer_config
from pipeline.render_job import RenderJob
from studio.short_export import resolve_export_output_path
from studio.project_builder import project_form_values


class ReviewRenderTest(unittest.TestCase):
    def test_placeholder_preserves_logo_size_and_missing_asset_behavior(self):
        from PIL import Image
        from renderer.bar_renderer import BarRenderer
        from renderer.review_renderer import DraftReviewRenderer
        with tempfile.TemporaryDirectory() as directory:
            logo = Path(directory)/'logo.png'
            Image.new('RGBA', (32, 16), 'red').save(logo)
            original = BarRenderer(output_dir=None)
            draft = DraftReviewRenderer(output_dir=None)
            try:
                self.assertEqual(original._load_logo(str(logo), 64).shape,
                                 draft._load_logo(str(logo), 64).shape)
                self.assertIsNone(draft._load_logo(str(logo.with_name('missing.png')), 64))
                self.assertFalse((original._load_logo(str(logo), 64) == draft._load_logo(str(logo), 64)).all())
            finally:
                original.close()
                draft.close()

    def test_sampling_preserves_duration_and_endpoints(self):
        for fps in (12, 17, 24, 30, 60, 144):
            for span in (1, 3, 101, 1000):
                for mode in ('quick', 'motion'):
                    ids, rate = review_frame_plan(7, 7 + span, fps, mode)
                    self.assertEqual(tuple(sorted(set(ids))), ids)
                    self.assertEqual(ids[0], 7)
                    if len(ids) > 1:
                        self.assertEqual(ids[-1], 7 + span - 1)
                    self.assertEqual(Fraction(len(ids), 1) / rate, Fraction(span, fps))
                    self.assertLessEqual(len(ids), span)

    def test_paths_and_persistence(self):
        data = {'export': {'review_mode': 'quick', 'review_detail': 'draft'}}
        preset = load_project_data(data)
        self.assertEqual(project_form_values(data)['review_detail'], 'draft')
        for mode in ('standard', 'short'):
            config = replace(preset.export_config, mode=mode, render_start_frame=2, render_end_frame=40)
            path = resolve_export_output_path('race.mp4', config)
            self.assertNotEqual(path, Path('race.mp4'))
            self.assertEqual(resolve_export_output_path(path, config), path)
            self.assertIn('_review_quick_draft', path.stem)
        for key in ('review_mode', 'review_detail'):
            with self.assertRaises(ProjectFileError):
                load_project_data({'export': {key: 'invalid'}})

    def test_review_scenes_are_exact_original_global_frames_and_do_not_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv = root / 'data.csv'
            csv.write_text('year,country,value\n2000,A,100\n2001,A,200\n2002,A,300\n')
            chart = ChartConfig(width=320, height=240, steps_per_transition=40, fps=20,
                frame_output_mode='png_sequence',
                value_grid_enabled=True, start_bars_at_zero=True,
                frames_dir=str(root/'frames'), output_file=str(root/'race.mp4'))
            source = DataSourceConfig(csv_path=str(csv))
            with patch('pipeline.render_job.BarRenderer') as factory, patch('pipeline.render_job.VideoExporter'), patch('builtins.print'):
                RenderJob(config=chart, data_source_config=source).run()
                full = [c.args[0] for c in factory.return_value.render.call_args_list]
            for mode in ('quick', 'motion'):
                settings = ExportConfig(review_mode=mode)
                ids, fps = review_frame_plan(0, len(full), chart.fps, mode)
                with patch('pipeline.render_job.BarRenderer') as factory, patch('pipeline.render_job.VideoExporter') as encoder, patch('pipeline.render_job.clean_frame_directory', side_effect=AssertionError('cleanup')), patch('builtins.print'):
                    result = RenderJob(config=chart, data_source_config=source, export_config=settings).run()
                    scenes = [c.args[0] for c in factory.return_value.render_rgba.call_args_list]
                    self.assertEqual(scenes, [full[i] for i in ids])
                    self.assertEqual(result.frames_rendered, len(ids))
                    self.assertIsNone(factory.call_args.kwargs['output_dir'])
                    self.assertEqual(encoder.call_args.kwargs['fps'], fps)
                    self.assertNotEqual(result.output_file, chart.output_file)
            simplified = review_renderer_config(chart, 'visual')
            self.assertEqual((simplified.width, simplified.height, simplified.fps), (320, 240, 20))
            self.assertEqual(simplified.logo_size, chart.logo_size)
            self.assertFalse(simplified.bar_shadow_enabled)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_real_review_mp4_preserves_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv = root/'data.csv'
            csv.write_text('year,country,value\n2000,A,100\n2001,A,200\n')
            chart = ChartConfig(width=1280, height=720, fps=60, steps_per_transition=61,
                output_file=str(root/'race.mp4'), frames_dir=str(root/'frames'))
            result = RenderJob(config=chart, data_source_config=DataSourceConfig(csv_path=str(csv)),
                               export_config=ExportConfig(review_mode='quick', review_detail='draft')).run()
            info = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json', result.output_file]))['streams'][0]
            self.assertAlmostEqual(float(info['duration']), 61/60, places=4)
            self.assertEqual(int(info['nb_frames']), result.frames_rendered)
            self.assertEqual((info['width'], info['height']), (960, 540))
            self.assertFalse((root/'race.mp4').exists())
            self.assertFalse((root/'frames').exists())
