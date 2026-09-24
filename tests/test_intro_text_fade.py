import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import _test_path
from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.export_config import ExportConfig
from config.project_file_loader import ProjectFileError, load_project_data, load_project_file
from core.layout_engine import structural_race_vertical_bounds
from core.scene_geometry import build_smart_text_bounds
from config.fun_fact_config import FunFactConfig
from models.scene import Scene
from pipeline.render_job import RenderJob
from renderer.bar_renderer import BarRenderer
from renderer.text_compositor import intro_text_lifecycle_opacity
from studio.preview import render_project_preview
from studio.project_builder import project_form_values, save_project_data


class IntroTextFadeTest(unittest.TestCase):
    def test_default_and_smooth_global_frame_timing(self):
        legacy = ChartConfig(fps=20)
        self.assertEqual(legacy.intro_text_behavior, "persistent")
        for frame in (0, 200, 215, 230, 1000):
            self.assertEqual(intro_text_lifecycle_opacity(legacy, frame), 1.0)

        timed = replace(legacy, intro_text_behavior="timed_fade")
        self.assertEqual(intro_text_lifecycle_opacity(timed, 0), 1.0)
        self.assertEqual(intro_text_lifecycle_opacity(timed, 200), 1.0)
        self.assertAlmostEqual(intro_text_lifecycle_opacity(timed, 215), 0.5)
        self.assertEqual(intro_text_lifecycle_opacity(timed, 230), 0.0)
        self.assertEqual(intro_text_lifecycle_opacity(timed, 400), 0.0)

    def test_only_title_and_subtitle_multiply_configured_opacity(self):
        config = ChartConfig(width=400, height=240, dpi=72, fps=20,
            intro_text_behavior="timed_fade", title_text_opacity=.8,
            subtitle_text_opacity=.6, time_label_opacity=.4,
            source_text_opacity=.7, logos_enabled=False)
        renderer = BarRenderer(config=config)
        scene = Scene(title="Title", subtitle="2000 → 2001 · units",
                      time_label="2000", source_label="Source")
        try:
            def commands(frame):
                scene.frame_index = frame
                renderer.render_rgba(scene)
                return (renderer._intro_text_artist.commands,
                        renderer._text_foreground_artist.commands,
                        renderer._text_background_artist.commands)

            full, source_full, date_full = commands(0)
            halfway, source_halfway, date_halfway = commands(215)
            gone, source_gone, date_gone = commands(230)
            self.assertEqual(len(full), 2)
            self.assertEqual(len(halfway), 2)
            self.assertEqual(len(gone), 0)
            for index in (0, 1):
                self.assertEqual(full[index][1:], halfway[index][1:])
                self.assertAlmostEqual(halfway[index][0][:, :, 3].max()
                                       / full[index][0][:, :, 3].max(), .5, delta=.02)
            self.assertEqual(source_full[0][0].tobytes(), source_halfway[0][0].tobytes())
            self.assertEqual(source_full[0][0].tobytes(), source_gone[0][0].tobytes())
            self.assertEqual(date_full[0][0].tobytes(), date_halfway[0][0].tobytes())
            self.assertEqual(date_full[0][0].tobytes(), date_gone[0][0].tobytes())
            self.assertGreater(renderer._intro_text_artist.get_zorder(),
                               renderer._logo_composite_artist.get_zorder())
            self.assertGreater(renderer._intro_text_artist.get_zorder(),
                               renderer._text_bar_artist.get_zorder())
            self.assertGreater(renderer._intro_text_artist.get_zorder(),
                               renderer._fun_fact_artist.get_zorder())
        finally:
            renderer.close()

    def test_timed_overlay_does_not_reserve_rows_or_smart_card_space(self):
        persistent = ChartConfig(width=640, height=400, dpi=72,
            bar_vertical_layout_mode="fill_available", bar_vertical_top_padding=0,
            value_grid_enabled=True, title_y=55, subtitle_y=105)
        overlay = replace(persistent, intro_text_behavior="timed_fade")
        old_top, old_bottom = structural_race_vertical_bounds(persistent)
        new_top, new_bottom = structural_race_vertical_bounds(overlay)
        self.assertLess(new_top, old_top)
        self.assertEqual(new_bottom, old_bottom)
        self.assertEqual(overlay.bar_vertical_top_padding, persistent.bar_vertical_top_padding)
        scene = Scene(title="Title", subtitle="Range · units", source_label="Source")
        facts = FunFactConfig()
        self.assertEqual(len(build_smart_text_bounds(persistent, facts, scene)), 4)
        self.assertEqual(len(build_smart_text_bounds(overlay, facts, scene)), 2)

    def test_timed_overlay_geometry_is_fixed_across_fade(self):
        with tempfile.TemporaryDirectory() as directory:
            csv = Path(directory) / "data.csv"
            csv.write_text("year,country,value\n0,A,100\n0,B,60\n1,A,100\n1,B,60\n", encoding="utf-8")
            config = ChartConfig(width=640, height=400, fps=20,
                steps_per_transition=260, bar_vertical_layout_mode="fill_available",
                value_grid_enabled=True, intro_text_behavior="timed_fade")
            scenes = []
            with patch("pipeline.render_job.BarRenderer"), patch("builtins.print"):
                RenderJob(config=config,
                    data_source_config=DataSourceConfig(csv_path=str(csv))).run(
                    frame_sampler=lambda start, end: (180, 200, 215, 230, 240),
                    frame_consumer=lambda scene, renderer: scenes.append(scene))
            geometry = [tuple((bar.name, bar.y, bar.height) for bar in scene.bars)
                        for scene in scenes]
            self.assertTrue(all(rows == geometry[0] for rows in geometry))
            self.assertTrue(all(scene.value_axis.line_top == scenes[0].value_axis.line_top
                                for scene in scenes))
            self.assertEqual([intro_text_lifecycle_opacity(config, scene.frame_index)
                              for scene in scenes], [1.0, 1.0, .5, 0.0, 0.0])

    def test_config_json_round_trip_and_invalid_values(self):
        self.assertEqual(load_project_data({}).chart_config.intro_text_behavior, "persistent")
        chart = {"intro_text_behavior": "timed_fade",
                 "intro_text_visible_duration_seconds": 7.5,
                 "intro_text_fade_duration_seconds": 2.25}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            save_project_data({"chart": chart}, path)
            restored = load_project_file(path).chart_config
        self.assertEqual((restored.intro_text_behavior,
                          restored.intro_text_visible_duration_seconds,
                          restored.intro_text_fade_duration_seconds),
                         ("timed_fade", 7.5, 2.25))
        self.assertEqual(project_form_values({"chart": chart})["intro_text_behavior"], "timed_fade")
        for field, value in (("intro_text_behavior", "unknown"),
                             ("intro_text_visible_duration_seconds", -1),
                             ("intro_text_fade_duration_seconds", float("nan"))):
            with self.subTest(field=field), self.assertRaises(ProjectFileError):
                load_project_data({"chart": {field: value}})

    def test_render_job_uses_global_frames_for_clips_timing_and_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            csv = Path(directory) / "data.csv"
            csv.write_text("year,country,value\n0,A,1\n1,A,2\n2,A,3\n", encoding="utf-8")
            source = DataSourceConfig(csv_path=str(csv))
            requested = (0, 190, 200, 215, 230, 232, 400, 590)
            for timing in ("uniform", "activity_weighted"):
                with self.subTest(timing=timing):
                    config = ChartConfig(fps=20, steps_per_transition=260,
                        start_bars_at_zero=True, value_grid_enabled=True,
                        intro_text_behavior="timed_fade",
                        animation=AnimationConfig(transition_duration_mode=timing))

                    def sample(export, frames):
                        scenes = []
                        with patch("pipeline.render_job.BarRenderer"), patch("builtins.print"):
                            RenderJob(config=config, data_source_config=source,
                                      export_config=export).run(
                                frame_sampler=lambda start, end: tuple(
                                    frame for frame in frames if start <= frame < end),
                                frame_consumer=lambda scene, renderer: scenes.append(scene))
                        return {frame: scene for frame, scene in zip(frames, scenes)}

                    full = sample(ExportConfig(final_frame_hold_seconds=2), requested)
                    clip = sample(ExportConfig(render_start_frame=180,
                        render_end_frame=240, final_frame_hold_seconds=2),
                        (190, 200, 215, 230, 232))
                    for frame, scene in clip.items():
                        self.assertEqual(scene, full[frame])
                        self.assertEqual(scene.frame_index, frame)
                    late_clip = sample(ExportConfig(render_start_frame=400,
                        render_end_frame=500, final_frame_hold_seconds=2), (400, 450))
                    self.assertEqual(late_clip[400], full[400])
                    self.assertEqual(intro_text_lifecycle_opacity(config, late_clip[450].frame_index), 0)
                    self.assertEqual(intro_text_lifecycle_opacity(config, full[0].frame_index), 1)
                    self.assertAlmostEqual(intro_text_lifecycle_opacity(config, full[215].frame_index), .5)
                    self.assertEqual(intro_text_lifecycle_opacity(config, full[400].frame_index), 0)
                    self.assertEqual(intro_text_lifecycle_opacity(config, full[590].frame_index), 0)
                    self.assertLess(full[590].frame_index, 590)
                    for review in ("quick", "motion"):
                        reviewed = sample(ExportConfig(review_mode=review), (215, 230))
                        self.assertEqual([scene.frame_index for scene in reviewed.values()], [215, 230])
                        self.assertAlmostEqual(intro_text_lifecycle_opacity(config, reviewed[215].frame_index), .5)

    def test_preview_and_short_keep_video_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv = root / "data.csv"
            csv.write_text("year,country,value\n0,A,1\n1,A,2\n2,A,3\n", encoding="utf-8")
            for mode in ("standard", "short"):
                project = {"chart": {"fps": 20, "steps_per_transition": 260,
                    "start_bars_at_zero": True, "value_grid_enabled": True,
                    "intro_text_behavior": "timed_fade"},
                    "data_source": {"csv_path": str(csv)},
                    "export": {"mode": mode}}
                with self.subTest(mode=mode), patch("studio.preview.BarRenderer") as renderer:
                    render_project_preview("preview", root_dir=root, project_data=project,
                        year=0, preview_mode="transition", transition_progress=175 / 259)
                    scene = renderer.return_value.render.call_args.args[0]
                    self.assertEqual(scene.frame_index, 215)
                    self.assertAlmostEqual(intro_text_lifecycle_opacity(
                        renderer.call_args.kwargs["config"], scene.frame_index), .5)

    def test_studio_controls_persist_with_existing_title_opacity(self):
        from streamlit.testing.v1 import AppTest

        app_path = Path(__file__).resolve().parents[1] / "src/ui/project_studio.py"
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        section = next(control for control in app.get("button_group")
                       if control.label == "Editor section")
        section.set_value("Canvas")
        app.run()
        next(control for control in app.selectbox
             if control.label == "Intro text behavior").set_value("timed_fade")
        app.run()
        next(control for control in app.number_input
             if control.label == "Visible duration (seconds)").set_value(8.0)
        next(control for control in app.number_input
             if control.label == "Fade duration (seconds)").set_value(2.0)
        app.run()
        self.assertFalse(app.exception)
        chart = json.loads(app.json[0].value)["chart"]
        self.assertEqual((chart["intro_text_behavior"],
                          chart["intro_text_visible_duration_seconds"],
                          chart["intro_text_fade_duration_seconds"]),
                         ("timed_fade", 8.0, 2.0))
        self.assertEqual(chart["title_text_opacity"], 1.0)


if __name__ == "__main__":
    unittest.main()
