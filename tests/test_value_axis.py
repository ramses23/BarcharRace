import math
import tempfile
import unittest
from dataclasses import replace
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
from core.bar_value_scale import BarValueScaleResolver, scale_bar_sprites
from core.scene_geometry import build_scene_geometry
from core.value_axis import (
    NICE_TICK_FAMILY,
    ValueAxisTracker,
    adaptive_tick_count,
    format_axis_tick,
    nice_ticks,
)
from models.bar_sprite import BarSprite
from models.fun_fact import ActiveFunFact, FunFact
from models.scene import Scene
from models.value_axis import SemanticDataScale
from pipeline.render_job import RenderJob
from renderer.bar_renderer import BarRenderer
from studio.preview import render_project_preview
from studio.layout_preview import build_studio_layout_preview
from studio.project_builder import build_project_data, project_form_values
from utils.text_fit import measure_text_width, measurement_font


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
    def test_vertical_frame_is_structural_while_leader_and_rank_motion_change(self):
        for width, height, top_margin, bottom_margin in (
            (1920, 1080, 260, 140),
            (1080, 1920, 330, 180),
        ):
            for mode in ("dynamic", "static"):
                for rank_motion_strength in (1.0, 0.7, 0.5):
                    config = self._config(
                        width=width,
                        height=height,
                        top_margin=top_margin,
                        bottom_margin=bottom_margin,
                        value_grid_mode=mode,
                    )
                    before = [
                        sprite("A", 100, width=600, y=320),
                        sprite("B", 80, width=480, y=410),
                    ]
                    crossing = [
                        replace(
                            before[0],
                            value=90,
                            width=520,
                            y=410.375,
                            height=42 - (6 * rank_motion_strength),
                        ),
                        replace(
                            before[1],
                            value=300,
                            width=650,
                            y=320.625,
                            height=42 + (6 * rank_motion_strength),
                        ),
                    ]
                    after = [
                        replace(crossing[1], y=320, height=42),
                        replace(crossing[0], y=410, height=42),
                    ]
                    tracker = ValueAxisTracker.from_config(
                        config, [before, crossing, after]
                    )
                    states = [tracker.next(frame) for frame in (before, crossing, after)]

                    vertical_frames = {
                        (state.line_top, state.line_bottom, state.label_y)
                        for state in states
                    }
                    self.assertEqual(len(vertical_frames), 1)
                    if mode == "dynamic":
                        before_ticks = {tick.value: tick.x for tick in states[0].ticks}
                        crossing_ticks = {tick.value: tick.x for tick in states[1].ticks}
                        shared = set(before_ticks) & set(crossing_ticks) - {0.0}
                        self.assertTrue(shared)
                        self.assertTrue(any(
                            before_ticks[value] != crossing_ticks[value]
                            for value in shared
                        ))
                        self.assertNotEqual(
                            states[0].scale.domain_max,
                            states[1].scale.domain_max,
                        )

    def test_progressive_dynamic_grid_uses_current_leader_semantic_scale(self):
        config = self._config(
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        bars = [
            sprite("China", 1_370_000_000, width=600),
            sprite("India", 1_280_000_000, width=560, y=260),
        ]
        state = ValueAxisTracker.from_config(config, [bars]).next(bars)
        ticks = {tick.value: tick for tick in state.ticks}

        self.assertIsInstance(state.scale, SemanticDataScale)
        self.assertEqual(state.scale.domain_max, 1_370_000_000)
        self.assertEqual(state.scale.width, 600)
        self.assertAlmostEqual(
            ticks[500_000_000].x,
            config.left_margin + (600 * 500 / 1_370),
        )
        self.assertAlmostEqual(
            ticks[1_000_000_000].x,
            config.left_margin + (600 * 1_000 / 1_370),
        )
        self.assertNotIn(1_500_000_000, ticks)
        self.assertNotIn(2_000_000_000, ticks)
        self.assertGreater(
            state.scale.x_for_value(2_000_000_000),
            state.scale.right_x,
        )

    def test_population_2026_semantic_positions_and_hidden_upper_ticks(self):
        config = self._config(
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        leader = 1_476_625_571
        bars = [
            sprite("India", leader, width=600),
            sprite("China", 1_412_914_090, width=574, y=260),
        ]
        state = ValueAxisTracker.from_config(config, [bars]).next(bars)
        ticks = {tick.value: tick for tick in state.ticks}

        for value, ratio in (
            (500_000_000, 500_000_000 / leader),
            (1_000_000_000, 1_000_000_000 / leader),
            (1_250_000_000, 1_250_000_000 / leader),
        ):
            self.assertAlmostEqual(
                state.scale.x_for_value(value),
                config.left_margin + (600 * ratio),
            )
        self.assertTrue(all(value <= leader for value in ticks))
        self.assertNotIn(1_500_000_000, ticks)
        self.assertNotIn(2_000_000_000, ticks)

    def test_grid_and_bars_align_after_target_but_not_during_reveal(self):
        config = self._config(
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        bars = [
            sprite("Leader", 1_000_000_000, width=600),
            sprite("Half", 500_000_000, width=300, y=260),
        ]
        tracker = ValueAxisTracker.from_config(config, [bars])
        grid = tracker.next(bars)
        resolver = BarValueScaleResolver.from_config(config, [bars, bars])
        full = resolver.for_sprites(bars, timeline_progress=0.5)
        reveal = resolver.for_sprites(bars, timeline_progress=0.25)

        for value in (250_000_000, 500_000_000, 1_000_000_000):
            self.assertAlmostEqual(
                grid.scale.x_for_value(value),
                full.x_for_value(value),
            )
        self.assertEqual(reveal.leader_occupancy, 0.5)
        self.assertGreater(
            grid.scale.x_for_value(500_000_000),
            reveal.x_for_value(500_000_000),
        )

    def test_start_zero_keeps_full_semantic_grid_with_zero_bar_bodies(self):
        config = self._config(
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        bars = [
            sprite("Leader", 1_000_000_000, width=600),
            sprite("Half", 500_000_000, width=300, y=260),
        ]
        grid = ValueAxisTracker.from_config(config, [bars]).next(bars)
        resolver = BarValueScaleResolver.from_config(config, [bars, bars])
        first_scale = resolver.for_sprites(bars, timeline_progress=0.0)
        first_bars = scale_bar_sprites(bars, first_scale)

        self.assertEqual([bar.width for bar in first_bars], [0.0, 0.0])
        self.assertGreater(grid.scale.x_for_value(500_000_000), config.left_margin)
        self.assertEqual(
            grid.scale.x_for_value(1_000_000_000),
            grid.scale.right_x,
        )

    def test_progressive_dynamic_direction_follows_interpolated_leader(self):
        config = self._config(
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        tracker = ValueAxisTracker.from_config(
            config,
            [[sprite("Leader", 1_000_000_000)]],
        )
        initial = tracker.next([sprite("Leader", 1_000_000_000)])
        rising = tracker.next([sprite("Leader", 1_250_000_000)])
        falling = tracker.next([sprite("Leader", 1_100_000_000)])
        initial_x = {tick.value: tick.x for tick in initial.ticks}
        rising_x = {tick.value: tick.x for tick in rising.ticks}
        falling_x = {tick.value: tick.x for tick in falling.ticks}

        self.assertLess(rising_x[1_000_000_000], initial_x[1_000_000_000])
        self.assertGreater(falling_x[1_000_000_000], rising_x[1_000_000_000])

    def test_progressive_tick_identity_fades_at_semantic_positions(self):
        config = self._config(
            value_grid_target_tick_count=5,
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        tracker = ValueAxisTracker.from_config(
            config,
            [[sprite("Leader", 1_000_000_000)]],
        )
        tracker.next([sprite("Leader", 1_000_000_000)])
        changed = tracker.next([sprite("Leader", 1_370_000_000)])
        by_value = {tick.value: tick for tick in changed.ticks}

        self.assertGreater(by_value[500_000_000].opacity, 0.0)
        self.assertLess(by_value[500_000_000].opacity, 1.0)
        self.assertAlmostEqual(
            by_value[500_000_000].x,
            changed.scale.x_for_value(500_000_000),
        )

    def test_grid_style_changes_do_not_change_progressive_bar_geometry(self):
        bars = [
            sprite("Leader", 100, width=600),
            sprite("Other", 75, width=450, y=260),
        ]
        scales = []
        for target, opacity, tick_format in (
            (3, 0.1, "full"),
            (10, 0.9, "compact"),
        ):
            config = self._config(
                start_bars_at_zero=True,
                leader_full_width_point=0.5,
                value_grid_target_tick_count=target,
                value_grid_line_opacity=opacity,
                value_grid_tick_value_format=tick_format,
            )
            ValueAxisTracker.from_config(config, [bars]).next(bars)
            scales.append(
                BarValueScaleResolver.from_config(config, [bars, bars])
                .for_sprites(bars, timeline_progress=0.75)
            )

        self.assertEqual(scales[0], scales[1])
        self.assertEqual(
            [scales[0].width_for_value(value) for value in (100, 75)],
            [600, 450],
        )

    def test_static_grid_and_stable_bar_scale_are_both_value_monotone(self):
        config = self._config(value_grid_mode="static")
        source = [sprite("A", 40_000), sprite("B", 20_000, width=300)]
        tracker = ValueAxisTracker.from_config(config, [source])
        state = tracker.next(source)
        bar_scale = BarValueScaleResolver.from_config(
            config, [source]
        ).for_sprites(source)
        scaled = scale_bar_sprites(source, bar_scale)
        tick = next(tick for tick in state.ticks if tick.value == 20_000)
        bar = next(item for item in scaled if item.value == 20_000)

        self.assertGreater(bar.x + bar.width, bar.x)
        self.assertGreater(tick.x, state.scale.origin_x)
        self.assertAlmostEqual(
            bar.width,
            bar_scale.width_for_value(bar.value),
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

    def test_dynamic_rising_visible_max_never_moves_persistent_ticks_right(self):
        config = self._browser_config(value_grid_mode="dynamic")
        tracker = ValueAxisTracker.from_config(config, [[
            sprite("Firefox", 1_590_915_078, width=1444),
            sprite("Chrome", 1_500_000_000, width=1362),
        ]])
        states = [
            tracker.next([
                sprite("Firefox", 1_590_915_078, width=1444),
                sprite("Chrome", 1_500_000_000, width=1362),
            ]),
            tracker.next([
                sprite("Chrome", 1_592_032_263, width=1453),
                sprite("Firefox", 1_580_000_000, width=1401),
            ]),
            tracker.next([
                sprite("Chrome", 1_610_259_340, width=1462),
                sprite("Firefox", 1_570_000_000, width=1388),
            ]),
        ]

        for previous, current in zip(states, states[1:]):
            previous_ticks = {tick.value: tick.x for tick in previous.ticks}
            persistent = [
                tick
                for tick in current.ticks
                if tick.value > 0 and tick.value in previous_ticks
            ]
            self.assertTrue(persistent)
            self.assertTrue(all(
                tick.x <= previous_ticks[tick.value] + 1e-9
                for tick in persistent
            ))

    def test_dynamic_equal_visible_max_never_moves_persistent_ticks_right(self):
        config = self._config(value_grid_mode="dynamic")
        tracker = ValueAxisTracker.from_config(
            config,
            [[sprite("A", 100, width=300)]],
        )
        first = tracker.next([sprite("A", 100, width=300)])
        second = tracker.next([sprite("A", 100, width=450)])
        first_ticks = {tick.value: tick.x for tick in first.ticks}
        persistent = [
            tick
            for tick in second.ticks
            if tick.value > 0 and tick.value in first_ticks
        ]

        self.assertTrue(persistent)
        self.assertTrue(all(
            tick.x <= first_ticks[tick.value] + 1e-9
            for tick in persistent
        ))

    def test_dynamic_falling_real_max_allows_smooth_rightward_ticks(self):
        config = self._browser_config(value_grid_mode="dynamic")
        tracker = ValueAxisTracker.from_config(
            config,
            [[sprite("Chrome", 898_849_333, width=1256)]],
        )
        september = tracker.next([
            sprite("Chrome", 898_849_333, width=1256),
        ])
        october = tracker.next([
            sprite("Chrome", 880_537_500, width=1256),
        ])
        september_ticks = {tick.value: tick.x for tick in september.ticks}
        persistent = [
            tick
            for tick in october.ticks
            if tick.value > 0 and tick.value in september_ticks
        ]

        self.assertLess(october.scale.domain_max, september.scale.domain_max)
        self.assertTrue(persistent)
        self.assertTrue(all(
            tick.x > september_ticks[tick.value]
            for tick in persistent
        ))

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

    def test_static_mode_keeps_domain_fixed_and_uses_current_frame_width(self):
        config = self._config(value_grid_mode="static")
        tracker = ValueAxisTracker.from_config(
            config,
            [[sprite("A", 35_000)], [sprite("A", 70_000)]],
        )
        low = tracker.next([sprite("A", 35_000, width=600)])
        high = tracker.next([sprite("A", 70_000, width=300)])

        self.assertEqual(low.scale.domain_max, high.scale.domain_max)
        self.assertEqual(low.scale.width, 600)
        self.assertEqual(high.scale.width, 300)
        self.assertNotEqual(
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

    def test_tick_value_formats_support_same_full_and_compact(self):
        compact_bars = ValueFormatConfig(
            decimal_places=1,
            compact=True,
            prefix="$",
            suffix=" USD",
        )
        self.assertEqual(
            format_axis_tick(250_000_000, 250_000_000, compact_bars),
            "$250M USD",
        )
        self.assertEqual(
            format_axis_tick(
                250_000_000, 250_000_000, compact_bars, "full"
            ),
            "$250,000,000 USD",
        )
        examples = {
            1_000: "1K",
            2_500: "2.5K",
            250_000_000: "250M",
            500_000_000: "500M",
            1_000_000_000: "1B",
            1_250_000_000: "1.25B",
            2_500_000_000_000: "2.5T",
        }
        plain = ValueFormatConfig(decimal_places=0)
        for value, expected in examples.items():
            with self.subTest(value=value):
                self.assertEqual(
                    format_axis_tick(value, value, plain, "compact"),
                    expected,
                )

    def test_compact_format_allows_more_non_overlapping_ticks_than_full(self):
        options = dict(
            axis_width=500,
            requested_count=12,
            tick_font_size=16,
            domain_max=2_500_000_000,
            value_format=ValueFormatConfig(decimal_places=0),
            font_family="DejaVu Sans",
            dpi=72,
        )
        full_count = adaptive_tick_count(
            **options, tick_value_format="full"
        )
        compact_count = adaptive_tick_count(
            **options, tick_value_format="compact"
        )

        self.assertGreater(compact_count, full_count)

    def test_vertical_ratio_reduces_tick_count_and_both_ratios_render(self):
        count_options = dict(
            domain_max=1_500_000_000,
            value_format=ValueFormatConfig(decimal_places=0),
            font_family="DejaVu Sans",
            dpi=72,
        )
        landscape_count = adaptive_tick_count(
            1_400,
            8,
            16,
            **count_options,
        )
        vertical_count = adaptive_tick_count(
            520,
            8,
            16,
            **count_options,
        )
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
                value_grid_tick_value_format="compact",
            )
            bars = [sprite("A", 40_000, width=width - 70, x=40, y=110)]
            tracker = ValueAxisTracker.from_config(config, [bars])
            state = tracker.next(bars)
            bar_scale = BarValueScaleResolver.from_config(
                config, [bars]
            ).for_sprites(bars)
            self._assert_tick_labels_do_not_overlap(config, state)
            scene = Scene(
                title="",
                bars=scale_bar_sprites(bars, bar_scale),
                value_axis=state,
                bar_value_scale=bar_scale,
            )
            renderer = BarRenderer(config=config)
            try:
                rgba = renderer.render_rgba(scene)
            finally:
                renderer.close()
            self.assertEqual(len(rgba), width * height * 4)

    def test_browser_geometry_uses_current_width_and_preserves_fun_fact_limit(self):
        config = self._browser_config(value_grid_mode="dynamic")
        fun_fact = self._browser_fun_fact()
        layout = LayoutEngine(config=config, fun_fact_config=fun_fact)
        wide = layout.build(self._browser_bars_2009())
        constrained = layout.build(self._browser_bars_2012())
        tracker = ValueAxisTracker.from_config(config, [wide, constrained])
        bar_resolver = BarValueScaleResolver.from_config(
            config, [wide, constrained]
        )

        wide_state = tracker.next(wide)
        wide_bar_scale = bar_resolver.for_sprites(wide)
        wide_scaled = scale_bar_sprites(wide, wide_bar_scale)
        ie = next(bar for bar in wide_scaled if bar.name == "IE")

        self.assertAlmostEqual(max(bar.width for bar in wide), 1462.0)
        self.assertAlmostEqual(wide_state.scale.width, 1462.0)
        self.assertAlmostEqual(wide_state.scale.domain_max, 1_500_000_000)
        self.assertAlmostEqual(ie.width, 1462.0)

        constrained_state = tracker.next(constrained)
        constrained_bar_scale = bar_resolver.for_sprites(constrained)
        constrained_scaled = scale_bar_sprites(
            constrained,
            constrained_bar_scale,
        )
        self.assertAlmostEqual(
            max(bar.width for bar in constrained),
            704.0143603133159,
        )
        self.assertAlmostEqual(
            constrained_state.scale.width,
            704.0143603133159,
        )
        self.assertAlmostEqual(
            constrained_state.scale.right_x,
            config.left_margin + 704.0143603133159,
        )
        required_value_lane = layout._required_value_lane(constrained)
        collision_right = (
            fun_fact.editorial_card_x
            - fun_fact.editorial_collision_gap
        )
        scaled_by_name = {bar.name: bar for bar in constrained_scaled}
        for bar in constrained:
            row_top = bar.y - (bar.height / 2.0)
            row_bottom = bar.y + (bar.height / 2.0)
            if (
                row_bottom > fun_fact.editorial_card_y
                and row_top
                < fun_fact.editorial_card_y + fun_fact.editorial_card_height
            ):
                scaled = scaled_by_name[bar.name]
                self.assertLessEqual(
                    scaled.x + scaled.width + required_value_lane,
                    collision_right,
                )

    def test_editorial_reservation_is_stable_before_during_and_after_card(self):
        config = self._browser_config(value_grid_mode="dynamic")
        fun_fact_config = self._browser_fun_fact()
        bars = LayoutEngine(
            config=config,
            fun_fact_config=fun_fact_config,
        ).build(self._browser_bars_2009())
        state = ValueAxisTracker.from_config(config, [bars]).next(bars)
        bar_scale = BarValueScaleResolver.from_config(
            config, [bars]
        ).for_sprites(bars)
        scaled = scale_bar_sprites(bars, bar_scale)
        active = ActiveFunFact(
            FunFact(
                id="audit",
                start="2010-01",
                end="2010-01",
                headline="Editorial audit",
            ),
            opacity=1.0,
        )
        scenes = (
            Scene(
                title="", bars=scaled, value_axis=state,
                bar_value_scale=bar_scale,
            ),
            Scene(
                title="",
                bars=scaled,
                value_axis=state,
                fun_fact=active,
                bar_value_scale=bar_scale,
            ),
            Scene(
                title="", bars=scaled, value_axis=state,
                bar_value_scale=bar_scale,
            ),
        )
        geometries = [
            build_scene_geometry(config, fun_fact_config, scene)
            for scene in scenes
        ]

        self.assertEqual(geometries[0], geometries[1])
        self.assertEqual(geometries[1], geometries[2])
        self.assertIsNotNone(geometries[0]["editorial_rect"])

    def test_browser_static_domain_is_global_but_width_is_per_frame(self):
        config = self._browser_config(value_grid_mode="static")
        layout = LayoutEngine(
            config=config,
            fun_fact_config=self._browser_fun_fact(),
        )
        wide = layout.build(self._browser_bars_2009())
        constrained = layout.build(self._browser_bars_2012())
        tracker = ValueAxisTracker.from_config(config, [wide, constrained])

        wide_state = tracker.next(wide)
        constrained_state = tracker.next(constrained)

        self.assertEqual(
            wide_state.scale.domain_max,
            constrained_state.scale.domain_max,
        )
        self.assertAlmostEqual(wide_state.scale.width, 1462.0)
        self.assertAlmostEqual(
            constrained_state.scale.width,
            704.0143603133159,
        )

    def test_real_tick_labels_do_not_overlap_for_targets_and_aspect_ratios(self):
        for width, height in ((1920, 1080), (1080, 1920)):
            for target_count in (3, 5, 8):
                with self.subTest(
                    width=width,
                    height=height,
                    target_count=target_count,
                ):
                    config = self._browser_config(
                        width=width,
                        height=height,
                        right_margin=190,
                        value_grid_target_tick_count=target_count,
                    )
                    bars = [
                        sprite(
                            "IE",
                            1_122_031_900,
                            width=config.max_bar_width,
                            x=config.left_margin,
                        )
                    ]
                    state = ValueAxisTracker.from_config(
                        config,
                        [bars],
                    ).next(bars)

                    self.assertLessEqual(
                        len([tick for tick in state.ticks if tick.label]),
                        target_count,
                    )
                    self._assert_tick_labels_do_not_overlap(config, state)

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
        bar_scale = BarValueScaleResolver.from_config(
            config, [bars]
        ).for_sprites(bars)
        scene = Scene(
            title="",
            bars=scale_bar_sprites(bars, bar_scale),
            value_axis=state,
            bar_value_scale=bar_scale,
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

    def test_advanced_bar_track_uses_structural_bar_extent(self):
        config = self._config(
            bar_appearance_mode="unified",
            bar_track_enabled=True,
        )
        bars = [sprite("A", 40_000)]
        state = ValueAxisTracker.from_config(config, [bars]).next(bars)
        bar_scale = BarValueScaleResolver.from_config(
            config, [bars]
        ).for_sprites(bars)
        scene = Scene(
            title="",
            bars=scale_bar_sprites(bars, bar_scale),
            value_axis=state,
            bar_value_scale=bar_scale,
        )
        renderer = BarRenderer(config=config)
        try:
            renderer._draw_scene(scene, draw_canvas=True)
            track_vertices = (
                renderer._advanced_track_collection.get_paths()[0].vertices
            )
            self.assertAlmostEqual(
                max(track_vertices[:, 0]),
                bar_scale.right_x,
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
        bar_scale = BarValueScaleResolver.from_config(
            config, [bars]
        ).for_sprites(bars)
        scene = Scene(
            title="Title",
            subtitle="Period",
            bars=scale_bar_sprites(bars, bar_scale),
            value_axis=state,
            bar_value_scale=bar_scale,
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
                preview.scene.bar_value_scale.x_for_value(bar.value),
            )

    def test_legacy_default_is_off_and_builder_loader_preserve_axis_settings(self):
        self.assertFalse(ChartConfig().value_grid_enabled)
        self.assertEqual(ChartConfig().value_grid_tick_value_format, "same")
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
            value_grid_tick_value_format="compact",
        )
        config = load_project_data(data).chart_config
        values = project_form_values(data)

        self.assertTrue(config.value_grid_enabled)
        self.assertEqual(config.value_grid_mode, "static")
        self.assertEqual(config.value_grid_line_thickness, 2.5)
        self.assertEqual(config.value_grid_tick_font_weight, "bold")
        self.assertEqual(config.value_grid_tick_value_format, "compact")
        self.assertEqual(values["value_grid_target_tick_count"], 6)
        self.assertEqual(values["value_grid_tick_value_format"], "compact")

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
                value_grid_tick_value_format="compact",
                start_bars_at_zero=True,
                leader_full_width_point=0.5,
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
                value_grid_tick_value_format="compact",
                start_bars_at_zero=True,
                leader_full_width_point=0.5,
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
                [
                    (tick.value, tick.x, tick.label, tick.opacity)
                    for tick in preview_axis.ticks
                ],
                [
                    (tick.value, tick.x, tick.label, tick.opacity)
                    for tick in render_axis.ticks
                ],
            )
            self.assertEqual(
                [(bar.name, bar.value, bar.x, bar.width) for bar in preview_scene.bars],
                [(bar.name, bar.value, bar.x, bar.width) for bar in render_scene.bars],
            )
            self.assertEqual(
                preview_scene.bar_value_scale,
                render_scene.bar_value_scale,
            )
            for bar in preview_scene.bars:
                self.assertAlmostEqual(
                    bar.x + bar.width,
                    preview_scene.bar_value_scale.x_for_value(bar.value),
                )

    def test_monotone_values_match_preview_render_job_and_value_axis(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path = root / "data.csv"
            csv_path.write_text(
                "year,country,value\n"
                "0,IE,1012073100\n"
                "1,IE,999017500\n"
                "2,IE,999188800\n"
                "3,IE,1009314166\n",
                encoding="utf-8",
            )
            steps = 8
            chart = ChartConfig(
                frames_dir=str(root / "frames"),
                output_file=str(root / "video.mp4"),
                frame_output_mode="png_sequence",
                steps_per_transition=steps,
                value_grid_enabled=True,
                value_grid_mode="dynamic",
                animation=AnimationConfig(
                    easing="ease_out_cubic",
                    value_smoothing=True,
                    motion_mode="continuous",
                ),
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
                steps_per_transition=steps,
                value_grid_enabled=True,
                value_grid_mode="dynamic",
                motion_mode="continuous",
            )

            for step in (1, 4, 8):
                with self.subTest(step=step):
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
                            year=1,
                            transition_progress=step / steps,
                        )
                    preview_scene = (
                        preview_renderer.return_value.render.call_args.args[0]
                    )
                    render_scene = render_scenes[steps + step]
                    preview_bar = preview_scene.bars[0]
                    render_bar = render_scene.bars[0]

                    self.assertEqual(preview_bar.value, render_bar.value)
                    self.assertEqual(
                        preview_bar.width,
                        preview_scene.bar_value_scale.width_for_value(
                            preview_bar.value
                        ),
                    )
                    self.assertEqual(
                        render_bar.width,
                        render_scene.bar_value_scale.width_for_value(
                            render_bar.value
                        ),
                    )
                    self.assertEqual(
                        preview_scene.bar_value_scale,
                        render_scene.bar_value_scale,
                    )

            self.assertGreater(render_scenes[steps + 1].bars[0].value, 999_017_500)

    def _assert_tick_labels_do_not_overlap(self, config, state):
        font = measurement_font(
            config.value_grid_tick_font_size,
            config.dpi,
            config.value_font_family or config.font_family,
            config.value_grid_tick_font_weight,
            config.value_grid_tick_font_style,
        )
        bounds = [
            (
                tick.x - (measure_text_width(tick.label, font) / 2.0),
                tick.x + (measure_text_width(tick.label, font) / 2.0),
            )
            for tick in state.ticks
            if tick.label
        ]
        self.assertTrue(all(
            previous_right <= current_left
            for (_, previous_right), (current_left, _)
            in zip(bounds, bounds[1:])
        ))

    @staticmethod
    def _browser_config(**overrides):
        defaults = dict(
            width=1920,
            height=1080,
            dpi=150,
            left_margin=20,
            right_margin=190,
            max_visible_bars=10,
            auto_fit_bar_count=True,
            bar_vertical_layout_mode="fill_available",
            bar_vertical_top_padding=18,
            bar_vertical_bottom_padding=18,
            title_enabled=False,
            subtitle_enabled=False,
            source_label_enabled=True,
            source_y=1050,
            source_font_size=13,
            logos_enabled=False,
            value_labels_enabled=True,
            value_font_size=26,
            value_font_family="Comic Sans MS",
            value_label_gap=12,
            bar_appearance_mode="unified",
            bar_fill_type="solid",
            bar_value_position="outside",
            value_format=ValueFormatConfig(decimal_places=0),
            value_grid_enabled=True,
            value_grid_mode="dynamic",
            value_grid_tick_labels_enabled=True,
            value_grid_tick_font_size=16,
            value_grid_target_tick_count=5,
        )
        defaults.update(overrides)
        return ChartConfig(**defaults)

    @staticmethod
    def _browser_fun_fact():
        return FunFactConfig(
            enabled=True,
            layout="editorial_floating",
            panel_width=525,
            panel_margin=24,
            panel_padding=22,
            editorial_card_x=992,
            editorial_card_y=280,
            editorial_card_width=917,
            editorial_card_height=725,
            editorial_collision_gap=24,
        )

    @staticmethod
    def _browser_bars_2009():
        values = (
            ("IE", 1_122_031_900),
            ("Firefox", 463_699_500),
            ("Opera", 53_006_500),
            ("Safari", 48_166_400),
            ("Chrome", 23_659_900),
            ("AOL", 4_662_900),
            ("Mozilla", 2_590_500),
            ("Nokia", 2_072_700),
            ("BlackBerry", 518_100),
            ("NetFront", 172_700),
        )
        return [sprite(name, value) for name, value in values]

    @staticmethod
    def _browser_bars_2012():
        values = (
            ("Chrome", 685_462_250),
            ("IE", 678_878_050),
            ("Firefox", 540_374_700),
            ("Safari", 204_110_200),
            ("Opera", 89_592_150),
            ("Android", 56_671_150),
            ("Nokia", 27_512_550),
            ("UC Browser", 20_222_900),
            ("BlackBerry", 13_403_550),
            ("NetFront", 9_406_000),
        )
        return [sprite(name, value) for name, value in values]

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
