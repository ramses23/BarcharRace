import copy
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch, Mock

import _test_path
from config.chart_config import ChartConfig
from config.animation_config import AnimationConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.export_config import ExportConfig
from config.project_preset import ProjectPreset
from pipeline.render_job import RenderJob
from studio.render_estimator import (sample_global_frames, human_render_time,
    estimate_render_job, estimate_cache_key, cached_estimate, job_from_preset)


class RenderEstimatorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.csv = self.root / "data.csv"
        self.csv.write_text("year,country,value\n0,A,100\n0,B,80\n1,A,60\n1,B,150\n2,A,160\n2,B,90\n", encoding="utf-8")
        self.preset = ProjectPreset("test", ChartConfig(width=320, height=240, dpi=72,
            left_margin=60, right_margin=20, top_margin=60, bottom_margin=30,
            steps_per_transition=30, fps=30, value_grid_enabled=True,
            frames_dir=str(self.root / "must_not_create_frames"),
            output_file=str(self.root / "must_not_create.mp4"),
            animation=AnimationConfig(motion_mode="continuous", rank_movement_duration=.1)),
            DataSourceConfig(csv_path=str(self.csv)), DatasetConfig())

    def test_deterministic_uniform_selection_and_small_windows(self):
        ids = sample_global_frames(9000, 10800)
        self.assertEqual(len(ids), 16)
        self.assertEqual(ids, sample_global_frames(9000, 10800))
        self.assertEqual((ids[0], ids[-1]), (9000, 10799))
        self.assertTrue(all(9000 <= f < 10800 for f in ids))
        self.assertEqual(sample_global_frames(70, 72), (70, 71))
        self.assertEqual(sample_global_frames(70, 71), (70,))
        for start, end in ((-1, 10), (5, 5), (6, 5)):
            with self.assertRaises(ValueError):
                sample_global_frames(start, end)

    def test_actual_raster_sample_has_global_frames_and_no_files_or_mutation(self):
        preset = replace(self.preset, export_config=ExportConfig(render_start_frame=35, render_end_frame=55))
        before = copy.deepcopy(preset)
        files = list(self.root.rglob("*"))
        with patch("pipeline.render_job.VideoExporter", side_effect=AssertionError("exporter")), \
             patch("pipeline.render_job.clean_frame_directory", side_effect=AssertionError("cleanup")):
            result = estimate_render_job(job_from_preset(preset, self.root))
        self.assertEqual(preset, before)
        self.assertEqual(list(self.root.rglob("*")), files)
        self.assertEqual(result.output_frames, 20)
        self.assertEqual(result.sample_frames, sample_global_frames(35, 55))
        self.assertEqual(result.warmup_frames, 2)
        self.assertGreater(result.estimated_seconds, 0)
        self.assertEqual(len(result.sample_seconds), 16)

    def test_full_and_custom_frame_authority(self):
        for start, end, expected in ((None, None, 61), (0, 30, 30), (40, 50, 10)):
            preset = replace(self.preset, export_config=ExportConfig(render_start_frame=start, render_end_frame=end))
            with patch("pipeline.render_job.BarRenderer"):
                result = estimate_render_job(job_from_preset(preset, self.root))
            self.assertEqual(result.output_frames, expected)

    def test_sample_scenes_equal_full_render_scenes_including_short(self):
        for mode in ("standard", "short"):
            preset = replace(self.preset, export_config=ExportConfig(mode=mode))
            with patch("pipeline.render_job.BarRenderer") as renderer, \
                 patch("pipeline.render_job.VideoExporter"), patch("builtins.print"):
                job_from_preset(preset, self.root).run()
                calls = renderer.return_value.render_rgba.call_args_list
                if not calls:
                    calls = renderer.return_value.render.call_args_list
                full = [c.args[0] for c in calls]
            scenes = []
            job = job_from_preset(preset, self.root)
            with patch("pipeline.render_job.BarRenderer"):
                result = job.run(frame_sampler=sample_global_frames,
                    frame_consumer=lambda scene, renderer: scenes.append(scene))
            self.assertEqual(scenes, [full[i] for i in sample_global_frames(0, 61)])
            self.assertEqual(result.output_file, "")

    def test_key_changes_with_fps_resolution_range_format_and_visual_features(self):
        key = estimate_cache_key(self.preset, self.root)
        self.assertEqual(key, estimate_cache_key(self.preset, self.root))
        variants = [replace(self.preset, chart_config=replace(self.preset.chart_config, **change))
                    for change in ({"fps": 60}, {"width": 640}, {"bar_gradient_enabled": False},
                        {"value_grid_enabled": False}, {"label_font_family": "Arial"})]
        variants += [replace(self.preset, export_config=ExportConfig(**change))
                     for change in ({"mode": "short"}, {"render_start_frame": 10}, {"render_end_frame": 20})]
        for variant in variants:
            self.assertNotEqual(key, estimate_cache_key(variant, self.root))
        self.csv.write_text(self.csv.read_text() + "3,A,90\n", encoding="utf-8")
        self.assertNotEqual(key, estimate_cache_key(self.preset, self.root))

    def test_fps_changes_requested_seconds_to_frame_count(self):
        from utils.render_window import timecode_to_frame
        for fps, expected in ((30, 900), (60, 1800)):
            self.assertEqual(timecode_to_frame("30", fps), expected)

    def test_cache_hit_and_active_render_guard(self):
        cache, factory = {}, Mock()
        with patch("studio.render_estimator.estimate_render_job", return_value="measured") as measure:
            self.assertEqual(cached_estimate(cache, "a", factory), "measured")
            self.assertEqual(cached_estimate(cache, "a", factory), "measured")
            measure.assert_called_once()
            cached_estimate(cache, "b", factory)
            self.assertEqual(list(cache), ["b"])
            with self.assertRaises(RuntimeError):
                cached_estimate(cache, "c", factory, render_active=True)
            self.assertEqual(measure.call_count, 2)

    def test_ui_button_is_disabled_during_active_render(self):
        import pandas as pd
        from studio.project_draft import ProjectDraft
        from ui.project_studio import _render_time_estimate_panel
        draft = ProjectDraft.create({"data_source": {"csv_path": str(self.csv)}}, "test.json")
        with patch("ui.project_studio.st") as st, \
             patch("ui.project_studio._active_project_root", return_value=self.root):
            st.session_state = {}
            st.button.return_value = False
            _render_time_estimate_panel(draft, pd.read_csv(self.csv), render_active=True)
            self.assertTrue(st.button.call_args.kwargs["disabled"])

    def test_robust_statistic_and_frame_extrapolation(self):
        class Job:
            def run(self, *, frame_sampler, frame_consumer):
                for _ in frame_sampler(9000, 10800):
                    frame_consumer(None, Mock())
                return Mock(profile=Mock(total_seconds=10., render_frames_seconds=9.))
        # Every call takes one second except a single measured outlier.
        values, tick = [], 0
        for i in range(38):
            tick += 100 if i == 10 else 1
            values.append(tick)
        result = estimate_render_job(Job(), clock=iter(values).__next__)
        self.assertEqual(result.median_frame_seconds, 1.)
        self.assertEqual(result.estimated_seconds, 1801.)

    def test_human_time_format(self):
        for value, text in ((42, "42 sec"), (198, "3 min 18 sec"),
                            (1637, "27 min"), (4440, "1 h 14 min")):
            self.assertEqual(human_render_time(value), text)

    def test_full_thirty_second_and_ten_second_estimates_follow_frame_count(self):
        estimates = []
        for start, end in ((0, 1800), (300, 1200), (300, 600)):
            class Job:
                def run(self, *, frame_sampler, frame_consumer):
                    for frame in frame_sampler(start, end):
                        self.assert_frame = frame
                        frame_consumer(None, Mock())
                    return Mock(profile=Mock(total_seconds=10., render_frames_seconds=9.))
            estimate = estimate_render_job(Job(), clock=iter(range(100)).__next__)
            estimates.append(estimate.estimated_seconds)
        self.assertEqual(estimates, [1801., 901., 301.])
