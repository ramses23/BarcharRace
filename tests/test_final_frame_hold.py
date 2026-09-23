import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.export_config import ExportConfig
from config.project_file_loader import ProjectFileError, load_project_data
from core.review_render import review_frame_plan
from pipeline.render_job import RenderJob
from studio.short_export import estimate_export_duration
from utils.video_duration import final_frame_hold_frames


class FinalFrameHoldTest(unittest.TestCase):
    def test_duration_and_validation(self):
        self.assertEqual(final_frame_hold_frames(10, 60), 599)
        self.assertEqual(final_frame_hold_frames(0, 60), 0)
        self.assertEqual(final_frame_hold_frames(.01, 10), 0)
        self.assertEqual(estimate_export_duration((0, 1), ChartConfig(fps=10, steps_per_transition=4),
                         ExportConfig(final_frame_hold_seconds=2)).frame_count, 23)
        self.assertEqual(load_project_data({'export': {'final_frame_hold_seconds': 10}})
                         .export_config.final_frame_hold_seconds, 10)
        for value in (-1, 61, True, '10', float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ProjectFileError):
                load_project_data({'export': {'final_frame_hold_seconds': value}})

    def test_full_clip_and_review_freeze_the_exact_scene(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv = root / 'data.csv'
            csv.write_text('year,country,value\n0,A,1\n1,A,2\n2,A,3\n')
            chart = ChartConfig(width=320, height=240, fps=10,
                steps_per_transition=4, top_margin=55, bottom_margin=20,
                left_margin=20, right_margin=20, frame_output_mode='png_sequence',
                output_file=str(root/'race.mp4'), frames_dir=str(root/'frames'))
            source = DataSourceConfig(csv_path=str(csv))
            def run(export):
                with patch('pipeline.render_job.BarRenderer') as factory, \
                     patch('pipeline.render_job.VideoExporter'), patch('builtins.print'):
                    result = RenderJob(config=chart, data_source_config=source,
                                       export_config=export).run()
                    scenes = [call.args[0] for call in factory.return_value.render.call_args_list]
                    return result, scenes

            settings = ExportConfig(final_frame_hold_seconds=2)
            result, full = run(settings)
            self.assertEqual(result.frames_rendered, 27)
            self.assertEqual(len(full), 27)
            self.assertEqual(full[7].bars[0].value, 3)
            self.assertTrue(all(scene is full[7] for scene in full[8:]))
            self.assertEqual(full[-1].frame_index, full[7].frame_index)
            for start, end in ((5, 12), (8, 15), (20, 27)):
                result, clip = run(ExportConfig(final_frame_hold_seconds=2,
                    render_start_frame=start, render_end_frame=end))
                self.assertEqual(result.frames_rendered, end - start)
                self.assertEqual(clip, full[start:end])
                self.assertTrue(all(scene is clip[-1] for scene in clip if start >= 8))

            observed = []
            with patch('pipeline.render_job.BarRenderer'), \
                 patch('pipeline.render_job.VideoExporter'), patch('builtins.print'):
                RenderJob(config=chart, data_source_config=source,
                    export_config=settings).run(frame_sampler=lambda start, end: (0, 7, 10, 26),
                    frame_consumer=lambda scene, renderer: observed.append(scene))
            self.assertEqual(observed, [full[i] for i in (0, 7, 10, 26)])

            with patch('pipeline.render_job.BarRenderer') as factory, \
                 patch('pipeline.render_job.VideoExporter') as exporter, patch('builtins.print'):
                reviewed = RenderJob(config=chart, data_source_config=source,
                    export_config=ExportConfig(final_frame_hold_seconds=2,
                                               review_mode='quick')).run()
                ids, _ = review_frame_plan(0, 27, chart.fps, 'quick')
                self.assertEqual(reviewed.frames_rendered, len(ids))
                self.assertEqual(exporter.return_value.open_stream.return_value.stdin.write.call_count,
                                 len(ids))
                # Held frames reuse the already rasterized source frame.
                self.assertLess(factory.return_value.render_rgba.call_count, len(ids))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_real_mp4_duration_and_last_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv = root/'data.csv'
            csv.write_text('year,country,value\n0,A,1\n1,A,2\n')
            chart = ChartConfig(width=320, height=240, fps=10, steps_per_transition=4,
                                top_margin=55, bottom_margin=20, left_margin=20, right_margin=20,
                                output_file=str(root/'race.mp4'), frames_dir=str(root/'frames'))
            result = RenderJob(config=chart, data_source_config=DataSourceConfig(csv_path=str(csv)),
                export_config=ExportConfig(final_frame_hold_seconds=2)).run()
            info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
                '-of', 'json', result.output_file]))['streams'][0]
            self.assertEqual(int(info['nb_frames']), 23)
            self.assertAlmostEqual(float(info['duration']), 2.3, places=4)

    def test_quick_review_can_skip_original_final_frame_and_still_hold_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv = root/'data.csv'
            csv.write_text('year,country,value\n0,A,1\n1,A,2\n')
            chart = ChartConfig(width=320, height=240, fps=30, steps_per_transition=4,
                                top_margin=55, bottom_margin=20,
                                output_file=str(root/'race.mp4'))
            export = ExportConfig(review_mode='quick', final_frame_hold_seconds=1)
            ids, _ = review_frame_plan(0, 33, 30, 'quick')
            self.assertNotIn(3, ids)
            with patch('pipeline.render_job.BarRenderer') as renderer, \
                 patch('pipeline.render_job.VideoExporter') as exporter, patch('builtins.print'):
                renderer.return_value.render_rgba.side_effect = (
                    lambda scene: str(scene.bars[0].value).encode())
                result = RenderJob(config=chart, data_source_config=DataSourceConfig(csv_path=str(csv)),
                                   export_config=export).run()
                self.assertEqual(result.frames_rendered, len(ids))
                self.assertEqual(exporter.return_value.open_stream.return_value.stdin.write.call_count,
                                 len(ids))
                self.assertEqual(renderer.return_value.render_rgba.call_args_list[0].args[0].bars[0].value,
                                 2)
                self.assertEqual(renderer.return_value.render_rgba.call_count, 3)
                output = [call.args[0] for call in
                    exporter.return_value.open_stream.return_value.stdin.write.call_args_list]
                self.assertEqual(output[-1], b'2.0')
                self.assertEqual(output[2:], [b'2.0'] * (len(ids) - 2))


if __name__ == '__main__':
    unittest.main()
