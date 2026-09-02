import unittest
from dataclasses import replace
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import _test_path

from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.fun_fact_config import FunFactConfig
from core.editorial_placement import SmartEditorialPlacementResolver
from core.fun_fact_scheduler import FunFactScheduler
from core.timeline import Timeline
from pipeline.render_job import RenderJob
from studio.preview import render_project_preview
from models.fun_fact import FunFact, FunFactCollection
from config.dataset_config import DatasetConfig
import pandas as pd


def geometry(width=1000, height=600, bars=(), date=None, source=None, logos=()):
    return {
        "canvas": {"x": 0, "y": 0, "width": width, "height": height},
        "safe_area": {"x": 24, "y": 24, "width": width - 48, "height": height - 48},
        "bar_rects": [dict(item) for item in bars],
        "primary_logo_rects": [dict(item) for item in logos],
        "secondary_logo_rects": [],
        "category_lane": {"x": 80, "y": 80, "width": 100, "height": height - 160},
        "ranking_lane": {"x": 30, "y": 80, "width": 50, "height": height - 160},
        "text_bounds": {
            "date": date,
            "source": source,
            "title": None,
            "subtitle": None,
        },
    }


class EditorialSmartPlacementTest(unittest.TestCase):
    def setUp(self):
        self.chart = ChartConfig(width=1000, height=600)
        self.config = FunFactConfig(
            enabled=True,
            layout="editorial_floating",
            editorial_layout_mode="overlay",
            editorial_placement_mode="smart",
            editorial_card_width=300,
            editorial_card_height=180,
            editorial_keep_inside_safe_area=True,
            editorial_protect_top_n=3,
            editorial_bar_clearance=16,
            panel_margin=24,
        )
        self.fact = FunFact("card", "1", "3", "Headline")
        self.scheduler_stub = SimpleNamespace(
            facts=(SimpleNamespace(
                fact=self.fact,
                start_index=0,
                end_index=2,
            ),),
        )

    def resolve(self, frames, config=None):
        return SmartEditorialPlacementResolver.from_geometry(
            self.chart,
            config or self.config,
            self.scheduler_stub,
            {index: frame for index, frame in enumerate(frames)},
        )

    def test_empty_canvas_uses_deterministic_bottom_center_tie_break(self):
        first = self.resolve([geometry()]).decision_for("card")
        second = self.resolve([geometry()]).decision_for("card")
        self.assertEqual(first, second)
        self.assertEqual(first.candidate, "bottom_center")
        self.assertEqual(first.position, (350, 396))
        self.assertFalse(first.used_fallback)

    def test_complete_window_anticipates_a_growing_lower_bar(self):
        early = geometry(bars=({"x": 180, "y": 90, "width": 300, "height": 44},))
        late = geometry(bars=({"x": 180, "y": 430, "width": 720, "height": 60},))
        early_only = self.resolve([early]).decision_for("card")
        complete = self.resolve([early, late]).decision_for("card")
        self.assertEqual(early_only.candidate, "bottom_center")
        self.assertNotEqual(complete.position, early_only.position)

    def test_protect_top_n_uses_rank_order_and_fallback_is_explicit(self):
        full = geometry(bars=(
            {"x": 0, "y": 0, "width": 1000, "height": 600},
            {"x": 0, "y": 0, "width": 1000, "height": 600},
            {"x": 0, "y": 0, "width": 1000, "height": 600},
        ))
        decision = self.resolve([full]).decision_for("card")
        self.assertTrue(decision.used_fallback)
        self.assertGreater(decision.protected_overlap, 0)
        unprotected = self.resolve(
            [full],
            config=replace(self.config, editorial_protect_top_n=0),
        ).decision_for("card")
        self.assertFalse(unprotected.used_fallback)

    def test_clearance_expands_visual_bar_obstacles(self):
        near_bottom = geometry(bars=(
            {"x": 180, "y": 375, "width": 700, "height": 10},
        ))
        zero = self.resolve(
            [near_bottom],
            config=replace(self.config, editorial_bar_clearance=0),
        ).decision_for("card")
        forty = self.resolve(
            [near_bottom],
            config=replace(self.config, editorial_bar_clearance=40),
        ).decision_for("card")
        self.assertEqual(zero.candidate, "bottom_center")
        self.assertNotEqual(forty.position, zero.position)

    def test_date_source_logo_and_value_extension_are_obstacles(self):
        frame = geometry(
            bars=({"x": 180, "y": 120, "width": 480, "height": 44},),
            logos=({"x": 650, "y": 100, "width": 100, "height": 100},),
            date={"x": 330, "y": 390, "width": 340, "height": 100},
            source={"x": 300, "y": 520, "width": 400, "height": 30},
        )
        decision = self.resolve([frame]).decision_for("card")
        self.assertNotEqual(decision.candidate, "bottom_center")

    def test_scheduler_lookup_is_stable_for_random_access_and_sequential_calls(self):
        timeline = Timeline(
            pd.DataFrame({
                "period": [1, 2, 3],
                "category": ["A", "A", "A"],
                "value": [1, 2, 3],
            }),
            config=DatasetConfig(
                year_column="period",
                name_column="category",
                value_column="value",
            ),
        )
        scheduler = FunFactScheduler(
            FunFactCollection(1, (self.fact,), "facts.json"),
            timeline,
        )
        resolver = SmartEditorialPlacementResolver.from_geometry(
            self.chart,
            self.config,
            scheduler,
            {0: geometry(), 1: geometry(), 2: geometry()},
        )
        scheduler.set_placement_resolver(resolver)
        direct = scheduler.active_for_period(2)
        sequential = [scheduler.active_for_period(period) for period in (1, 2, 3)]
        self.assertEqual((direct.resolved_x, direct.resolved_y), (350, 396))
        self.assertEqual(
            {(item.resolved_x, item.resolved_y) for item in sequential},
            {(350, 396)},
        )

    def test_portrait_candidates_use_portrait_safe_geometry(self):
        chart = ChartConfig(width=1080, height=1920)
        config = replace(
            self.config,
            editorial_card_width=700,
            editorial_card_height=420,
        )
        resolver = SmartEditorialPlacementResolver.from_geometry(
            chart,
            config,
            self.scheduler_stub,
            {0: geometry(width=1080, height=1920)},
        )
        x, y = resolver.position_for("card")
        self.assertGreaterEqual(x, 24)
        self.assertGreaterEqual(y, 24)
        self.assertLessEqual(x + 700, 1056)
        self.assertLessEqual(y + 420, 1896)

    def test_preview_and_render_job_share_the_same_smart_position(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "data.csv").write_text(
                "period,category,value\n"
                "1,A,100\n1,B,70\n2,A,140\n2,B,90\n3,A,180\n3,B,120\n",
                encoding="utf-8",
            )
            (root / "facts.json").write_text(json.dumps({
                "version": 1,
                "fun_facts": [{
                    "id": "card",
                    "start": "1",
                    "end": "3",
                    "headline": "Stable card",
                }],
            }), encoding="utf-8")
            chart = ChartConfig(
                width=1000,
                height=600,
                steps_per_transition=3,
                fps=3,
                frames_dir=str(root / "frames"),
                output_file=str(root / "video.mp4"),
                frame_output_mode="png_sequence",
            )
            fun_facts = replace(
                self.config,
                source="facts.json",
            )
            project = {
                "schema_version": 2,
                "name": "smart-parity",
                "chart": {
                    "width": chart.width,
                    "height": chart.height,
                    "steps_per_transition": chart.steps_per_transition,
                    "fps": chart.fps,
                },
                "data_source": {
                    "source_type": "csv",
                    "csv_path": "data.csv",
                },
                "dataset": {
                    "year_column": "period",
                    "name_column": "category",
                    "value_column": "value",
                },
                "fun_facts": {
                    key: value
                    for key, value in fun_facts.__dict__.items()
                    if value is not None
                },
            }
            with patch("studio.preview.BarRenderer") as preview_renderer:
                preview_renderer.return_value.render.return_value = root / "preview.png"
                render_project_preview(
                    "project.json",
                    root_dir=root,
                    project_data=project,
                    year=2,
                )
            preview_fact = preview_renderer.return_value.render.call_args.args[0].fun_fact

            with patch("pipeline.render_job.BarRenderer") as job_renderer, patch(
                "pipeline.render_job.VideoExporter"
            ):
                RenderJob(
                    config=chart,
                    data_source_config=DataSourceConfig(
                        source_type="csv",
                        csv_path=str(root / "data.csv"),
                    ),
                    dataset_config=DatasetConfig(
                        year_column="period",
                        name_column="category",
                        value_column="value",
                    ),
                    fun_fact_config=fun_facts,
                    project_root=root,
                ).run()
            rendered_facts = [
                call.args[0].fun_fact
                for call in job_renderer.return_value.render.call_args_list
                if call.args[0].fun_fact is not None
            ]
        self.assertTrue(rendered_facts)
        expected = (preview_fact.resolved_x, preview_fact.resolved_y)
        self.assertEqual(
            {(item.resolved_x, item.resolved_y) for item in rendered_facts},
            {expected},
        )


if __name__ == "__main__":
    unittest.main()
