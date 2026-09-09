import copy
import json
import random
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import _test_path
import pandas as pd

from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.export_config import ExportConfig
from config.project_file_loader import load_project_data, load_project_file, ProjectFileError
from config.project_preset import ProjectPreset
from core.bar_selector import BarSelector
from core.display_calendar import DisplayCalendarResolver
from core.layout_engine import LayoutEngine
from core.motion_engine import MotionEngine
from core.timeline import Timeline
from core.transition_timing import (TransitionTimingPlan, allocate_transition_steps,
    build_transition_timing_plan, minimum_transition_frames, timing_plan_from_timeline,
    transition_activity, allocation_weight)
from models.bar_data import BarData
from pipeline.render_job import RenderJob
from renderer.bar_renderer import BarRenderer
from studio.layout_preview import build_studio_layout_preview
from studio.preview import render_project_preview
from studio.project_builder import project_form_values, save_project_data
from studio.render_estimator import estimate_cache_key, sample_global_frames
from studio.short_export import apply_export_profile, resolve_export_periods
from studio.value_axis_preview import value_axis_preview_fingerprint


def bars(*values):
    return [BarData(name=name, value=value, color="#124578") for name, value in values]


class TransitionAllocationTest(unittest.TestCase):
    def test_minimum_seconds_round_up_deterministically(self):
        for seconds, expected in ((.5, 30), (1., 60), (2., 120)):
            self.assertEqual(minimum_transition_frames(seconds, 60), expected)
        self.assertEqual(minimum_transition_frames(.5, 25), 13)
        self.assertEqual(minimum_transition_frames(1.1, 30), 33)
        for bad in (True, .49, 2.01, float("nan"), float("inf"), "1"):
            with self.assertRaises(ValueError):
                minimum_transition_frames(bad, 60)

    def test_zero_gets_minimum_and_high_activity_gets_more(self):
        self.assertEqual(allocate_transition_steps([0, 1, 8], 100, 10), (10, 100, 190))

    def test_cube_root_weight_keeps_zero_order_and_compresses_ratios(self):
        self.assertEqual(allocation_weight(0), 0)
        self.assertEqual(allocation_weight(8), 2)
        scores = (.001, .008, .027, .064, .125, .5, 1.)
        weights = [allocation_weight(s) for s in scores]
        self.assertTrue(all(a < b for a, b in zip(weights, weights[1:])))
        for a, b in zip(scores, scores[1:]):
            self.assertAlmostEqual(allocation_weight(b) / allocation_weight(a), (b / a) ** (1 / 3))
            self.assertLess(allocation_weight(b) / allocation_weight(a), b / a)

    def test_all_zero_bypasses_cube_root(self):
        with patch("core.transition_timing.allocation_weight", side_effect=AssertionError("transform")):
            self.assertEqual(allocate_transition_steps([0] * 4, 100, 10), (100,) * 4)

    def test_marvel_score_snapshot_concave_allocation(self):
        # Frozen scores from the real sentinel, not special cases in production.
        scores = (0., .5935824706635136, 0., .5851624011313634,
            .25017844899129077, .22801864959911122, .12427775426882019,
            .08823503678464939, .20521105048753985, .18370680459895206,
            .06596358342735337, .09000071748432319, .17751817658068014,
            .16910991257919175, .17731029456064287, .21834979151937306,
            .17429509157742415, .24662132186646837, .17231892585892275,
            .2845851042463515, .1304166510010932, .03359041811206171,
            .1360384985632024, .18793684509503117, .17083026711375035,
            .20245604119230812, .048479935334357814, .04345542273946113)
        expected = (60, 1653, 60, 1646, 1255, 1218, 1006, 904, 1178,
            1138, 826, 910, 1125, 1108, 1125, 1202, 1119, 1249, 1115,
            1307, 1021, 672, 1035, 1146, 1112, 1173, 751, 726)
        allocated = allocate_transition_steps(scores, 1030, 60)
        self.assertEqual(allocated, expected)
        self.assertEqual(sum(allocated), 28 * 1030)
        self.assertEqual(max(allocated) / 60, 27.55)  # Derived sentinel, not a hard cap.

    def test_all_zero_falls_back_to_uniform(self):
        self.assertEqual(allocate_transition_steps([0] * 5, 1030, 60), (1030,) * 5)

    def test_minimum_that_does_not_fit_is_rejected_even_all_zero(self):
        for scores in ([0, 1], [0, 0]):
            with self.assertRaisesRegex(ValueError, "average frame budget"):
                allocate_transition_steps(scores, 30, 60)

    def test_largest_remainder_stable_ties(self):
        self.assertEqual(allocate_transition_steps([1, 1, 0], 2, 1), (3, 2, 1))

    def test_exact_budget_randomized_and_deterministic(self):
        rng = random.Random(1948)
        for _ in range(200):
            n = rng.randrange(1, 100)
            minimum = rng.choice([30, 60, 120])
            steps = minimum + rng.randrange(10000)
            scores = [rng.random() if rng.randrange(3) else 0.0 for _ in range(n)]
            result = allocate_transition_steps(scores, steps, minimum)
            self.assertEqual(sum(result), n * steps)
            self.assertGreaterEqual(min(result), minimum)
            self.assertEqual(result, allocate_transition_steps(scores, steps, minimum))
            if any(scores):
                for score, allocation in zip(scores, result):
                    if score == 0:
                        self.assertEqual(allocation, minimum)

    def test_score_scale_independent_and_counts_effective_entries_exits(self):
        a, b = bars(("A", 10), ("B", 5)), bars(("B", 20), ("C", 6))
        activity = transition_activity(a, b)
        scaled = transition_activity([replace(x, value=x.value * 1e12) for x in a],
                                     [replace(x, value=x.value * 1e12) for x in b])
        self.assertEqual(activity, scaled)
        self.assertEqual(activity.changed_bars, 3)
        self.assertGreater(activity.rank_activity, 0)
        self.assertGreater(activity.magnitude, 0)
        self.assertLessEqual(activity.score, 1)

    def test_zero_value_and_selection_activity_exactly_zero(self):
        a = bars(("Blade", 131237688))
        self.assertEqual(transition_activity(a, a).score, 0)
        self.assertEqual(transition_activity([], []).score, 0)
        tie = bars(("A", 1), ("B", 1))
        activity = transition_activity(tie, tie[::-1])
        self.assertEqual(activity.changed_bars, 0)
        self.assertGreater(activity.rank_activity, 0)

    def test_mapping_every_frame_in_both_motion_modes(self):
        for continuous in (False, True):
            plan = TransitionTimingPlan((3, 8, 2), continuous)
            self.assertEqual(plan.prefix_offsets, (0, 3, 11, 13))
            self.assertEqual(plan.total_transition_frames, 13)
            self.assertEqual(plan.frame_count, 13 + int(continuous))
            frames = []
            for i, steps in enumerate(plan.steps_per_transition):
                start, end = plan.frame_bounds(i)
                for local, frame in enumerate(range(start, end)):
                    expected = ((local + int(i > 0)) / steps if continuous else local / (steps - 1))
                    self.assertEqual(plan.locate(frame), (i, local, expected))
                    frames.append(frame)
            self.assertEqual(frames, list(range(plan.frame_count)))
            for bad in (-1, plan.frame_count, 1.5, True):
                with self.assertRaises(ValueError):
                    plan.locate(bad)

    def test_uniform_plan_matches_historical_offsets_and_counts(self):
        for mode in ("continuous", "transition_easing"):
            chart = ChartConfig(steps_per_transition=7, animation=AnimationConfig(motion_mode=mode))
            plan = build_transition_timing_plan(chart, [[], [], [], []])
            self.assertEqual(plan.steps_per_transition, (7,) * 3)
            for i in range(3):
                continuous = mode == "continuous"
                self.assertEqual(plan.frame_bounds(i), (i * 7 + int(continuous and i > 0), (i + 1) * 7 + int(continuous)))

    def test_loader_defaults_validation_and_roundtrip(self):
        self.assertEqual(load_project_data({}).chart_config.animation.transition_duration_mode, "uniform")
        self.assertEqual(project_form_values({})["minimum_transition_duration_seconds"], 1.)
        for minimum in (.5, 1., 2.):
            data = {"animation": {"transition_duration_mode": "activity_weighted",
                                   "minimum_transition_duration_seconds": minimum}}
            before = copy.deepcopy(data)
            config = load_project_data(data).chart_config.animation
            self.assertEqual(data, before)
            self.assertEqual(config.minimum_transition_duration_seconds, minimum)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "project.json"
                save_project_data(data, path)
                self.assertEqual(load_project_file(path).chart_config.animation, config)
        for field, value in (("transition_duration_mode", "adaptive"),
                             ("minimum_transition_duration_seconds", True),
                             ("minimum_transition_duration_seconds", float("nan"))):
            with self.assertRaises(ProjectFileError):
                load_project_data({"animation": {field: value}})


class TransitionTimingIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows = [(year, name, value) for year, values in (
            (2000, [("A", 100), ("B", 50)]),
            (2001, [("A", 100), ("B", 50)]),
            (2002, [("A", 140), ("B", 70)]),
            (2003, [("A", 140), ("B", 70)]),
            (2004, [("A", 80), ("B", 200), ("C", 60)])) for name, value in values]
        self.df = pd.DataFrame(self.rows, columns=["year", "country", "value"])
        self.csv = self.root / "data.csv"
        self.df.to_csv(self.csv, index=False)
        self.chart = ChartConfig(width=320, height=240, dpi=72, left_margin=60,
            right_margin=20, top_margin=60, bottom_margin=30, bar_height=25, bar_gap=5,
            steps_per_transition=40, fps=10, value_grid_enabled=True,
            start_bars_at_zero=True, date_style="flip_calendar",
            frame_output_mode="png_sequence", frames_dir=str(self.root / "frames"),
            output_file=str(self.root / "race.mp4"),
            animation=AnimationConfig(motion_mode="continuous", rank_movement_duration=.1,
                transition_duration_mode="activity_weighted"))
        self.source = DataSourceConfig(csv_path=str(self.csv))

    def scenes(self, config, export=ExportConfig(), *, samples=False):
        result_scenes = []
        with patch("pipeline.render_job.BarRenderer") as renderer, patch("pipeline.render_job.VideoExporter"), patch("builtins.print"):
            job = RenderJob(config=config, data_source_config=self.source, export_config=export)
            if samples:
                job.run(frame_sampler=sample_global_frames, frame_consumer=lambda scene, _: result_scenes.append(scene))
            else:
                job.run()
                result_scenes = [c.args[0] for c in renderer.return_value.render.call_args_list]
        return result_scenes

    def plan(self, config, export=ExportConfig()):
        timeline = Timeline(self.df)
        return timing_plan_from_timeline(apply_export_profile(config, export), timeline,
                                         resolve_export_periods(timeline.get_years(), export))

    def test_exact_budget_minima_standard_short(self):
        for mode in ("standard", "short"):
            for minimum in (.5, 1., 2.):
                config = replace(self.chart, animation=replace(self.chart.animation, minimum_transition_duration_seconds=minimum))
                plan = self.plan(config, ExportConfig(mode=mode))
                self.assertEqual(plan.total_transition_frames, 160)
                self.assertEqual(plan.frame_count, 161)
                self.assertEqual(plan.steps_per_transition[0], int(minimum * config.fps))
                self.assertEqual(plan.steps_per_transition[2], int(minimum * config.fps))

    def test_partial_and_estimator_random_access_match_full_standard_short(self):
        for motion in ("continuous", "transition_easing"):
            config = replace(self.chart, animation=replace(self.chart.animation, motion_mode=motion))
            for mode in ("standard", "short"):
                export = ExportConfig(mode=mode)
                full = self.scenes(config, export)
                plan = self.plan(config, export)
                self.assertEqual(len(full), plan.frame_count)
                for start, end in ((0, 3), (9, 15), (50, 62), (len(full) - 3, len(full))):
                    clip = self.scenes(config, replace(export, render_start_frame=start, render_end_frame=end))
                    self.assertEqual(clip, full[start:end])
                sampled = self.scenes(config, export, samples=True)
                self.assertEqual(sampled, [full[i] for i in sample_global_frames(0, len(full))])

    def test_calendar_checkpoints_and_local_progress(self):
        plan = self.plan(self.chart)
        timeline = Timeline(self.df)
        resolver = DisplayCalendarResolver.from_timeline(timeline, timeline.get_years(),
            steps_per_transition=40, continuous_motion=True, timing_plan=plan)
        self.assertEqual(resolver.frame_count, plan.frame_count)
        for frame in range(plan.frame_count):
            i, local, t = plan.locate(frame)
            a, b = resolver.anchors[i:i + 2]
            self.assertEqual(resolver.state_at(frame).display_datetime, a + (b - a) * t)

    def test_no_false_growth_and_rank_duration_scales_with_local_transition(self):
        full = self.scenes(self.chart)
        plan = self.plan(self.chart)
        for index in (0, 2):
            start, end = plan.frame_bounds(index)
            values = {b.name: b.value for b in full[start].bars}
            for scene in full[start:end]:
                self.assertEqual({b.name: b.value for b in scene.bars}, values)
        motion = MotionEngine(self.chart.animation)
        for steps in (60, 1200):
            self.assertAlmostEqual(motion._rank_progress(.05, lambda t: t)[0], .5)
            self.assertEqual(motion._rank_progress((steps * .1) / steps, lambda t: t)[0], 1.)

    def test_preview_and_layout_match_render_in_selected_short_range(self):
        for mode in ("standard", "short"):
            for motion in ("continuous", "transition_easing"):
                export = ExportConfig(mode=mode, short_from_period=2001, short_to_period=2004)
                chart = replace(self.chart, animation=replace(self.chart.animation, motion_mode=motion))
                from dataclasses import asdict
                data = {"chart": {k: v for k, v in asdict(chart).items() if k not in ("animation", "selection", "value_format", "theme")},
                    "animation": asdict(chart.animation), "selection": asdict(chart.selection),
                    "data_source": asdict(self.source), "export": asdict(export)}
                data = json.loads(json.dumps(data))
                chart = load_project_data(data).chart_config
                full = self.scenes(chart, export)
                plan = self.plan(chart, export)
                years = resolve_export_periods(Timeline(self.df).get_years(), export)
                for index, progress in ((i, p) for i in range(len(years) - 1) for p in (0., .37, 1.)):
                    frame = plan.frame_at_progress(index, progress)
                    with patch("studio.preview.BarRenderer") as renderer:
                        render_project_preview("test", root_dir=self.root, project_data=data,
                            year=years[index], preview_mode="transition", transition_progress=progress)
                        preview = renderer.return_value.render.call_args.args[0]
                    layout = build_studio_layout_preview(data, self.df,
                        {"year": years[index], "preview_mode": "transition", "transition_progress": progress}).scene
                    for scene in (preview, layout):
                        self.assertEqual(scene.frame_index, frame)
                        self.assertEqual(scene.bars, full[frame].bars)
                        self.assertEqual(scene.display_calendar, full[frame].display_calendar)
                        self.assertEqual(scene.value_axis, full[frame].value_axis)

    def test_weighted_preview_cache_keys_include_fps_steps_mode_and_minimum(self):
        from studio.project_draft import ProjectDraft
        data = {"chart": {"fps": 60, "steps_per_transition": 1030},
                "animation": {"transition_duration_mode": "activity_weighted", "minimum_transition_duration_seconds": 1.}}
        before = ProjectDraft.create(data, "test")
        for section, field, value in (("chart", "fps", 30), ("chart", "steps_per_transition", 900),
                ("animation", "transition_duration_mode", "uniform"),
                ("animation", "minimum_transition_duration_seconds", .5),
                ("export", "mode", "short")):
            variant = copy.deepcopy(data)
            variant.setdefault(section, {})[field] = value
            after = ProjectDraft.create(variant, "test")
            self.assertNotEqual(before.preview_fingerprint, after.preview_fingerprint)
            self.assertNotEqual(before.auto_preview_fingerprint, after.auto_preview_fingerprint)

    def test_uniform_legacy_and_explicit_mode_pixel_compatibility(self):
        legacy = replace(self.chart, animation=AnimationConfig(motion_mode="continuous"))
        explicit = replace(legacy, animation=replace(legacy.animation, transition_duration_mode="uniform", minimum_transition_duration_seconds=2.))
        old, new = self.scenes(legacy), self.scenes(explicit)
        self.assertEqual(old, new)
        self.assertEqual(len(old), 161)
        with_renderer = BarRenderer(output_dir=None, config=legacy)
        try:
            for frame in (0, 39, 40, 41, 160):
                self.assertEqual(with_renderer.render_rgba(old[frame]), with_renderer.render_rgba(new[frame]))
        finally:
            with_renderer.close()

    def test_estimator_and_axis_fingerprints_invalidate(self):
        preset = ProjectPreset("timing", self.chart, self.source, DatasetConfig())
        key = estimate_cache_key(preset, self.root)
        timeline = Timeline(self.df)
        selector, layout = BarSelector(self.chart.selection), LayoutEngine(self.chart)
        sprites = tuple(layout.build(selector.select(timeline.get_frame(p))) for p in timeline.get_years())
        axis_key = value_axis_preview_fingerprint(self.chart, sprites)
        for update in ({"transition_duration_mode": "uniform"}, {"minimum_transition_duration_seconds": .5}):
            chart = replace(self.chart, animation=replace(self.chart.animation, **update))
            self.assertNotEqual(key, estimate_cache_key(replace(preset, chart_config=chart), self.root))
            self.assertNotEqual(axis_key, value_axis_preview_fingerprint(chart, sprites))

    def test_impossible_minimum_fails_before_exporter_or_cleanup(self):
        config = replace(self.chart, steps_per_transition=2)
        with patch("pipeline.render_job.VideoExporter", side_effect=AssertionError("exporter")), patch("pipeline.render_job.clean_frame_directory", side_effect=AssertionError("cleanup")):
            with self.assertRaisesRegex(ValueError, "average frame budget"):
                RenderJob(config=config, data_source_config=self.source).run()

    def test_editorial_geometry_uses_same_variable_global_frames(self):
        from config.fun_fact_config import FunFactConfig
        from core.bar_value_scale import BarValueScaleResolver
        from core.editorial_placement import _effective_frame_geometry, _iter_effective_smart_geometry
        from core.fun_fact_scheduler import FunFactScheduler
        from models.fun_fact import FunFact, FunFactCollection
        timeline = Timeline(self.df)
        years = timeline.get_years()
        scheduler = FunFactScheduler(FunFactCollection(1,
            (FunFact("timing", "2000", "2004", "Activity"),), "facts.json"), timeline)
        selector, layout = BarSelector(self.chart.selection), LayoutEngine(self.chart)
        endpoints = {year: layout.build(selector.select(timeline.get_frame(year))) for year in years}
        config = FunFactConfig()
        arguments = dict(chart_config=self.chart, fun_fact_config=config, scheduler=scheduler,
            periods=years, sprites_by_period=endpoints, source_label="", calendar_resolver=None,
            scale_resolver=BarValueScaleResolver.from_config(self.chart, endpoints.values()))
        full = self.scenes(self.chart)
        with patch("core.editorial_placement.build_scene_geometry", side_effect=lambda c, f, s: s):
            geometry = _effective_frame_geometry(**arguments)
        with patch("core.editorial_placement.build_smart_scene_geometry", side_effect=lambda c, f, s, **kw: s), patch("core.editorial_placement._cached_smart_text_bounds", return_value={}):
            smart = list(_iter_effective_smart_geometry(**arguments, logo_availability={}))
        self.assertEqual(len(geometry), len(full))
        self.assertEqual(len(smart), len(full))
        for (frame, position), scene in geometry.items():
            self.assertEqual(scene.bars, full[frame].bars)
            self.assertEqual(scene.frame_index, frame)
            self.assertEqual(smart[frame][0:2], (frame, position))
            self.assertEqual(smart[frame][2].bars, scene.bars)
