import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
import pandas as pd

from config.chart_config import ChartConfig
from config.animation_config import AnimationConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.fun_fact_config import FunFactConfig
from config.project_file_loader import load_project_data
from config.value_format_config import ValueFormatConfig
from core.layout_engine import LayoutEngine
from core.scene_geometry import build_scene_geometry
from core.value_axis import (
    NICE_TICK_FAMILY,
    ValueAxisTracker,
    adaptive_tick_count,
    format_axis_tick,
    nice_ticks,
    scale_bar_sprites,
)
from models.bar_sprite import BarSprite
from models.scene import Scene
from pipeline.render_job import RenderJob
from renderer.bar_renderer import BarRenderer
from studio.preview import render_project_preview
from studio.layout_preview import build_studio_layout_preview
from studio.project_builder import build_project_data, project_form_values


def sprite(name, value, *, width=600, x=200, y=200, opacity=1.0):
    return BarSprite(
        name=name,
        value=value,
        color="#2A78B8",
        x=x,
        y=y,
        width=width,
        height=42,
        opacity=opacity,
    )


class ValueAxisTest(unittest.TestCase):
    def test_value_scale_aligns_bar_endpoint_and_gridline_exactly(self):
        config = self._config(value_grid_mode="static")
        source = [sprite("A", 40_000), sprite("B", 20_000, width=300)]
        tracker = ValueAxisTracker.from_config(config, [source])
        state = tracker.next(source)
        scaled = scale_bar_sprites(source, state.scale)
        tick = next(tick for tick in state.ticks if tick.value == 20_000)
        bar = next(item for item in scaled if item.value == 20_000)

        self.assertAlmostEqual(bar.x + bar.width, tick.x)
        self.assertAlmostEqual(
            bar.width,
            state.scale.width_for_value(bar.value),
        )
        self.assertEqual(state.scale.x_for_value(0), config.left_margin)

    def test_nice_ticks_use_readable_family_for_common_domains(self):
        for domain in (35_000, 45_000, 52_000):
            step, ticks = nice_ticks(domain, 5)
            exponent = math.floor(math.log10(step))
            fraction = step / (10 ** exponent)

            self.assertTrue(any(
                math.isclose(fraction, candidate)
                for candidate in NICE_TICK_FAMILY
            ))
            self.assertEqual(ticks[0], 0.0)
            self.assertTrue(all(
                current > previous
                for previous, current in zip(ticks, ticks[1:])
            ))
            self.assertLessEqual(ticks[-1], domain)

    def test_dynamic_domain_expands_smoothly_and_persistent_tick_moves_left(self):
        config = self._config(
            value_grid_mode="dynamic",
            value_grid_target_tick_count=4,
        )
        tracker = ValueAxisTracker.from_config(
            config,
            [[sprite("A", 35_000)], [sprite("A", 70_000)]],
        )
        first = tracker.next([sprite("A", 35_000)])
        first_tick = next(tick for tick in first.ticks if tick.value == 20_000)
        states = [first]
        for value in range(36_000, 70_001, 2_000):
            states.append(tracker.next([sprite("A", value)]))
        last = states[-1]
        last_tick = next(tick for tick in last.ticks if tick.value == 20_000)

        domains = [state.scale.domain_max for state in states]
        self.assertTrue(all(
            current >= previous
            for previous, current in zip(domains, domains[1:])
        ))
        self.assertTrue(all(
            current - previous < 25_000
            for previous, current in zip(domains, domains[1:])
        ))
        self.assertLess(last_tick.x, first_tick.x)
        self.assertEqual(last_tick.opacity, 1.0)

    def test_contraction_is_slower_than_expansion(self):
        config = self._config(value_grid_mode="dynamic")
        tracker = ValueAxisTracker.from_config(
            config,
            [[sprite("A", 100)], [sprite("A", 200)]],
        )
        initial = tracker.next([sprite("A", 100)])
        expanded = tracker.next([sprite("A", 200)])
        contracted = tracker.next([sprite("A", 100)])

        expansion = expanded.scale.domain_max - initial.scale.domain_max
        contraction = expanded.scale.domain_max - contracted.scale.domain_max
        self.assertGreater(expansion, 0.0)
        self.assertGreater(contraction, 0.0)
        self.assertLess(contraction, expansion)
        self.assertGreater(contracted.scale.domain_max, initial.scale.domain_max)

    def test_tick_changes_fade_by_value_identity(self):
        config = self._config(
            value_grid_mode="dynamic",
            value_grid_target_tick_count=4,
        )
        tracker = ValueAxisTracker.from_config(
            config,
            [[sprite("A", 35_000)], [sprite("A", 70_000)]],
        )
        first = tracker.next([sprite("A", 35_000)])
        second = tracker.next([sprite("A", 70_000)])
        first_by_value = {tick.value: tick for tick in first.ticks}
        second_by_value = {tick.value: tick for tick in second.ticks}

        self.assertEqual(first_by_value[20_000].opacity, 1.0)
        self.assertEqual(second_by_value[20_000].opacity, 1.0)
        self.assertGreater(second_by_value[30_000].opacity, 0.0)
        self.assertLess(second_by_value[30_000].opacity, 1.0)
        self.assertLess(second_by_value[20_000].x, first_by_value[20_000].x)

    def test_static_mode_keeps_domain_and_tick_positions_fixed(self):
        config = self._config(value_grid_mode="static")
        tracker = ValueAxisTracker.from_config(
            config,
            [[sprite("A", 35_000)], [sprite("A", 70_000)]],
        )
        low = tracker.next([sprite("A", 35_000)])
        high = tracker.next([sprite("A", 70_000)])

        self.assertEqual(low.scale.domain_max, high.scale.domain_max)
        self.assertEqual(
            [(tick.value, tick.x) for tick in low.ticks],
            [(tick.value, tick.x) for tick in high.ticks],
        )

    def test_tick_formatter_reuses_project_prefix_and_avoids_noise(self):
        value_format = ValueFormatConfig(
            decimal_places=4,
            prefix="$",
            suffix=" USD",
        )
        self.assertEqual(
            format_axis_tick(20_000, 10_000, value_format),
            "$20,000 USD",
        )

    def test_vertical_ratio_reduces_tick_count_and_both_ratios_render(self):
        landscape_count = adaptive_tick_count(1_400, 8, 16)
        vertical_count = adaptive_tick_count(520, 8, 16)
        self.assertLess(vertical_count, landscape_count)

        for width, height in ((320, 180), (180, 320)):
            config = self._config(
                width=width,
                height=height,
                left_margin=40,
                right_margin=30,
                top_margin=70,
                bottom_margin=30,
                title_enabled=False,
                subtitle_enabled=False,
                source_label_enabled=False,
                time_label_enabled=False,
            )
            bars = [sprite("A", 40_000, width=width - 70, x=40, y=110)]
            tracker = ValueAxisTracker.from_config(config, [bars])
            state = tracker.next(bars)
            labeled_ticks = [tick for tick in state.ticks if tick.label]
            self.assertTrue(all(
                current.x - previous.x
                >= config.value_grid_tick_font_size * 3
                for previous, current in zip(
                    labeled_ticks,
                    labeled_ticks[1:],
                )
            ))
            scene = Scene(
                title="",
                bars=scale_bar_sprites(bars, state.scale),
                value_axis=state,
            )
            renderer = BarRenderer(config=config)
            try:
                rgba = renderer.render_rgba(scene)
            finally:
                renderer.close()
            self.assertEqual(len(rgba), width * height * 4)

    def test_grid_layer_is_behind_bars_text_and_logos(self):
        config = self._config(
            width=640,
            height=360,
            left_margin=120,
            right_margin=80,
            title_enabled=False,
            subtitle_enabled=False,
            source_label_enabled=False,
            time_label_enabled=False,
        )
        bars = [sprite("A", 40_000, width=440, x=120, y=180)]
        state = ValueAxisTracker.from_config(config, [bars]).next(bars)
        scene = Scene(
            title="",
            bars=scale_bar_sprites(bars, state.scale),
            value_axis=state,
        )
        renderer = BarRenderer(config=config)
        try:
            renderer._draw_scene(scene, draw_canvas=True)
            grid_zorder = renderer._value_grid_collection.get_zorder()
            bar_zorder = renderer._gradient_artist.get_zorder()
            tick_zorder = renderer._value_tick_artists[0].get_zorder()
            logo_zorder = renderer._logo_composite_artist.get_zorder()
            text_zorder = renderer._text_foreground_artist.get_zorder()
        finally:
            renderer.close()

        self.assertLess(grid_zorder, bar_zorder)
        self.assertLess(tick_zorder, bar_zorder)
        self.assertLess(grid_zorder, logo_zorder)
        self.assertLess(grid_zorder, text_zorder)

    def test_advanced_bar_track_uses_value_axis_extent(self):
        config = self._config(
            bar_appearance_mode="unified",
            bar_track_enabled=True,
        )
        bars = [sprite("A", 40_000)]
        state = ValueAxisTracker.from_config(config, [bars]).next(bars)
        scene = Scene(
            title="",
            bars=scale_bar_sprites(bars, state.scale),
            value_axis=state,
        )
        renderer = BarRenderer(config=config)
        try:
            renderer._draw_scene(scene, draw_canvas=True)
            track_vertices = (
                renderer._advanced_track_collection.get_paths()[0].vertices
            )
            self.assertAlmostEqual(
                max(track_vertices[:, 0]),
                state.scale.right_x,
            )
        finally:
            renderer.close()

    def test_disabled_grid_is_pixel_identical_when_scene_has_axis_state(self):
        enabled_config = self._config(width=320, height=180)
        disabled_config = self._config(
            width=320,
            height=180,
            value_grid_enabled=False,
        )
        bars = [sprite("A", 40_000, width=200, x=80, y=100)]
        state = ValueAxisTracker.from_config(enabled_config, [bars]).next(bars)
        with_axis = Scene(title="", bars=bars, value_axis=state)
        without_axis = Scene(title="", bars=bars)
        renderer = BarRenderer(config=disabled_config)
        try:
            self.assertEqual(
                renderer.render_rgba(with_axis),
                renderer.render_rgba(without_axis),
            )
        finally:
            renderer.close()

    def test_layout_reserves_tick_lane_and_scene_geometry_is_real(self):
        config = self._config(
            title_y=70,
            title_font_size=32,
            subtitle_y=110,
            subtitle_font_size=20,
            top_margin=120,
        )
        bars = LayoutEngine(config=config).build([
            sprite("A", 40_000),
            sprite("B", 20_000),
        ])
        tracker = ValueAxisTracker.from_config(config, [bars])
        state = tracker.next(bars)
        scene = Scene(
            title="Title",
            subtitle="Period",
            bars=scale_bar_sprites(bars, state.scale),
            value_axis=state,
        )
        geometry = build_scene_geometry(config, FunFactConfig(), scene)

        subtitle_bottom = config.subtitle_y + (
            config.subtitle_font_size * config.dpi / 144.0
        )
        self.assertGreater(state.label_y, subtitle_bottom)
        self.assertEqual(
            geometry["value_axis"]["origin_x"],
            float(config.left_margin),
        )
        self.assertEqual(
            geometry["value_axis"]["ticks"][1]["x"],
            round(state.ticks[1].x, 3),
        )

    def test_text_placement_preview_uses_real_value_axis_geometry(self):
        data = self._project_data(
            steps_per_transition=4,
            value_grid_enabled=True,
            value_grid_mode="dynamic",
        )
        dataframe = pd.DataFrame({
            "year": [2000, 2000, 2001, 2001],
            "country": ["A", "B", "A", "B"],
            "value": [33_000, 18_000, 52_000, 27_000],
        })
        preview = build_studio_layout_preview(
            data,
            dataframe,
            {
                "preview_mode": "transition",
                "year": 2000,
                "transition_progress": 1 / 3,
            },
        )
        geometry = build_scene_geometry(
            preview.chart_config,
            preview.fun_fact_config,
            preview.scene,
        )

        self.assertIsNotNone(preview.scene.value_axis)
        self.assertEqual(
            geometry["value_axis"]["domain_max"],
            round(preview.scene.value_axis.scale.domain_max, 6),
        )
        for bar in preview.scene.bars:
            self.assertAlmostEqual(
                bar.x + bar.width,
                preview.scene.value_axis.scale.x_for_value(bar.value),
            )

    def test_legacy_default_is_off_and_builder_loader_preserve_axis_settings(self):
        self.assertFalse(ChartConfig().value_grid_enabled)
        data = self._project_data(
            value_grid_enabled=True,
            value_grid_mode="static",
            value_grid_tick_labels_enabled=True,
            value_grid_line_color="#123456",
            value_grid_line_opacity=0.4,
            value_grid_line_thickness=2.5,
            value_grid_tick_text_color="#ABCDEF",
            value_grid_tick_text_opacity=0.8,
            value_grid_tick_font_size=18,
            value_grid_tick_font_weight="bold",
            value_grid_tick_font_style="italic",
            value_grid_target_tick_count=6,
        )
        config = load_project_data(data).chart_config
        values = project_form_values(data)

        self.assertTrue(config.value_grid_enabled)
        self.assertEqual(config.value_grid_mode, "static")
        self.assertEqual(config.value_grid_line_thickness, 2.5)
        self.assertEqual(config.value_grid_tick_font_weight, "bold")
        self.assertEqual(values["value_grid_target_tick_count"], 6)

    def test_preview_and_render_job_replay_identical_dynamic_axis(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path = root / "data.csv"
            csv_path.write_text(
                "year,country,value\n"
                "2000,A,33000\n2000,B,18000\n"
                "2001,A,52000\n2001,B,27000\n",
                encoding="utf-8",
            )
            chart = ChartConfig(
                frames_dir=str(root / "frames"),
                output_file=str(root / "video.mp4"),
                frame_output_mode="png_sequence",
                steps_per_transition=4,
                value_grid_enabled=True,
                value_grid_mode="dynamic",
                animation=AnimationConfig(easing="ease_out_cubic"),
            )
            with patch("pipeline.render_job.BarRenderer") as renderer_class:
                with patch("pipeline.render_job.VideoExporter"):
                    with patch("builtins.print"):
                        RenderJob(
                            config=chart,
                            data_source_config=DataSourceConfig(
                                source_type="csv",
                                csv_path=str(csv_path),
                            ),
                            dataset_config=DatasetConfig(),
                        ).run()
            render_scenes = [
                call.args[0]
                for call in renderer_class.return_value.render.call_args_list
            ]

            preview_data = self._project_data(
                csv_path="data.csv",
                steps_per_transition=4,
                value_grid_enabled=True,
                value_grid_mode="dynamic",
            )
            with patch("studio.preview.BarRenderer") as preview_renderer:
                preview_renderer.return_value.render.return_value = str(
                    root / "preview.png"
                )
                render_project_preview(
                    root / "project.json",
                    output_dir=root / "previews",
                    root_dir=root,
                    project_data=preview_data,
                    preview_mode="transition",
                    year=2000,
                    transition_progress=1 / 3,
                )
            preview_scene = preview_renderer.return_value.render.call_args.args[0]
            render_scene = render_scenes[1]
            render_axis = render_scene.value_axis
            preview_axis = preview_scene.value_axis

            self.assertAlmostEqual(
                preview_axis.scale.domain_max,
                render_axis.scale.domain_max,
            )
            self.assertEqual(
                [(tick.value, tick.x, tick.opacity) for tick in preview_axis.ticks],
                [(tick.value, tick.x, tick.opacity) for tick in render_axis.ticks],
            )
            self.assertEqual(
                [(bar.name, bar.value, bar.x, bar.width) for bar in preview_scene.bars],
                [(bar.name, bar.value, bar.x, bar.width) for bar in render_scene.bars],
            )
            for bar in preview_scene.bars:
                self.assertAlmostEqual(
                    bar.x + bar.width,
                    preview_axis.scale.x_for_value(bar.value),
                )

    @staticmethod
    def _config(**overrides):
        defaults = dict(
            width=800,
            height=450,
            dpi=72,
            left_margin=200,
            right_margin=100,
            top_margin=180,
            bottom_margin=60,
            value_grid_enabled=True,
            value_grid_mode="dynamic",
            value_grid_target_tick_count=5,
            value_format=ValueFormatConfig(decimal_places=0),
        )
        defaults.update(overrides)
        return ChartConfig(**defaults)

    @staticmethod
    def _project_data(**overrides):
        defaults = dict(
            name="value_axis",
            csv_path="data.csv",
            year_column="year",
            name_column="country",
            value_column="value",
            title="Value axis",
            source_label="Source",
            output_file="output.mp4",
            frames_dir="frames",
            layout_preset="youtube_1080p",
            theme="clean_report",
            typography_preset="studio",
            value_format="integer",
            fps=30,
            steps_per_transition=30,
            top_n=5,
            max_visible_bars=5,
        )
        defaults.update(overrides)
        return build_project_data(**defaults)


if __name__ == "__main__":
    unittest.main()
