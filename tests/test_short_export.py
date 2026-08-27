import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.export_config import ExportConfig
from config.fun_fact_config import FunFactConfig
from config.project_file_loader import ProjectFileError, load_project_data
from config.project_preset import ProjectPreset
from core.layout_engine import LayoutEngine
from models.bar_data import BarData
from PIL import Image
from pipeline.render_job import RenderJob
from studio.project_builder import project_form_values
from studio.project_runtime import resolve_project_preset_paths
from studio.preview import render_project_preview
from studio.short_export import (
    apply_export_profile,
    estimate_export_duration,
    resolve_export_output_path,
    resolve_export_periods,
    short_fun_fact_config,
    short_overlay_for_frame,
)


class ShortExportTest(unittest.TestCase):
    def test_effective_output_path_preserves_standard_and_suffixes_short_once(self):
        standard = ExportConfig(mode="standard")
        short = ExportConfig(mode="short")

        self.assertEqual(
            resolve_export_output_path("race.mp4", standard),
            Path("race.mp4"),
        )
        self.assertEqual(
            resolve_export_output_path("race.mp4", short),
            Path("race_short.mp4"),
        )
        self.assertEqual(
            resolve_export_output_path("race_short.mp4", short),
            Path("race_short.mp4"),
        )

    def test_runtime_resolves_short_output_without_mutating_project_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            preset = ProjectPreset(
                name="short_output",
                chart_config=ChartConfig(output_file="output/race.mp4"),
                data_source_config=DataSourceConfig(),
                dataset_config=DatasetConfig(),
                export_config=ExportConfig(mode="short"),
            )

            effective = resolve_project_preset_paths(
                preset,
                project_root=root,
                output_root=root,
            )

        self.assertEqual(
            Path(effective.chart_config.output_file),
            root / "output" / "race_short.mp4",
        )
        self.assertEqual(preset.chart_config.output_file, "output/race.mp4")

    def test_standard_profile_preserves_existing_canvas_and_timeline(self):
        chart = ChartConfig(width=1280, height=720)
        export = ExportConfig(
            mode="standard",
            short_from_period=2001,
            short_to_period=2002,
        )

        self.assertIs(apply_export_profile(chart, export), chart)
        self.assertEqual(
            resolve_export_periods((2000, 2001, 2002), export),
            (2000, 2001, 2002),
        )

    def test_short_profile_is_native_vertical_and_recalculates_geometry(self):
        chart = ChartConfig(width=1920, height=1080, left_margin=320, top_margin=270)

        short = apply_export_profile(chart, ExportConfig(mode="short"))

        self.assertEqual((short.width, short.height), (1080, 1920))
        self.assertEqual(short.left_margin, 260)
        self.assertEqual(short.top_margin, 420)
        self.assertEqual(chart.width, 1920)
        self.assertEqual(chart.height, 1080)
        sprites = LayoutEngine(config=short).build([
            BarData(name="A", value=100),
            BarData(name="B", value=50),
        ])
        self.assertTrue(all(0 <= sprite.x < 1080 for sprite in sprites))
        self.assertTrue(all(sprite.x + sprite.width <= 1080 for sprite in sprites))

    def test_range_is_inclusive_and_rejects_invalid_or_unknown_periods(self):
        periods = (2000, 2001, 2002, 2003)
        export = ExportConfig(
            mode="short",
            short_from_period=2001,
            short_to_period=2003,
        )
        self.assertEqual(
            resolve_export_periods(periods, export),
            (2001, 2002, 2003),
        )

        with self.assertRaisesRegex(ValueError, "cannot be after"):
            resolve_export_periods(
                periods,
                ExportConfig(
                    mode="short",
                    short_from_period=2003,
                    short_to_period=2001,
                ),
            )
        with self.assertRaisesRegex(ValueError, "available timeline"):
            resolve_export_periods(
                periods,
                ExportConfig(mode="short", short_from_period=1999),
            )

    def test_duration_uses_selected_transitions_without_changing_steps(self):
        chart = ChartConfig(fps=20, steps_per_transition=40)
        export = ExportConfig(
            mode="short",
            short_from_period=2001,
            short_to_period=2003,
        )

        estimate = estimate_export_duration((2000, 2001, 2002, 2003), chart, export)

        self.assertEqual(estimate.transition_count, 2)
        self.assertEqual(estimate.frame_count, 80)
        self.assertEqual(estimate.duration_seconds, 4.0)
        self.assertEqual(chart.steps_per_transition, 40)

    def test_intro_context_and_outro_follow_frame_time(self):
        export = ExportConfig(
            mode="short",
            short_intro_duration=2.0,
            short_outro_duration=2.0,
        )

        intro = short_overlay_for_frame(
            export, frame_index=0, total_frames=300, fps=30
        )
        context = short_overlay_for_frame(
            export, frame_index=120, total_frames=300, fps=30
        )
        outro = short_overlay_for_frame(
            export, frame_index=270, total_frames=300, fps=30
        )

        self.assertEqual(intro.kind, "intro")
        self.assertGreater(intro.opacity, 0)
        self.assertEqual(context.kind, "context")
        self.assertEqual(outro.kind, "outro")

    def test_short_can_exclude_fun_facts_without_mutating_project_config(self):
        original = FunFactConfig(enabled=True, source="facts.json")

        effective = short_fun_fact_config(
            original,
            ExportConfig(mode="short", short_include_fun_facts=False),
        )

        self.assertFalse(effective.enabled)
        self.assertTrue(original.enabled)
        self.assertTrue(short_fun_fact_config(
            original,
            ExportConfig(mode="short", short_include_fun_facts=True),
        ).enabled)

    def test_export_text_settings_load_and_repopulate_form_values(self):
        data = {
            "name": "short_test",
            "export": {
                "mode": "short",
                "short_from_period": 2001,
                "short_to_period": 2005,
                "short_intro_text": "WATCH CHINA CLIMB",
                "short_intro_duration": 2.5,
                "short_context_title": "World's Largest Economies",
                "short_context_subtitle": "2001 -> 2005",
                "short_outro_text": "Watch the full ranking ->",
                "short_outro_duration": 3.0,
            },
        }

        preset = load_project_data(data)
        values = project_form_values(data)

        self.assertEqual(preset.export_config.mode, "short")
        self.assertEqual(preset.export_config.short_intro_duration, 2.5)
        self.assertEqual(preset.export_config.short_outro_duration, 3.0)
        self.assertEqual(values["short_context_subtitle"], "2001 -> 2005")

    def test_loader_rejects_non_vertical_short_resolution(self):
        with self.assertRaisesRegex(ProjectFileError, "short_width"):
            load_project_data({"export": {"short_width": 1920}})

    def test_render_job_limits_periods_and_uses_vertical_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path = root / "sample.csv"
            csv_path.write_text(
                "year,country,value\n"
                "2000,A,10\n2001,A,20\n2002,A,30\n2003,A,40\n",
                encoding="utf-8",
            )
            chart = ChartConfig(
                frames_dir=str(root / "frames"),
                output_file=str(root / "race.mp4"),
                frame_output_mode="png_sequence",
                fps=30,
                steps_per_transition=2,
            )
            export = ExportConfig(
                mode="short",
                short_from_period=2001,
                short_to_period=2003,
                short_intro_duration=0.03,
                short_outro_duration=0.05,
            )

            with patch("pipeline.render_job.BarRenderer") as renderer_class:
                with patch("pipeline.render_job.VideoExporter") as exporter_class:
                    with patch("builtins.print"):
                        result = RenderJob(
                            config=chart,
                            data_source_config=DataSourceConfig(
                                source_type="csv",
                                csv_path=str(csv_path),
                            ),
                            dataset_config=DatasetConfig(),
                            export_config=export,
                        ).run()

            renderer_config = renderer_class.call_args.kwargs["config"]
            exporter_config = exporter_class.call_args.kwargs["config"]
            scenes = [call.args[0] for call in renderer_class.return_value.render.call_args_list]
            self.assertEqual((renderer_config.width, renderer_config.height), (1080, 1920))
            self.assertEqual(
                Path(exporter_config.output_file),
                root / "race_short.mp4",
            )
            self.assertEqual(Path(result.output_file), root / "race_short.mp4")
            self.assertEqual(Path(chart.output_file), root / "race.mp4")
            self.assertEqual(result.transitions_rendered, 2)
            self.assertEqual(result.frames_rendered, 4)
            self.assertEqual(scenes[0].short_overlay.kind, "intro")
            self.assertEqual(scenes[-1].short_overlay.kind, "outro")

    def test_short_preview_renders_real_vertical_canvas_with_intro(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            csv_path = root / "sample.csv"
            csv_path.write_text(
                "year,country,value\n2000,A,10\n2001,A,20\n",
                encoding="utf-8",
            )
            project_data = {
                "name": "short_preview",
                "chart": {
                    "width": 320,
                    "height": 180,
                    "dpi": 80,
                    "left_margin": 90,
                    "right_margin": 30,
                    "top_margin": 50,
                    "bottom_margin": 25,
                    "bar_height": 18,
                    "bar_gap": 6,
                    "logos_enabled": False,
                    "max_visible_bars": 1,
                },
                "data_source": {
                    "source_type": "csv",
                    "csv_path": str(csv_path),
                },
                "dataset": {
                    "year_column": "year",
                    "name_column": "country",
                    "value_column": "value",
                },
                "export": {
                    "mode": "short",
                    "short_from_period": 2000,
                    "short_to_period": 2001,
                    "short_intro_text": "WATCH CHINA CLIMB",
                },
            }

            preview_path = render_project_preview(
                root / "project.json",
                output_dir=root / "preview",
                year=2000,
                root_dir=root,
                project_data=project_data,
            )

            with Image.open(preview_path) as preview:
                self.assertEqual(preview.size, (1080, 1920))


if __name__ == "__main__":
    unittest.main()
