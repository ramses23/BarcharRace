import unittest
from dataclasses import replace
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import _test_path

from config.chart_config import ChartConfig
from config.animation_config import AnimationConfig
from config.data_source_config import DataSourceConfig
from config.fun_fact_config import FunFactConfig
from core.bar_text_geometry import resolve_value_text_geometry
from core.bar_value_scale import BarValueScaleResolver
from core.editorial_placement import (
    SmartEditorialPlacementResolver,
    _effective_frame_geometry,
    build_smart_editorial_placement_resolver,
)
from core.fun_fact_scheduler import FunFactScheduler
from core.scene_geometry import build_scene_geometry
from core.timeline import Timeline
from pipeline.render_job import RenderJob
from studio.preview import render_project_preview
from models.fun_fact import FunFact, FunFactCollection
from models.bar_sprite import BarSprite
from models.scene import Scene
from config.dataset_config import DatasetConfig
from config.value_format_config import ValueFormatConfig
from renderer.bar_renderer import BarRenderer
from utils.value_formatter import format_value
from utils.text_fit import measurement_font
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

    def _full_window_fixture(self, *, rank_duration=1.0, steps=9):
        timeline = Timeline(
            pd.DataFrame({
                "period": [1, 2],
                "category": ["A", "A"],
                "value": [100, 100],
            }),
            config=DatasetConfig(
                year_column="period",
                name_column="category",
                value_column="value",
            ),
        )
        fact = FunFact("card", "1", "2", "Crossing")
        scheduler = FunFactScheduler(
            FunFactCollection(1, (fact,), "facts.json"),
            timeline,
        )
        chart = ChartConfig(
            width=1000,
            height=600,
            left_margin=180,
            right_margin=80,
            steps_per_transition=steps,
            animation=AnimationConfig(
                rank_movement_duration=rank_duration,
            ),
            value_labels_enabled=False,
            category_labels_enabled=False,
            logos_enabled=False,
        )
        config = replace(
            self.config,
            editorial_card_width=240,
            editorial_card_height=120,
            editorial_protect_top_n=1,
            editorial_bar_clearance=0,
        )
        sprites = {
            1: [BarSprite(
                "A", 100, "#123456", 180, 36, 390, 32,
                rank=1, bar_available_width=390,
            )],
            2: [BarSprite(
                "A", 100, "#123456", 180, 456, 390, 32,
                rank=1, bar_available_width=390,
            )],
        }
        return chart, config, scheduler, sprites

    def test_full_effective_window_detects_crossing_missed_by_checkpoints(self):
        chart, config, scheduler, sprites = self._full_window_fixture()
        scale = BarValueScaleResolver.from_config(chart, sprites.values())
        full_geometry = _effective_frame_geometry(
            chart_config=chart,
            fun_fact_config=config,
            scheduler=scheduler,
            periods=(1, 2),
            sprites_by_period=sprites,
            source_label="",
            calendar_resolver=None,
            scale_resolver=scale,
        )
        endpoint_geometry = {
            key: value
            for key, value in full_geometry.items()
            if key[0] in (0, chart.steps_per_transition - 1)
        }
        checkpoint_only = SmartEditorialPlacementResolver.from_geometry(
            chart, config, scheduler, endpoint_geometry,
        ).decision_for("card")
        complete = build_smart_editorial_placement_resolver(
            chart_config=chart,
            fun_fact_config=config,
            scheduler=scheduler,
            periods=(1, 2),
            sprites_by_period=sprites,
            source_label="",
        )
        self.assertEqual(checkpoint_only.candidate, "center")
        self.assertEqual(complete.decision_for("card").candidate, "bottom_right")
        self.assertEqual(complete.decision_for("card").protected_overlap, 0)
        self.assertEqual(complete.precompute_stats["frames_analyzed"], 9)
        self.assertEqual(complete.precompute_stats["frames_by_card"]["card"], 9)

    def test_rank_duration_and_rank_motion_are_present_in_frame_obstacles(self):
        arrival_frames = {}
        for duration in (1.0, 0.7, 0.5):
            chart, config, scheduler, sprites = self._full_window_fixture(
                rank_duration=duration,
                steps=11,
            )
            sprites[1][0].rank = 2
            sprites[2][0].rank = 1
            geometry = _effective_frame_geometry(
                chart_config=chart,
                fun_fact_config=config,
                scheduler=scheduler,
                periods=(1, 2),
                sprites_by_period=sprites,
                source_label="",
                calendar_resolver=None,
                scale_resolver=BarValueScaleResolver.from_config(
                    chart, sprites.values()
                ),
            )
            centers = [
                item["bar_obstacles"][0]["bar"]["y"]
                + (item["bar_obstacles"][0]["bar"]["height"] / 2)
                for item in geometry.values()
            ]
            arrival_frames[duration] = next(
                index for index, center in enumerate(centers)
                if abs(center - 456) < 1e-6
            )
            heights = [
                item["bar_obstacles"][0]["bar"]["height"]
                for item in geometry.values()
            ]
            self.assertGreater(max(heights), 32)
        self.assertEqual(arrival_frames, {1.0: 10, 0.7: 7, 0.5: 5})

    def test_protect_top_n_uses_each_interpolated_frames_rank_positions(self):
        frame = geometry(bars=())
        frame["bar_obstacles"] = [
            {
                "rank": rank,
                "opacity": 1.0,
                "bar": {"x": 180, "y": y, "width": 600, "height": 40},
                "category_text": None,
                "value_text": None,
                "primary_logos": [],
                "secondary_logos": [],
            }
            for rank, y in ((1, 40), (2, 180), (3, 460), (4, 320))
        ]
        top_one = self.resolve(
            [frame],
            config=replace(
                self.config,
                editorial_card_width=240,
                editorial_card_height=120,
                editorial_protect_top_n=1,
                editorial_bar_clearance=0,
            ),
        ).decision_for("card")
        top_three = self.resolve(
            [frame],
            config=replace(
                self.config,
                editorial_card_width=240,
                editorial_card_height=120,
                editorial_protect_top_n=3,
                editorial_bar_clearance=0,
            ),
        ).decision_for("card")
        self.assertEqual(top_one.protected_overlap, 0)
        self.assertEqual(top_three.protected_overlap, 0)
        self.assertNotEqual(top_one.position, top_three.position)

    def test_scene_and_renderer_share_real_value_text_geometry(self):
        config = ChartConfig(
            width=1400,
            height=700,
            left_margin=180,
            value_font_size=20,
            value_font_weight="bold",
            value_font_style="italic",
            bar_appearance_mode="unified",
            bar_value_position="outside",
            bar_value_border_enabled=True,
            bar_value_border_width=2,
            bar_value_shadow_enabled=True,
            bar_value_shadow_offset_x=3,
            bar_value_shadow_offset_y=-2,
            logos_enabled=False,
        )
        sprite = BarSprite(
            "A", 1_059_749_516, "#123456", 180, 260, 500, 54,
            rank=1, bar_available_width=900,
        )
        scene_geometry = build_scene_geometry(
            config,
            FunFactConfig(enabled=False),
            Scene(title="", bars=[sprite]),
        )
        exposed = scene_geometry["value_text_geometries"][0]
        renderer = BarRenderer(config=config)
        renderer_layout = renderer._value_label_layout(
            sprite,
            format_value(sprite.value, config.value_format),
        )
        self.assertEqual(exposed["text"], renderer_layout["text"])
        self.assertEqual(exposed["x"], renderer_layout["x"])
        self.assertEqual(exposed["ha"], renderer_layout["ha"])
        self.assertGreater(exposed["rect"]["width"], 160)
        command = renderer._text_command(
            renderer_layout["text"],
            renderer_layout["x"],
            renderer_layout.get("y", sprite.y),
            ha=renderer_layout["ha"],
            va=renderer_layout.get("va", "center"),
            font_size=config.value_font_size,
            font_family=config.value_font_family,
            font_weight=config.value_font_weight,
            font_style=config.value_font_style,
            color=renderer_layout["color"],
            stroke_width=config.bar_value_border_width,
            stroke_color=config.bar_value_border_color,
            shadow_offset=(
                config.bar_value_shadow_offset_x,
                config.bar_value_shadow_offset_y,
            ),
            shadow_color=config.bar_value_shadow_color,
            shadow_opacity=0.72,
        )
        self.assertEqual(exposed["rect"]["x"], command[1])
        self.assertEqual(exposed["rect"]["y"], command[2])
        self.assertEqual(exposed["rect"]["width"], command[0].shape[1])
        self.assertEqual(exposed["rect"]["height"], command[0].shape[0])

    def test_short_range_uses_only_selected_effective_frames_and_stable_lookup(self):
        timeline = Timeline(
            pd.DataFrame({
                "period": [1, 2, 3, 4],
                "category": ["A"] * 4,
                "value": [80, 100, 90, 120],
            }),
            config=DatasetConfig(
                year_column="period",
                name_column="category",
                value_column="value",
            ),
        )
        scheduler = FunFactScheduler(
            FunFactCollection(
                1,
                (FunFact("short-card", "2", "3", "Short crossing"),),
                "facts.json",
            ),
            timeline,
        )
        chart = ChartConfig(
            width=1080,
            height=1920,
            left_margin=180,
            right_margin=80,
            steps_per_transition=7,
            bar_appearance_mode="unified",
            bar_value_position="outside",
            value_format=ValueFormatConfig(decimal_places=1),
            logos_enabled=False,
        )
        sprites = {
            period: [BarSprite(
                "A", value, "#123456", 180, y, width, 54,
                rank=1, bar_available_width=700,
            )]
            for period, value, y, width in (
                (1, 80, 140, 320),
                (2, 100, 260, 500),
                (3, 90, 1420, 450),
                (4, 120, 1700, 600),
            )
        }
        config = replace(
            self.config,
            editorial_card_width=360,
            editorial_card_height=220,
            editorial_protect_top_n=1,
        )
        resolver = build_smart_editorial_placement_resolver(
            chart_config=chart,
            fun_fact_config=config,
            scheduler=scheduler,
            periods=(2, 3),
            sprites_by_period=sprites,
            source_label="",
        )
        decision = resolver.decision_for("short-card")
        self.assertEqual(resolver.precompute_stats["frames_analyzed"], 7)
        self.assertEqual(resolver.precompute_stats["frames_by_card"]["short-card"], 7)
        self.assertIsNotNone(decision)
        active = scheduler.force("short-card")
        self.assertEqual((active.resolved_x, active.resolved_y), decision.position)
        self.assertEqual(
            {resolver.position_for("short-card") for _ in range(3)},
            {decision.position},
        )
        self.assertGreaterEqual(decision.position[0], 0)
        self.assertGreaterEqual(decision.position[1], 0)
        self.assertLessEqual(
            decision.position[0] + config.editorial_card_width, chart.width,
        )
        self.assertLessEqual(
            decision.position[1] + config.editorial_card_height, chart.height,
        )

    def test_real_value_bbox_respects_full_compact_font_and_size(self):
        sprite = BarSprite(
            "A", 1_059_749_516, "#123456", 180, 260, 300, 54,
            rank=1,
        )
        full_config = ChartConfig(
            width=1600,
            value_font_size=20,
            value_format=ValueFormatConfig(decimal_places=1),
            logos_enabled=False,
        )
        compact_config = replace(
            full_config,
            value_format=ValueFormatConfig(decimal_places=1, compact=True),
        )
        full_text = format_value(sprite.value, full_config.value_format)
        compact_text = format_value(sprite.value, compact_config.value_format)
        full = resolve_value_text_geometry(full_config, sprite, full_text)
        compact = resolve_value_text_geometry(compact_config, sprite, compact_text)
        bold = resolve_value_text_geometry(
            replace(full_config, value_font_weight="bold"), sprite, full_text,
        )
        italic = resolve_value_text_geometry(
            replace(full_config, value_font_style="italic"), sprite, full_text,
        )
        large = resolve_value_text_geometry(
            replace(full_config, value_font_size=32), sprite, full_text,
        )
        self.assertEqual((full.text, compact.text), ("1,059,749,516.0", "1.1B"))
        self.assertGreater(full.width, 160)
        self.assertLess(compact.width, full.width)
        self.assertNotEqual(bold.width, full.width)
        self.assertNotEqual(
            measurement_font(
                full_config.value_font_size,
                full_config.dpi,
                full_config.value_font_family,
                full_config.value_font_weight,
                "normal",
            ).path,
            measurement_font(
                full_config.value_font_size,
                full_config.dpi,
                full_config.value_font_family,
                full_config.value_font_weight,
                "italic",
            ).path,
        )
        self.assertGreater(large.width, full.width)

    def test_real_value_bbox_follows_inside_above_and_logo_aware_outside(self):
        sprite = BarSprite("A", 1_000_000, "#123456", 180, 260, 300, 54)
        base = ChartConfig(
            width=1400,
            bar_appearance_mode="unified",
            value_font_size=20,
            logos_enabled=False,
        )
        text = format_value(sprite.value, base.value_format)
        inside = resolve_value_text_geometry(
            replace(base, bar_value_position="inside"), sprite, text,
        )
        above = resolve_value_text_geometry(
            replace(base, bar_value_position="above"), sprite, text,
        )
        outside = resolve_value_text_geometry(
            replace(base, bar_value_position="outside"),
            sprite,
            text,
            inside_right_logo_extent=(430, 540),
        )
        self.assertEqual(inside.horizontal_alignment, "right")
        self.assertEqual(above.vertical_alignment, "bottom")
        self.assertGreaterEqual(outside.x, 540 + base.logo_label_gap)

    def test_invisible_value_text_is_not_an_obstacle(self):
        config = ChartConfig(value_text_opacity=0.0, logos_enabled=False)
        sprite = BarSprite("A", 1_000_000, "#123456", 180, 260, 300, 54)
        result = build_scene_geometry(
            config,
            FunFactConfig(enabled=False),
            Scene(title="", bars=[sprite]),
        )
        self.assertIsNone(result["value_text_geometries"][0])
        self.assertIsNone(result["bar_obstacles"][0]["value_text"])

    def test_real_long_value_rejects_candidate_old_160_width_would_accept(self):
        config = replace(
            self.config,
            editorial_bar_clearance=0,
            editorial_protect_top_n=1,
        )

        def value_frame(width):
            frame = geometry(
                source={"x": 300, "y": 430, "width": 400, "height": 120},
            )
            frame["bar_obstacles"] = [{
                "rank": 1,
                "opacity": 1.0,
                "bar": {"x": 50, "y": 50, "width": 100, "height": 30},
                "category_text": None,
                "value_text": {"x": 10, "y": 180, "width": width, "height": 40},
                "primary_logos": [],
                "secondary_logos": [],
            }]
            return frame

        old_fixed = self.resolve([value_frame(160)], config=config).decision_for("card")
        real_bbox = self.resolve([value_frame(349)], config=config).decision_for("card")
        self.assertEqual(old_fixed.candidate, "center")
        self.assertEqual(real_bbox.candidate, "middle_right")
        self.assertEqual(real_bbox.protected_overlap, 0)

    def test_effective_frames_include_horizontal_growth_and_logo_geometry(self):
        chart, config, scheduler, sprites = self._full_window_fixture(steps=5)
        with tempfile.TemporaryDirectory() as temp_dir:
            logo = Path(temp_dir) / "logo.png"
            from PIL import Image
            Image.new("RGBA", (24, 24), (255, 0, 0, 255)).save(logo)
            chart = replace(
                chart,
                logos_enabled=True,
                bar_logo_position="inside_right",
                logo_size=50,
                primary_logo_min_size=12,
            )
            sprites[1][0].value = 20
            sprites[1][0].width = 100
            sprites[1][0].logo_path = str(logo)
            sprites[2][0].value = 100
            sprites[2][0].width = 500
            sprites[2][0].logo_path = str(logo)
            geometry_by_frame = _effective_frame_geometry(
                chart_config=chart,
                fun_fact_config=config,
                scheduler=scheduler,
                periods=(1, 2),
                sprites_by_period=sprites,
                source_label="",
                calendar_resolver=None,
                scale_resolver=BarValueScaleResolver.from_config(
                    chart, sprites.values()
                ),
            )
        widths = [
            frame["bar_obstacles"][0]["bar"]["width"]
            for frame in geometry_by_frame.values()
        ]
        self.assertEqual(len(widths), 5)
        self.assertTrue(all(a < b for a, b in zip(widths, widths[1:])))
        self.assertTrue(all(
            frame["bar_obstacles"][0]["primary_logos"]
            for frame in geometry_by_frame.values()
        ))

    def test_entity_entering_protected_rank_is_seen_mid_transition(self):
        chart, config, scheduler, sprites = self._full_window_fixture(steps=5)
        sprites[1].append(BarSprite(
            "B", 90, "#654321", 180, 456, 450, 32,
            rank=2, bar_available_width=500,
        ))
        sprites[2].append(BarSprite(
            "B", 110, "#654321", 180, 36, 500, 32,
            rank=1, bar_available_width=500,
        ))
        sprites[1][0].rank = 1
        sprites[2][0].rank = 2
        geometry_by_frame = _effective_frame_geometry(
            chart_config=chart,
            fun_fact_config=config,
            scheduler=scheduler,
            periods=(1, 2),
            sprites_by_period=sprites,
            source_label="",
            calendar_resolver=None,
            scale_resolver=BarValueScaleResolver.from_config(
                chart, sprites.values()
            ),
        )
        protected_names = []
        for frame in geometry_by_frame.values():
            visible = frame["bar_obstacles"]
            protected_names.append(min(visible, key=lambda item: item["rank"])["name"])
        self.assertEqual(protected_names[0], "A")
        self.assertEqual(protected_names[-1], "B")
        self.assertIn("B", protected_names[1:-1])


if __name__ == "__main__":
    unittest.main()
