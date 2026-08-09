import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from PIL import Image, ImageChops

import _test_path
from config.chart_config import ChartConfig
from config.dataset_config import DatasetConfig
from config.data_source_config import DataSourceConfig
from config.fun_fact_config import FunFactConfig
from config.project_file_loader import ProjectFileError, load_project_data
from core.fun_fact_scheduler import FunFactScheduleError, FunFactScheduler
from core.timeline import Timeline
from models.fun_fact import ActiveFunFact, FunFact, FunFactCollection
from models.scene import Scene
from renderer.bar_renderer import BarRenderer
from pipeline.render_job import RenderJob
from studio.fun_fact_layout import apply_fun_fact_layout
from studio.fun_fact_loader import FunFactFileError, load_fun_fact_collection
from studio.preview import render_project_preview
from studio.project_bundle import build_project_bundle, import_project_bundle
from studio.render_preflight import run_render_preflight
from utils.video_duration import estimate_video_duration


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "fun_facts"


class FunFactSystemTest(unittest.TestCase):
    def test_old_project_loads_with_fun_facts_disabled(self):
        preset = load_project_data({"schema_version": 1, "name": "legacy"})

        self.assertFalse(preset.fun_fact_config.enabled)
        self.assertIsNone(preset.fun_fact_config.source)

    def test_project_loader_accepts_strict_fun_fact_configuration(self):
        preset = load_project_data({
            "schema_version": 2,
            "name": "facts",
            "fun_facts": {
                "enabled": True,
                "source": "fun_facts/facts.json",
                "layout": "right_panel",
                "panel_width": 520,
                "panel_margin": 32,
                "panel_padding": 28,
                "fade_in": 0.2,
                "fade_out": 0.2,
            },
        })

        self.assertTrue(preset.fun_fact_config.enabled)
        self.assertEqual(preset.fun_fact_config.panel_width, 520)

    def test_project_loader_rejects_unknown_fun_fact_configuration(self):
        with self.assertRaisesRegex(ProjectFileError, "Unknown key"):
            load_project_data({
                "schema_version": 2,
                "fun_facts": {"enabled": True, "magic": True},
            })

    def test_legacy_project_preserves_effective_configuration_and_layout(self):
        legacy_data = self._monthly_project_data(enabled=False)
        legacy_data["schema_version"] = 1
        legacy_data.pop("fun_facts")
        current_data = json.loads(json.dumps(legacy_data))
        current_data["schema_version"] = 2
        current_data["fun_facts"] = {
            "enabled": False,
            "layout": "right_panel",
        }

        legacy = load_project_data(legacy_data)
        current = load_project_data(current_data)

        self.assertEqual(legacy.chart_config, current.chart_config)
        self.assertEqual(legacy.data_source_config, current.data_source_config)
        self.assertEqual(legacy.dataset_config, current.dataset_config)
        self.assertEqual(
            apply_fun_fact_layout(legacy.chart_config, legacy.fun_fact_config),
            legacy.chart_config,
        )
        self.assertEqual(
            apply_fun_fact_layout(current.chart_config, current.fun_fact_config),
            current.chart_config,
        )

    def test_disabled_fun_facts_preview_matches_legacy_preview(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_monthly_project(root)
            legacy_data = self._monthly_project_data(enabled=False)
            legacy_data["schema_version"] = 1
            legacy_data.pop("fun_facts")
            current_data = json.loads(json.dumps(legacy_data))
            current_data["schema_version"] = 2
            current_data["fun_facts"] = {
                "enabled": False,
                "layout": "right_panel",
            }

            legacy_path = render_project_preview(
                "legacy.json",
                output_dir="legacy_preview",
                year=2,
                root_dir=root,
                project_data=legacy_data,
            )
            current_path = render_project_preview(
                "current.json",
                output_dir="current_preview",
                year=2,
                root_dir=root,
                project_data=current_data,
            )
            with Image.open(legacy_path).convert("RGBA") as legacy_image, Image.open(
                current_path
            ).convert("RGBA") as current_image:
                difference = ImageChops.difference(legacy_image, current_image)

            self.assertIsNone(difference.getbbox())

    def test_loads_valid_monthly_fixture_and_uses_visible_label(self):
        dataframe = pd.read_csv(FIXTURE_DIR / "monthly.csv")
        timeline = Timeline(dataframe, config=self._monthly_config())
        collection = load_fun_fact_collection(
            "tests/fixtures/fun_facts/monthly_fun_facts.json",
            project_root=Path(__file__).parents[1],
        )
        scheduler = FunFactScheduler(collection, timeline)

        self.assertEqual(timeline.resolve_time_label("2010-05"), 2)
        self.assertIsNone(scheduler.active_for_period(1))
        self.assertEqual(scheduler.active_for_period(2).fact.id, "may_demo")
        self.assertIsNone(scheduler.active_for_period(3))

    def test_annual_timeline_uses_numeric_label_fallback(self):
        timeline = Timeline(pd.DataFrame({
            "year": [2010, 2011, 2012],
            "country": ["A", "A", "A"],
            "value": [1, 2, 3],
        }))
        scheduler = FunFactScheduler(self._collection(
            FunFact("annual", "2011", "2011", "Annual fact")
        ), timeline)

        self.assertEqual(timeline.resolve_time_label("2011"), 2011)
        self.assertEqual(scheduler.active_for_period(2011).fact.id, "annual")

    def test_fade_in_and_fade_out_follow_interpolated_timeline_position(self):
        timeline = self._four_period_timeline()
        scheduler = FunFactScheduler(self._collection(
            FunFact("fade", "2010-04", "2010-06", "Fade fact")
        ), timeline, fade_in=0.2, fade_out=0.2)

        fade_in = scheduler.active_at(1, 2, progress=0.3)
        fade_out = scheduler.active_at(3, 4, progress=0.7)

        self.assertAlmostEqual(fade_in.opacity, 0.5, places=6)
        self.assertAlmostEqual(fade_out.opacity, 0.5, places=6)

    def test_rejects_unresolved_range_and_overlap(self):
        timeline = self._four_period_timeline()
        with self.assertRaisesRegex(FunFactScheduleError, "cannot be resolved"):
            FunFactScheduler(self._collection(
                FunFact("missing", "2019-01", "2019-02", "Missing")
            ), timeline)
        with self.assertRaisesRegex(FunFactScheduleError, "overlap"):
            FunFactScheduler(FunFactCollection(
                version=1,
                source_path="facts.json",
                facts=(
                    FunFact("one", "2010-04", "2010-05", "One"),
                    FunFact("two", "2010-05", "2010-06", "Two"),
                ),
            ), timeline)

    def test_rejects_unresolved_end_and_reversed_range_with_fact_context(self):
        timeline = self._four_period_timeline()
        with self.assertRaisesRegex(
            FunFactScheduleError,
            "reverse.*end.*cannot be resolved",
        ):
            FunFactScheduler(self._collection(
                FunFact("reverse", "2010-04", "2019-02", "Missing end")
            ), timeline)
        with self.assertRaisesRegex(
            FunFactScheduleError,
            "backwards.*start.*after.*end",
        ):
            FunFactScheduler(self._collection(
                FunFact("backwards", "2010-07", "2010-05", "Backwards")
            ), timeline)

    def test_rejects_missing_id_and_headline_with_field_context(self):
        base_fact = {
            "id": "required_fields",
            "start": "1",
            "end": "1",
            "headline": "Required fields",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for field_name in ("id", "headline"):
                with self.subTest(field_name=field_name):
                    fact = dict(base_fact)
                    fact.pop(field_name)
                    path = root / f"missing_{field_name}.json"
                    self._write_json(path, {"version": 1, "fun_facts": [fact]})
                    with self.assertRaisesRegex(
                        FunFactFileError,
                        rf"field '{field_name}'.*non-empty string",
                    ):
                        load_fun_fact_collection(path.name, project_root=root)

    def test_rejects_invalid_fact_layout_and_image_fit(self):
        invalid_fields = {
            "layout": ("floating_panel", "right_panel"),
            "image_fit": ("stretch", "cover.*contain"),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for field_name, (invalid_value, expected) in invalid_fields.items():
                with self.subTest(field_name=field_name):
                    fact = {
                        "id": f"invalid_{field_name}",
                        "start": "1",
                        "end": "1",
                        "headline": "Invalid option",
                        field_name: invalid_value,
                    }
                    path = root / f"invalid_{field_name}.json"
                    self._write_json(path, {"version": 1, "fun_facts": [fact]})
                    with self.assertRaisesRegex(
                        FunFactFileError,
                        rf"invalid_{field_name}.*field '{field_name}'.*{expected}",
                    ):
                        load_fun_fact_collection(path.name, project_root=root)

    def test_rejects_unsupported_image_format_with_fact_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "images" / "animation.gif"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (16, 16), "purple").save(image_path, format="GIF")
            self._write_json(root / "facts.json", {
                "version": 1,
                "fun_facts": [{
                    "id": "unsupported_photo",
                    "start": "1",
                    "end": "1",
                    "headline": "Unsupported photo",
                    "image": "images/animation.gif",
                }],
            })

            with self.assertRaisesRegex(
                FunFactFileError,
                "unsupported_photo.*PNG, JPEG, or WEBP",
            ):
                load_fun_fact_collection("facts.json", project_root=root)

    def test_resolves_relative_source_and_image_from_project_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_monthly_project(root, with_image=True)

            collection = load_fun_fact_collection(
                "fun_facts/facts.json",
                project_root=root,
            )

            self.assertEqual(Path(collection.source_path), root / "fun_facts" / "facts.json")
            self.assertEqual(
                Path(collection.facts[0].image_path),
                root / "fun_facts" / "images" / "photo.jpg",
            )

    def test_rejects_invalid_json_and_missing_image_with_fact_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "invalid.json").write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(FunFactFileError, "Invalid JSON"):
                load_fun_fact_collection("invalid.json", project_root=root)

            self._write_json(root / "missing_image.json", {
                "version": 1,
                "fun_facts": [{
                    "id": "photo_fact",
                    "start": "1",
                    "end": "1",
                    "headline": "Photo",
                    "image": "images/missing.jpg",
                }],
            })
            with self.assertRaisesRegex(FunFactFileError, "photo_fact"):
                load_fun_fact_collection("missing_image.json", project_root=root)

    def test_right_panel_reserves_stable_bar_and_text_space(self):
        chart = ChartConfig(width=1000, left_margin=200, right_margin=100)
        fun_facts = FunFactConfig(
            enabled=True,
            panel_width=260,
            panel_margin=20,
            panel_padding=20,
        )

        adjusted = apply_fun_fact_layout(chart, fun_facts)

        self.assertEqual(adjusted.right_margin, 300)
        self.assertEqual(adjusted.max_bar_width, 500)
        self.assertLess(adjusted.time_label_x, 1000 - 260)
        self.assertEqual(adjusted.value_label_edge_padding, 300)
        self.assertEqual(apply_fun_fact_layout(chart, FunFactConfig()), chart)

    def test_fun_fact_body_color_falls_back_to_readable_contrast(self):
        chart = ChartConfig(
            width=640,
            height=360,
            background_color_override="#07111D",
            subtitle_text_color="#07111D",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            renderer = BarRenderer(
                output_dir=temp_dir,
                config=chart,
                fun_fact_config=FunFactConfig(enabled=True, panel_width=180),
            )
            try:
                background = renderer._fun_fact_panel_background()
                color = renderer._readable_fun_fact_color(
                    background,
                    chart.resolved_subtitle_text_color,
                )
            finally:
                renderer.close()

        ratio = renderer._contrast_ratio(
            tuple(channel / 255 for channel in background[:3]),
            tuple(channel / 255 for channel in color[:3]),
        )
        self.assertGreaterEqual(ratio, 4.5)

    def test_preview_scene_has_no_overlay_then_scheduled_and_forced_overlay(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_monthly_project(root)
            project_data = self._monthly_project_data(enabled=True)

            with patch("studio.preview.BarRenderer") as renderer_class:
                renderer_class.return_value.render.return_value = str(root / "preview.png")
                render_project_preview(
                    "project.json",
                    year=1,
                    root_dir=root,
                    project_data=project_data,
                )
                scene = renderer_class.return_value.render.call_args.args[0]
                self.assertIsNone(scene.fun_fact)

                render_project_preview(
                    "project.json",
                    year=2,
                    root_dir=root,
                    project_data=project_data,
                )
                scene = renderer_class.return_value.render.call_args.args[0]
                self.assertEqual(scene.fun_fact.fact.id, "may_demo")

                render_project_preview(
                    "project.json",
                    year=1,
                    root_dir=root,
                    project_data=project_data,
                    force_fun_fact_id="may_demo",
                )
                scene = renderer_class.return_value.render.call_args.args[0]
                self.assertTrue(scene.fun_fact.forced)

    def test_optional_image_cover_contain_and_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "photo.jpg"
            exif = Image.Exif()
            exif[274] = 6
            Image.new("RGB", (80, 40), "red").save(image_path, exif=exif)
            renderer = BarRenderer(
                output_dir=temp_dir,
                config=ChartConfig(width=640, height=360),
                fun_fact_config=FunFactConfig(enabled=True, panel_width=180),
            )
            try:
                with patch(
                    "renderer.bar_renderer.Image.open",
                    wraps=Image.open,
                ) as open_image:
                    cover = renderer._prepared_fun_fact_image(
                        str(image_path), 120, 120, "cover"
                    )
                    contain = renderer._prepared_fun_fact_image(
                        str(image_path), 120, 120, "contain"
                    )
                    repeated = renderer._prepared_fun_fact_image(
                        str(image_path), 120, 120, "cover"
                    )
                oriented_size = next(iter(renderer._fun_fact_image_cache.values())).size
            finally:
                renderer.close()

        self.assertEqual(cover.size, (120, 120))
        self.assertEqual(contain.size, (120, 120))
        self.assertIs(cover, repeated)
        self.assertEqual(open_image.call_count, 1)
        self.assertEqual(oriented_size, (40, 80))

    def test_monthly_smoke_preview_renders_overlay_png(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_monthly_project(root)
            output = render_project_preview(
                "project.json",
                output_dir="preview",
                year=2,
                root_dir=root,
                project_data=self._monthly_project_data(enabled=True),
            )

            with Image.open(output) as image:
                self.assertEqual(image.size, (640, 360))

    def test_fun_facts_do_not_change_duration_or_frame_count(self):
        without = estimate_video_duration(
            period_count=189,
            steps_per_transition=24,
            fps=24,
            continuous_motion=False,
        )
        with_facts = estimate_video_duration(
            period_count=189,
            steps_per_transition=24,
            fps=24,
            continuous_motion=False,
        )

        self.assertEqual(without.frame_count, with_facts.frame_count)
        self.assertEqual(without.duration_seconds, with_facts.duration_seconds)

    def test_render_job_schedules_overlay_without_adding_frames(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_monthly_project(root)
            chart = ChartConfig(
                width=640,
                height=360,
                left_margin=120,
                right_margin=70,
                top_margin=105,
                bottom_margin=55,
                steps_per_transition=9,
                fps=3,
                frames_dir=str(root / "frames"),
                output_file=str(root / "video.mp4"),
                frame_output_mode="png_sequence",
            )
            with patch("pipeline.render_job.BarRenderer") as renderer_class, patch(
                "pipeline.render_job.VideoExporter"
            ):
                result = RenderJob(
                    config=chart,
                    data_source_config=DataSourceConfig(
                        source_type="csv",
                        csv_path=str(root / "data" / "monthly.csv"),
                    ),
                    dataset_config=self._monthly_config(),
                    fun_fact_config=FunFactConfig(
                        enabled=True,
                        source="fun_facts/facts.json",
                        panel_width=180,
                        panel_margin=10,
                        panel_padding=12,
                    ),
                    project_root=root,
                ).run()

            scenes = [call.args[0] for call in renderer_class.return_value.render.call_args_list]
            active = [scene for scene in scenes if scene.fun_fact is not None]
            expected = estimate_video_duration(
                period_count=3,
                steps_per_transition=9,
                fps=3,
                continuous_motion=False,
            )
            self.assertEqual(result.frames_rendered, expected.frame_count)
            self.assertTrue(active)
            self.assertTrue(all(scene.time_label != "2" for scene in active))
            self.assertGreater(len({repr(scene.bars) for scene in active}), 1)

    def test_bundle_preserves_fun_fact_json_and_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_monthly_project(root, with_image=True)
            project = self._monthly_project_data(enabled=True)
            export = build_project_bundle(project, root_dir=root)
            with zipfile.ZipFile(io.BytesIO(export.data)) as archive:
                names = set(archive.namelist())
                self.assertTrue(any(name.startswith("assets/fun_facts/") for name in names))
                self.assertTrue(any("fun_facts/images" in name for name in names))

            imported = import_project_bundle(export.data, root_dir=root)
            imported_project = json.loads(
                Path(imported.project_path).read_text(encoding="utf-8")
            )
            source = root / imported_project["fun_facts"]["source"]
            imported_facts = json.loads(source.read_text(encoding="utf-8"))
            image = root / imported_facts["fun_facts"][0]["image"]
            self.assertTrue(source.is_file())
            self.assertTrue(image.is_file())

    def test_preflight_reports_enabled_missing_fun_fact_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_monthly_project(root)
            project = self._monthly_project_data(enabled=True)
            project["fun_facts"]["source"] = "fun_facts/missing.json"
            self._write_json(root / "project.json", project)

            result = run_render_preflight(
                "project.json",
                root_dir=root,
                ffmpeg_path="ffmpeg",
            )

        check = next(check for check in result.checks if check.key == "fun_facts")
        self.assertEqual(check.level, "error")
        self.assertIn("fun_facts.source", check.message)

    def test_preflight_surfaces_fact_id_for_invalid_schedule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_monthly_project(root)
            self._write_json(root / "fun_facts" / "facts.json", {
                "version": 1,
                "fun_facts": [{
                    "id": "backwards_schedule",
                    "start": "2010-06",
                    "end": "2010-04",
                    "headline": "Backwards schedule",
                }],
            })
            self._write_json(
                root / "project.json",
                self._monthly_project_data(enabled=True),
            )

            result = run_render_preflight(
                "project.json",
                root_dir=root,
                ffmpeg_path="ffmpeg",
            )

        check = next(check for check in result.checks if check.key == "fun_facts")
        self.assertEqual(check.level, "error")
        self.assertRegex(
            check.message,
            "backwards_schedule.*start.*after.*end",
        )

    @staticmethod
    def _monthly_config():
        return DatasetConfig(
            year_column="period",
            time_label_column="date",
            name_column="category",
            value_column="value",
        )

    @staticmethod
    def _collection(*facts):
        return FunFactCollection(version=1, facts=tuple(facts), source_path="facts.json")

    @classmethod
    def _four_period_timeline(cls):
        return Timeline(pd.DataFrame({
            "period": [1, 2, 3, 4],
            "date": ["2010-04", "2010-05", "2010-06", "2010-07"],
            "category": ["A", "A", "A", "A"],
            "value": [1, 2, 3, 4],
        }), config=cls._monthly_config())

    @staticmethod
    def _write_json(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    @classmethod
    def _write_monthly_project(cls, root, with_image=False):
        (root / "data").mkdir(parents=True, exist_ok=True)
        (root / "data" / "monthly.csv").write_text(
            (FIXTURE_DIR / "monthly.csv").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        fact = {
            "id": "may_demo",
            "start": "2010-05",
            "end": "2010-05",
            "headline": "MAY DEMO FACT",
            "body": "Visible monthly labels drive this overlay.",
            "layout": "right_panel",
            "image_fit": "cover",
        }
        if with_image:
            image_path = root / "fun_facts" / "images" / "photo.jpg"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (80, 40), "blue").save(image_path)
            fact["image"] = "fun_facts/images/photo.jpg"
        cls._write_json(root / "fun_facts" / "facts.json", {
            "version": 1,
            "fun_facts": [fact],
        })

    @staticmethod
    def _monthly_project_data(*, enabled):
        return {
            "schema_version": 2,
            "name": "monthly_demo",
            "chart": {
                "width": 640,
                "height": 360,
                "dpi": 100,
                "left_margin": 120,
                "right_margin": 70,
                "top_margin": 105,
                "bottom_margin": 55,
                "bar_height": 34,
                "bar_gap": 10,
                "title": "Monthly demo",
                "title_x": 30,
                "title_y": 35,
                "subtitle_x": 30,
                "subtitle_y": 70,
                "time_label_x": 580,
                "time_label_y": 315,
                "source_x": 30,
                "source_y": 335,
                "title_font_size": 18,
                "subtitle_font_size": 12,
                "time_label_font_size": 36,
                "source_font_size": 9,
                "label_font_size": 10,
                "value_font_size": 10,
                "rank_label_font_size": 10,
            },
            "data_source": {
                "source_type": "csv",
                "csv_path": "data/monthly.csv",
                "source_label_override": "Source: fixture",
            },
            "dataset": {
                "year_column": "period",
                "time_label_column": "date",
                "name_column": "category",
                "value_column": "value",
            },
            "fun_facts": {
                "enabled": enabled,
                "source": "fun_facts/facts.json",
                "layout": "right_panel",
                "panel_width": 180,
                "panel_margin": 10,
                "panel_padding": 12,
                "fade_in": 0.2,
                "fade_out": 0.2,
            },
        }


if __name__ == "__main__":
    unittest.main()
