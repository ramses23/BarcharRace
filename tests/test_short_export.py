import tempfile
import unittest
from dataclasses import fields, replace
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
from core.rank_motion import RANK_MOTION_HEIGHT_EMPHASIS
from core.bar_value_scale import BarValueScaleResolver
from core.scene_geometry import build_scene_geometry
from core.layout_engine import LayoutEngine
from models.bar_data import BarData
from models.bar_sprite import BarSprite
from models.scene import Scene
from PIL import Image
from pipeline.render_job import RenderJob
from studio.project_builder import project_form_values
from studio.fun_fact_layout import editorial_geometry
from studio.project_runtime import resolve_project_preset_paths
from studio.preview import render_project_preview
from studio.short_export import (
    apply_export_profile,
    estimate_export_duration,
    resolve_export_output_path,
    resolve_export_periods,
    short_bar_area_bottom,
    short_fun_fact_config,
    short_overlay_for_frame,
)


class ShortExportTest(unittest.TestCase):
    def test_progression_reference_uses_effective_short_range(self):
        periods = (2000, 2001, 2002, 2003, 2004)
        all_sets = [
            [BarSprite(
                name="Leader",
                value=value,
                color="#123456",
                x=100,
                y=100,
                width=600,
                height=40,
                bar_available_width=600,
            )]
            for value in (10, 20, 30, 40, 50)
        ]
        chart = ChartConfig(
            steps_per_transition=10,
            leader_full_width_point=0.5,
        )
        short_periods = resolve_export_periods(
            periods,
            ExportConfig(
                mode="short",
                short_from_period=2002,
                short_to_period=2004,
            ),
        )
        selected_sets = [
            all_sets[periods.index(period)]
            for period in short_periods
        ]

        standard = BarValueScaleResolver.from_config(chart, all_sets)
        short = BarValueScaleResolver.from_config(chart, selected_sets)

        self.assertEqual(short_periods, (2002, 2003, 2004))
        self.assertEqual(standard.domain_max, 30)
        self.assertEqual(short.domain_max, 40)
        self.assertNotEqual(standard.domain_max, short.domain_max)

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

    def test_short_fill_available_reserves_date_and_source_safe_region(self):
        chart = ChartConfig(
            width=1920,
            height=1080,
            dpi=150,
            max_visible_bars=10,
            auto_fit_bar_count=True,
            bar_vertical_layout_mode="fill_available",
            bar_vertical_top_padding=18,
            bar_vertical_bottom_padding=18,
            title_enabled=False,
            subtitle_enabled=False,
            time_label_enabled=True,
            time_label_font_size=70,
            source_label_enabled=True,
            source_font_size=13,
            logos_enabled=True,
            logo_size=100,
            bar_logo_position="inside_right",
            value_labels_enabled=True,
            value_font_size=26,
            value_grid_enabled=True,
            value_grid_tick_labels_enabled=True,
        )
        short = apply_export_profile(chart, ExportConfig(mode="short"))
        bars = [
            BarData(
                name=f"Browser {index}",
                value=10 - index,
                logo_path=f"browser-{index}.png",
            )
            for index in range(10)
        ]
        sprites = LayoutEngine(config=short).build(bars)
        scene = Scene(
            title="",
            time_label="2009-04",
            source_label="Source: browser dataset",
            bars=sprites,
        )
        geometry = build_scene_geometry(short, FunFactConfig(), scene)
        last_row = geometry["row_rects"][-1]
        last_row_bottom = last_row["y"] + last_row["height"]
        effective_rank_bottom = (
            last_row_bottom + (RANK_MOTION_HEIGHT_EMPHASIS / 2.0)
        )
        date_top = geometry["text_bounds"]["date"]["y"]
        source_top = geometry["text_bounds"]["source"]["y"]
        value_bottom = (
            sprites[-1].y
            + (short.value_font_size * short.dpi / 144.0)
        )
        last_logo = geometry["primary_logo_rects"][-1]
        last_logo_bottom = last_logo["y"] + last_logo["height"]

        self.assertEqual((short.width, short.height), (1080, 1920))
        self.assertEqual(len(sprites), 10)
        self.assertLessEqual(
            effective_rank_bottom + 12.0,
            date_top,
        )
        self.assertLessEqual(value_bottom, date_top)
        self.assertLessEqual(last_logo_bottom, date_top)
        self.assertLessEqual(effective_rank_bottom + 12.0, source_top)
        self.assertEqual(
            short.height - short.bar_vertical_bottom_padding,
            int(short_bar_area_bottom(replace(
                short,
                bar_vertical_bottom_padding=chart.bar_vertical_bottom_padding,
            ))),
        )

    def test_short_safe_region_does_not_change_standard_or_editorial_geometry(self):
        chart = ChartConfig(
            width=1920,
            height=1080,
            bar_vertical_layout_mode="fill_available",
            max_visible_bars=10,
        )
        bars = [BarData(name=str(index), value=10 - index) for index in range(10)]
        standard_rows = LayoutEngine(config=chart).build(bars)

        standard = apply_export_profile(chart, ExportConfig(mode="standard"))
        reapplied_rows = LayoutEngine(config=standard).build(bars)

        self.assertIs(standard, chart)
        self.assertEqual(
            [(sprite.y, sprite.height) for sprite in standard_rows],
            [(sprite.y, sprite.height) for sprite in reapplied_rows],
        )

        short = apply_export_profile(chart, ExportConfig(mode="short"))
        prior_short = replace(
            short,
            bar_vertical_bottom_padding=chart.bar_vertical_bottom_padding,
        )
        facts = FunFactConfig(
            enabled=True,
            layout="editorial_floating",
            editorial_card_x=520,
            editorial_card_y=300,
            editorial_card_width=500,
            editorial_card_height=700,
        )
        self.assertEqual(
            editorial_geometry(prior_short, facts),
            editorial_geometry(short, facts),
        )

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
            short_intro_text="A neutral intro",
            short_context_title="Configured context",
            short_context_subtitle="Configured range",
            short_outro_text="Configured CTA",
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

    def test_short_defaults_are_semantically_neutral_and_draw_no_empty_panel(self):
        export = ExportConfig(mode="short")
        default_text = " ".join((
            export.short_intro_text,
            export.short_context_title,
            export.short_context_subtitle,
            export.short_outro_text,
        ))

        self.assertNotIn("World’s Largest Economies", default_text)
        self.assertNotIn("2001 → 2005", default_text)
        self.assertNotIn("CHINA", default_text)
        self.assertEqual(default_text.strip(), "")
        for frame_index in (0, 120, 299):
            self.assertIsNone(short_overlay_for_frame(
                export,
                frame_index=frame_index,
                total_frames=300,
                fps=30,
            ))

    def test_legacy_defaults_load_and_explicit_short_text_roundtrips_exactly(self):
        legacy = load_project_data({"name": "legacy"})
        self.assertEqual(legacy.export_config, ExportConfig())
        self.assertIsNone(short_overlay_for_frame(
            replace(legacy.export_config, mode="short"),
            frame_index=0,
            total_frames=30,
            fps=30,
        ))

        configured = ExportConfig(
            mode="short",
            short_intro_text="  Exact intro  ",
            short_context_title="Exact project topic",
            short_context_subtitle="1999 → 2026",
            short_outro_text="Exact CTA →",
        )
        serialized = {
            "name": "configured",
            "export": {
                field.name: getattr(configured, field.name)
                for field in fields(ExportConfig)
            },
        }
        reloaded = load_project_data(serialized)

        self.assertEqual(reloaded.export_config, configured)
        self.assertEqual(
            reloaded.export_config.short_intro_text,
            "  Exact intro  ",
        )

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
                short_intro_text="Configured intro",
                short_intro_duration=0.03,
                short_outro_text="Configured outro",
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

    def test_short_preview_and_render_job_share_safe_profile_and_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            csv_path = root / "browsers.csv"
            rows = ["year,country,value"]
            for year in (2000, 2001):
                rows.extend(
                    f"{year},Browser {index},{1000 - (index * 50) + year}"
                    for index in range(10)
                )
            csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            chart = ChartConfig(
                width=1920,
                height=1080,
                dpi=150,
                frames_dir=str(root / "frames"),
                output_file=str(root / "race.mp4"),
                frame_output_mode="png_sequence",
                max_visible_bars=10,
                bar_vertical_layout_mode="fill_available",
                bar_vertical_top_padding=18,
                bar_vertical_bottom_padding=18,
                title_enabled=False,
                subtitle_enabled=False,
                time_label_font_size=70,
                source_font_size=13,
                logos_enabled=False,
                value_grid_enabled=True,
                fps=30,
                steps_per_transition=2,
            )
            export = ExportConfig(
                mode="short",
                short_from_period=2000,
                short_to_period=2001,
            )
            project_data = {
                "name": "short_parity",
                "chart": {
                    "width": chart.width,
                    "height": chart.height,
                    "dpi": chart.dpi,
                    "frames_dir": chart.frames_dir,
                    "output_file": chart.output_file,
                    "frame_output_mode": chart.frame_output_mode,
                    "max_visible_bars": chart.max_visible_bars,
                    "bar_vertical_layout_mode": chart.bar_vertical_layout_mode,
                    "bar_vertical_top_padding": chart.bar_vertical_top_padding,
                    "bar_vertical_bottom_padding": chart.bar_vertical_bottom_padding,
                    "title_enabled": chart.title_enabled,
                    "subtitle_enabled": chart.subtitle_enabled,
                    "time_label_font_size": chart.time_label_font_size,
                    "source_font_size": chart.source_font_size,
                    "logos_enabled": chart.logos_enabled,
                    "value_grid_enabled": chart.value_grid_enabled,
                    "fps": chart.fps,
                    "steps_per_transition": chart.steps_per_transition,
                },
                "data_source": {
                    "source_type": "csv",
                    "csv_path": str(csv_path),
                    "source_label_override": "Source: browser dataset",
                },
                "dataset": {
                    "year_column": "year",
                    "name_column": "country",
                    "value_column": "value",
                },
                "export": {
                    field.name: getattr(export, field.name)
                    for field in fields(ExportConfig)
                },
            }

            with patch("studio.preview.BarRenderer") as preview_renderer:
                preview_renderer.return_value.render.return_value = str(
                    root / "preview.png"
                )
                render_project_preview(
                    root / "project.json",
                    output_dir=root / "preview",
                    root_dir=root,
                    project_data=project_data,
                    year=2000,
                )
            preview_config = preview_renderer.call_args.kwargs["config"]
            preview_scene = preview_renderer.return_value.render.call_args.args[0]

            with patch("pipeline.render_job.BarRenderer") as render_renderer:
                with patch("pipeline.render_job.VideoExporter"):
                    with patch("builtins.print"):
                        RenderJob(
                            config=chart,
                            data_source_config=DataSourceConfig(
                                source_type="csv",
                                csv_path=str(csv_path),
                                source_label_override="Source: browser dataset",
                            ),
                            dataset_config=DatasetConfig(),
                            export_config=export,
                        ).run()
            render_config = render_renderer.call_args.kwargs["config"]
            render_scene = render_renderer.return_value.render.call_args_list[0].args[0]

            self.assertEqual(
                (preview_config.width, preview_config.height),
                (render_config.width, render_config.height),
            )
            self.assertEqual(
                preview_config.bar_vertical_bottom_padding,
                render_config.bar_vertical_bottom_padding,
            )
            self.assertEqual(
                [(bar.name, bar.y, bar.height) for bar in preview_scene.bars],
                [(bar.name, bar.y, bar.height) for bar in render_scene.bars],
            )

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
