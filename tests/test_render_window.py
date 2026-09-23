import tempfile
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import _test_path
from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.export_config import ExportConfig
from config.fun_fact_config import FunFactConfig
from config.project_file_loader import load_project_data, ProjectFileError
from pipeline.render_job import RenderJob
from renderer.bar_renderer import BarRenderer
from studio.short_export import resolve_export_output_path
from utils.render_window import resolve_render_window, timecode_to_frame, frame_to_timecode


class RenderWindowTest(unittest.TestCase):
    def test_partial_pixels_and_short_overlays_match_global_full_frames(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            csv = root / "data.csv"
            csv.write_text("year,country,value\n0,A,100\n0,B,80\n1,A,60\n1,B,150\n2,A,160\n2,B,90\n", encoding="utf-8")
            config = ChartConfig(width=320, height=240, dpi=72, left_margin=60,
                right_margin=20, top_margin=70, bottom_margin=30, steps_per_transition=4,
                title_enabled=False, subtitle_enabled=False, source_label_enabled=False,
                value_grid_enabled=True, background_motion="forward", frame_output_mode="ffmpeg_stream",
                animation=AnimationConfig(motion_mode="continuous"))
            source = DataSourceConfig(source_type="csv", csv_path=str(csv))
            facts = root / "facts.json"
            facts.write_text(json.dumps({"version": 1, "fun_facts": [{
                "id": "crossing", "start": "0", "end": "0",
                "headline": "Crossing", "body": "Global timeline parity",
            }]}), encoding="utf-8")
            fact_config = FunFactConfig(enabled=True, source=str(facts),
                layout="editorial_floating", editorial_card_width=240,
                editorial_card_height=140, editorial_card_x=50, editorial_card_y=50,
                editorial_layout_mode="overlay", editorial_placement_mode="smart")
            for mode in ("standard", "short"):
                export = ExportConfig(mode=mode)
                pixels = []
                scenes = []
                def run(settings):
                    with patch("pipeline.render_job.BarRenderer") as factory, patch("pipeline.render_job.VideoExporter"), patch("builtins.print"):
                        real = None
                        def create(**kwargs):
                            nonlocal real
                            real = BarRenderer(**kwargs)
                            renderer = type("Capture", (), {})()
                            def render(scene):
                                scenes.append(scene)
                                pixels.append(real.render_rgba(scene))
                                return pixels[-1]
                            renderer.render_rgba = render
                            renderer.close = real.close
                            return renderer
                        factory.side_effect = create
                        RenderJob(config=config, data_source_config=source,
                            fun_fact_config=fact_config, export_config=settings).run()
                run(export)
                full_pixels, full_scenes = pixels[:], scenes[:]
                if mode == "standard":
                    self.assertTrue(any(scene.fun_fact is not None for scene in scenes[3:7]))
                    # Frames after the original year still carry its card.
                    self.assertEqual(scenes[6].fun_fact.fact.id, "crossing")
                pixels.clear()
                scenes.clear()
                run(replace(export, render_start_frame=3, render_end_frame=7))
                self.assertEqual(scenes, full_scenes[3:7])
                self.assertEqual(pixels, full_pixels[3:7])

    def test_time_conversion_is_frame_exact(self):
        self.assertEqual(timecode_to_frame("02:30.000", 60), 9000)
        self.assertEqual(timecode_to_frame("03:00.000", 60), 10800)
        self.assertEqual(timecode_to_frame("0.025", 60), 2)
        for fps in (24, 60, 144, 240):
            for frame in (0, 1, 9001, 28918):
                self.assertEqual(timecode_to_frame(frame_to_timecode(frame, fps), fps), frame)

    def test_invalid_timecodes_rejected(self):
        for text in ("bad", "-1", "NaN", "Infinity", "1:60", "1:2:3:4", "1.5:20"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                timecode_to_frame(text, 60)

    def test_ranges_are_half_open_and_strict(self):
        self.assertEqual(resolve_render_window(100, ExportConfig()), (0, 100))
        for start, end in ((0, 10), (30, 60), (90, 100)):
            self.assertEqual(resolve_render_window(100, ExportConfig(render_start_frame=start, render_end_frame=end)), (start, end))
        for start, end in ((-1, 10), (2, 2), (10, 5), (0, 101), (True, 10), (1.5, 10)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                resolve_render_window(100, ExportConfig(render_start_frame=start, render_end_frame=end))

    def test_loader_preserves_frames_and_defaults(self):
        self.assertIsNone(load_project_data({}).export_config.render_start_frame)
        config = load_project_data({"export": {"render_start_frame": 9000, "render_end_frame": 10800}}).export_config
        self.assertEqual((config.render_start_frame, config.render_end_frame), (9000, 10800))
        for value in (-1, True, 1.5, "10"):
            with self.subTest(value=value), self.assertRaises(ProjectFileError):
                load_project_data({"export": {"render_start_frame": value}})

    def test_clip_names_protect_full_output(self):
        for mode in ("standard", "short"):
            full = resolve_export_output_path("race.mp4", ExportConfig(mode=mode))
            clip = resolve_export_output_path("race.mp4", ExportConfig(mode=mode, render_start_frame=9000, render_end_frame=10800))
            self.assertNotEqual(full, clip)
            self.assertIn("_clip_f9000_f10800", clip.stem)

    def test_partial_scenes_match_full_with_exact_progress_and_local_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            csv = root / "data.csv"
            csv.write_text("year,country,value\n2000,A,100\n2000,B,80\n2001,A,70\n2001,B,130\n2002,A,160\n2002,B,90\n", encoding="utf-8")
            source = DataSourceConfig(source_type="csv", csv_path=str(csv))
            for mode in ("transition", "continuous"):
                config = ChartConfig(
                    steps_per_transition=8, fps=60, value_grid_enabled=True,
                    start_bars_at_zero=True, date_style="flip_calendar",
                    frame_output_mode="png_sequence", frames_dir=str(root / "frames"),
                    output_file=str(root / "race.mp4"),
                    animation=AnimationConfig(motion_mode=mode, rank_movement_duration=0.1),
                )
                def run(export):
                    events = []
                    with patch("pipeline.render_job.BarRenderer") as renderer, patch("pipeline.render_job.VideoExporter"), patch("builtins.print"):
                        result = RenderJob(config=config, data_source_config=source, export_config=export, progress_callback=events.append).run()
                        calls = renderer.return_value.render.call_args_list
                    return result, calls, events
                _, full, _ = run(ExportConfig())
                for start, end in ((0, 3), (1, 2), (4, 10), (len(full) - 2, len(full)), (0, len(full))):
                    with self.subTest(mode=mode, start=start, end=end):
                        result, clip, events = run(ExportConfig(render_start_frame=start, render_end_frame=end))
                        self.assertEqual(result.frames_rendered, end - start)
                        self.assertEqual(len(clip), end - start)
                        for local, call in enumerate(clip):
                            self.assertEqual(call.args[0], full[start + local].args[0])
                            self.assertEqual(call.kwargs["filename"], config.frame_filename(local))
                        progress = [e for e in events if e.stage == "render_frames"]
                        self.assertEqual([e.current for e in progress], list(range(end - start + 1)))
                        self.assertTrue(all(e.total == end - start for e in progress))

    def test_middle_clip_never_interpolates_full_transitions(self):
        # A full-history motion replay would call these bulk interpolation APIs.
        with patch("core.motion_engine.MotionEngine.interpolate_sprites", side_effect=AssertionError("bulk replay")), patch("core.motion_engine.MotionEngine.interpolate_sprites_continuous", side_effect=AssertionError("bulk replay")):
            with tempfile.TemporaryDirectory() as temp:
                csv = Path(temp) / "data.csv"
                csv.write_text("year,country,value\n0,A,1\n1,A,2\n2,A,3\n", encoding="utf-8")
                with patch("pipeline.render_job.BarRenderer") as renderer, patch("pipeline.render_job.VideoExporter"), patch("builtins.print"):
                    result = RenderJob(
                        config=ChartConfig(steps_per_transition=600, frame_output_mode="ffmpeg_stream"),
                        data_source_config=DataSourceConfig(source_type="csv", csv_path=str(csv)),
                        export_config=ExportConfig(render_start_frame=900, render_end_frame=903),
                    ).run()
                    self.assertEqual(renderer.return_value.render_rgba.call_count, 3)
                    self.assertEqual(result.frames_rendered, 3)
