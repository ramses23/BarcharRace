from dataclasses import replace
import unittest

import _test_path
from config.chart_config import ChartConfig
from core.bar_value_scale import (
    BarValueScaleResolver,
    normalized_effective_timeline_progress,
    progressive_growth_envelope,
    scale_bar_sprites,
)
from core.motion_engine import MotionEngine
from core.value_axis import ValueAxisTracker
from models.bar_sprite import BarSprite
from models.scene import Scene
from models.value_axis import GridDisplayScale, ValueAxisState, ValueAxisTick
from renderer.bar_renderer import BarRenderer


def sprite(
    name,
    value,
    *,
    width=600,
    y=100,
    opacity=1.0,
    logo_path=None,
    bar_available_width=None,
):
    return BarSprite(
        name=name,
        value=value,
        color="#2A78B8",
        x=100,
        y=y,
        width=width,
        height=40,
        opacity=opacity,
        logo_path=logo_path,
        bar_available_width=bar_available_width,
    )


def grid_state(*, width, domain, tick_value=50):
    scale = GridDisplayScale(origin_x=100, width=width, domain_max=domain)
    return ValueAxisState(
        scale=scale,
        ticks=(ValueAxisTick(
            value=tick_value,
            x=scale.x_for_value(tick_value),
            label=str(tick_value),
            opacity=1.0,
        ),),
        tick_step=tick_value,
        line_top=60,
        line_bottom=300,
        label_y=40,
    )


class BarValueScaleTest(unittest.TestCase):
    def test_default_config_preserves_fixed_project_max_widths_exactly(self):
        config = ChartConfig(width=800, left_margin=100, right_margin=100)
        endpoint_sets = [
            [sprite("A", 25, bar_available_width=600)],
            [sprite("A", 50, bar_available_width=600)],
            [sprite("A", 100, bar_available_width=600)],
        ]
        resolver = BarValueScaleResolver.from_config(config, endpoint_sets)

        self.assertEqual(resolver.domain_max, 100)
        for sprites in endpoint_sets:
            scale = resolver.for_sprites(sprites)
            self.assertEqual(
                scale.width_for_value(sprites[0].value),
                sprites[0].value / 100 * 600,
            )

    def test_smoothstep_growth_is_exact_monotone_and_stops_at_target(self):
        observed = [
            progressive_growth_envelope(point, 1.0, enabled=True)
            for point in (0.0, 0.25, 0.5, 0.75, 1.0)
        ]

        self.assertEqual(observed, [0.0, 0.15625, 0.5, 0.84375, 1.0])
        self.assertTrue(all(a <= b for a, b in zip(observed, observed[1:])))
        self.assertEqual(
            progressive_growth_envelope(0.75, 0.5, enabled=True),
            1.0,
        )

    def test_first_effective_frame_has_zero_bodies_but_real_values(self):
        config = ChartConfig(
            width=800,
            left_margin=100,
            right_margin=100,
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        raw = [
            sprite("A", 80, bar_available_width=600),
            sprite("B", 40, y=160, bar_available_width=600),
        ]
        resolver = BarValueScaleResolver.from_config(config, [raw, raw])
        scaled = scale_bar_sprites(
            raw,
            resolver.for_sprites(raw, timeline_progress=0.0),
        )

        self.assertEqual([bar.width for bar in scaled], [0.0, 0.0])
        self.assertEqual([bar.value for bar in scaled], [80, 40])
        self.assertEqual([bar.rank for bar in scaled], [None, None])

    def test_full_width_reference_supports_25_50_and_75_percent(self):
        endpoints = [
            [sprite("Leader", value, bar_available_width=600)]
            for value in (20, 40, 60, 80, 100)
        ]
        for point, expected_reference in (
            (0.25, 40),
            (0.5, 60),
            (0.75, 80),
        ):
            with self.subTest(point=point):
                config = ChartConfig(
                    width=800,
                    left_margin=100,
                    right_margin=100,
                    steps_per_transition=20,
                    start_bars_at_zero=True,
                    leader_full_width_point=point,
                )
                resolver = BarValueScaleResolver.from_config(config, endpoints)
                target_sprites = endpoints[int(point * 4)]
                scale = resolver.for_sprites(
                    target_sprites, timeline_progress=point,
                )

                self.assertEqual(resolver.domain_max, expected_reference)
                self.assertAlmostEqual(
                    scale.width_for_value(resolver.domain_max),
                    scale.width,
                )
                self.assertEqual(scale.growth_envelope, 1.0)

    def test_start_zero_off_keeps_first_frame_visible_with_early_reference(self):
        config = ChartConfig(
            width=800,
            left_margin=100,
            right_margin=100,
            steps_per_transition=9,
            start_bars_at_zero=False,
            leader_full_width_point=0.5,
        )
        endpoints = [
            [sprite("Leader", 50, bar_available_width=600)],
            [sprite("Leader", 100, bar_available_width=600)],
            [sprite("Leader", 150, bar_available_width=600)],
        ]
        resolver = BarValueScaleResolver.from_config(config, endpoints)
        first = resolver.for_sprites(endpoints[0], timeline_progress=0.0)
        target = resolver.for_sprites(endpoints[1], timeline_progress=0.5)

        self.assertGreater(first.width_for_value(50), 0.0)
        self.assertEqual(first.growth_envelope, 0.5)
        self.assertEqual(first.width_for_value(50), 300)
        self.assertAlmostEqual(
            target.width_for_value(resolver.domain_max), target.width
        )

    def test_post_target_bars_remain_relative_above_historical_reference(self):
        config = ChartConfig(
            width=800,
            left_margin=100,
            right_margin=100,
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        endpoints = [
            [sprite("China", 800), sprite("India", 700, y=160)],
            [sprite("China", 1_115), sprite("India", 900, y=160)],
            [
                sprite("China", 1_400),
                sprite("India", 1_300, y=160),
                sprite("Third", 1_200, y=220),
            ],
        ]
        resolver = BarValueScaleResolver.from_config(config, endpoints)
        scale = resolver.for_sprites(endpoints[-1], timeline_progress=1.0)
        scaled = {
            bar.name: bar
            for bar in scale_bar_sprites(endpoints[-1], scale)
        }

        self.assertEqual(resolver.domain_max, 1_115)
        self.assertEqual(scaled["China"].width, scale.width)
        self.assertAlmostEqual(scaled["India"].width / scale.width, 1_300 / 1_400)
        self.assertAlmostEqual(scaled["Third"].width / scale.width, 1_200 / 1_400)
        self.assertLess(scaled["India"].width, scaled["China"].width)
        self.assertLess(scaled["Third"].width, scaled["India"].width)

    def test_population_ratios_2002_2003_2012_and_2026(self):
        config = ChartConfig(
            width=800,
            left_margin=100,
            right_margin=100,
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        cases = (
            ("2002", 1_286_866_835, 1_097_600_380, "China"),
            ("2003", 1_294_517_323, 1_116_803_000, "China"),
            ("2012", 1_369_668_277, 1_278_946_261, "China"),
            ("2026", 1_412_914_090, 1_476_625_571, "India"),
        )
        for period, china, india, leader_name in cases:
            with self.subTest(period=period):
                current = [
                    sprite("China", china, bar_available_width=600),
                    sprite("India", india, y=160, bar_available_width=600),
                ]
                resolver = BarValueScaleResolver.from_config(
                    config,
                    [[sprite("China", 500)], [sprite("China", 1_115)], current],
                )
                scale = resolver.for_sprites(current, timeline_progress=1.0)
                bars = {
                    bar.name: bar
                    for bar in scale_bar_sprites(current, scale)
                }
                leader = bars[leader_name]
                other_name = "India" if leader_name == "China" else "China"
                other = bars[other_name]

                self.assertEqual(leader.width, scale.width)
                self.assertAlmostEqual(
                    other.width / leader.width,
                    other.value / leader.value,
                )
                self.assertLess(other.width, leader.width)

    def test_leader_switch_and_exact_tie_are_stable(self):
        config = ChartConfig(
            width=800,
            left_margin=100,
            right_margin=100,
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        china_leads = [sprite("China", 120), sprite("India", 110, y=160)]
        india_leads = [sprite("China", 125), sprite("India", 130, y=160)]
        tie = [sprite("China", 140), sprite("India", 140, y=160)]
        resolver = BarValueScaleResolver.from_config(
            config, [china_leads, india_leads, tie]
        )

        for sprites, leader_name in (
            (china_leads, "China"),
            (india_leads, "India"),
        ):
            scale = resolver.for_sprites(sprites, timeline_progress=0.75)
            bars = {
                bar.name: bar
                for bar in scale_bar_sprites(sprites, scale)
            }
            self.assertEqual(bars[leader_name].width, scale.width)
            self.assertEqual(max(bar.width for bar in bars.values()), scale.width)

        tie_scale = resolver.for_sprites(tie, timeline_progress=1.0)
        tie_bars = scale_bar_sprites(tie, tie_scale)
        self.assertEqual([bar.width for bar in tie_bars], [600, 600])

    def test_reveal_preserves_relative_proportions(self):
        config = ChartConfig(
            width=800,
            left_margin=100,
            right_margin=100,
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        current = [sprite("Leader", 600), sprite("Other", 450, y=160)]
        resolver = BarValueScaleResolver.from_config(config, [current, current])
        scale = resolver.for_sprites(current, timeline_progress=0.25)
        bars = {
            bar.name: bar
            for bar in scale_bar_sprites(current, scale)
        }

        self.assertEqual(scale.leader_occupancy, 0.5)
        self.assertEqual(bars["Leader"].width, 300)
        self.assertEqual(bars["Other"].width, 225)
        self.assertEqual(
            bars["Other"].width / bars["Leader"].width,
            450 / 600,
        )

    def test_stable_value_grows_during_reveal_and_decrease_returns_afterward(self):
        config = ChartConfig(
            width=800,
            left_margin=100,
            right_margin=100,
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        endpoints = [
            [sprite("A", 100, bar_available_width=600)],
            [sprite("A", 100, bar_available_width=600)],
        ]
        resolver = BarValueScaleResolver.from_config(config, endpoints)
        reveal_widths = [
            resolver.for_sprites(
                endpoints[0], timeline_progress=point
            ).width_for_value(100)
            for point in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)
        ]
        after_target = resolver.for_sprites(
            endpoints[0], timeline_progress=0.75
        )

        self.assertTrue(all(
            before < after
            for before, after in zip(reveal_widths, reveal_widths[1:])
        ))
        self.assertLess(
            after_target.width_for_value(70),
            after_target.width_for_value(100),
        )

    def test_progress_and_width_cap_are_safe_and_deterministic(self):
        self.assertEqual(normalized_effective_timeline_progress(0, 11), 0.0)
        self.assertEqual(normalized_effective_timeline_progress(5, 11), 0.5)
        self.assertEqual(normalized_effective_timeline_progress(10, 11), 1.0)
        self.assertEqual(normalized_effective_timeline_progress(99, 11), 1.0)

        config = ChartConfig(
            width=800,
            left_margin=100,
            right_margin=100,
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        raw = [sprite("A", 100, bar_available_width=600)]
        resolver = BarValueScaleResolver.from_config(config, [raw, raw])
        scale_a = resolver.for_sprites(raw, timeline_progress=1.0)
        scale_b = resolver.for_sprites(raw, timeline_progress=1.0)
        self.assertEqual(scale_a, scale_b)
        self.assertEqual(scale_a.width_for_value(10_000), 600)

    def test_zero_tiny_and_normal_width_keep_logo_and_value_geometry_finite(self):
        config = ChartConfig(
            width=800,
            height=400,
            left_margin=100,
            right_margin=100,
            bar_logo_position="inside_right",
            logo_size=36,
            primary_logo_min_size=24,
            bar_value_position="outside",
            logos_enabled=True,
        )
        renderer = BarRenderer(config=config)
        try:
            layouts = []
            for width in (0.0, 0.25, 300.0):
                bar = sprite(
                    "A", 50, width=width, logo_path="logo.png",
                    bar_available_width=600,
                )
                logo = renderer._logo_layout(bar)
                value = renderer._value_label_layout(bar, "50")
                layouts.append((bar, logo, value))
        finally:
            renderer.close()

        for bar, logo, value in layouts:
            self.assertGreaterEqual(logo["left"], bar.x)
            self.assertGreaterEqual(value["x"], bar.x + bar.width)
            self.assertGreater(logo["size"], 0.0)

    def test_logo_and_value_label_follow_each_bars_relative_endpoint(self):
        config = ChartConfig(
            width=1000,
            height=400,
            left_margin=100,
            right_margin=100,
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
            bar_logo_position="inside_right",
            logo_size=36,
            bar_value_position="outside",
            logos_enabled=True,
        )
        current = [
            sprite(
                "Leader", 100, width=800, logo_path="leader.png",
                bar_available_width=800,
            ),
            sprite(
                "Other", 75, width=600, y=160, logo_path="other.png",
                bar_available_width=800,
            ),
        ]
        resolver = BarValueScaleResolver.from_config(config, [current, current])
        scale = resolver.for_sprites(current, timeline_progress=0.75)
        bars = scale_bar_sprites(current, scale)
        renderer = BarRenderer(config=config)
        try:
            layouts = {
                bar.name: (
                    bar,
                    renderer._logo_layout(bar),
                    renderer._value_label_layout(bar, str(bar.value)),
                )
                for bar in bars
            }
        finally:
            renderer.close()

        leader, leader_logo, leader_value = layouts["Leader"]
        other, other_logo, other_value = layouts["Other"]
        self.assertEqual(other.width / leader.width, 0.75)
        self.assertEqual(leader_logo["right"], leader.x + leader.width)
        self.assertEqual(other_logo["right"], other.x + other.width)
        self.assertGreaterEqual(other_value["x"], other.x + other.width)
        self.assertLess(other_logo["right"], leader_logo["right"])
        self.assertLess(other_value["x"], leader_value["x"])
        self.assertEqual(leader_value["ha"], "right")

    def test_progression_uses_reserved_structural_width_not_canvas_width(self):
        config = ChartConfig(
            width=1920,
            left_margin=210,
            right_margin=235,
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
        )
        reserved_width = 777
        raw = [sprite(
            "Leader", 100, width=reserved_width,
            bar_available_width=reserved_width,
        )]
        resolver = BarValueScaleResolver.from_config(config, [raw, raw])
        scale = resolver.for_sprites(raw, timeline_progress=0.5)

        self.assertEqual(scale.width, reserved_width)
        self.assertEqual(scale.width_for_value(resolver.domain_max), reserved_width)
        self.assertLess(scale.right_x, config.width - config.right_margin)

    def test_grid_only_change_preserves_bar_logo_value_and_track_geometry(self):
        config = ChartConfig(
            width=1000,
            height=400,
            left_margin=100,
            right_margin=100,
            top_margin=80,
            bottom_margin=60,
            value_grid_enabled=True,
            value_grid_tick_labels_enabled=True,
            start_bars_at_zero=True,
            leader_full_width_point=0.5,
            bar_appearance_mode="unified",
            bar_fill_type="solid",
            bar_track_enabled=True,
            bar_track_opacity=0.25,
            bar_logo_position="inside_right",
            logo_size=36,
            bar_value_position="outside",
            logos_enabled=True,
            title_enabled=False,
            subtitle_enabled=False,
            source_label_enabled=False,
            time_label_enabled=False,
        )
        raw = [
            sprite(
                "Leader", 80, width=800, logo_path="logo.png",
                bar_available_width=800,
            ),
            sprite(
                "Other", 60, width=600, y=160,
                bar_available_width=800,
            ),
        ]
        bar_scale = BarValueScaleResolver.from_config(
            config, [raw]
        ).for_sprites(raw, timeline_progress=1.0)
        bars = scale_bar_sprites(raw, bar_scale)
        compressed = grid_state(width=600, domain=120)
        expanded = grid_state(width=800, domain=100)
        bar = bars[0]
        other_bar = bars[1]

        renderer = BarRenderer(config=config)
        try:
            logo_before = renderer._logo_layout(bar)
            value_before = renderer._value_label_layout(bar, "80")
            logo_after = renderer._logo_layout(bar)
            value_after = renderer._value_label_layout(bar, "80")

            track_right = []
            render_bar = replace(bar, logo_path=None)
            for axis in (expanded, compressed):
                renderer._draw_scene(Scene(
                    title="",
                    bars=[render_bar],
                    value_axis=axis,
                    bar_value_scale=bar_scale,
                ), draw_canvas=True)
                vertices = (
                    renderer._advanced_track_collection
                    .get_paths()[0].vertices
                )
                track_right.append(max(vertices[:, 0]))
        finally:
            renderer.close()

        self.assertEqual(bar.x, bar_scale.origin_x)
        self.assertEqual(bar.x + bar.width, bar_scale.x_for_value(bar.value))
        self.assertEqual(other_bar.width / bar.width, 60 / 80)
        self.assertEqual(logo_before, logo_after)
        self.assertEqual(value_before["x"], value_after["x"])
        self.assertEqual(track_right, [bar_scale.right_x, bar_scale.right_x])
        self.assertNotEqual(expanded.ticks[0].x, compressed.ticks[0].x)

    def test_values_control_leader_middle_and_small_bar_widths(self):
        config = ChartConfig(width=800, left_margin=100, right_margin=100)
        endpoint_sets = [[
            sprite("Leader", 90),
            sprite("Middle", 50, y=160),
            sprite("Small", 10, y=220),
        ]]
        resolver = BarValueScaleResolver.from_config(config, endpoint_sets)
        scale = resolver.for_sprites(endpoint_sets[0])

        for name, low, high in (
            ("Leader", 80, 85),
            ("Middle", 40, 45),
            ("Small", 5, 7),
        ):
            with self.subTest(name=name):
                low_width = scale.width_for_value(low)
                high_width = scale.width_for_value(high)
                self.assertGreater(high_width, low_width)
                self.assertLess(scale.width_for_value(low - 1), low_width)
                self.assertEqual(
                    scale.width_for_value(low),
                    scale.width_for_value(low),
                )

    def test_rank_crossing_does_not_shrink_structural_race_width(self):
        config = ChartConfig(width=800, left_margin=100, right_margin=100)
        start = [
            replace(sprite(
                "A", 90, width=600, bar_available_width=600
            ), rank=1),
            replace(sprite(
                "B", 60, width=400, y=160, bar_available_width=600
            ), rank=2),
        ]
        end = [
            replace(sprite(
                "A", 60, width=400, y=160, bar_available_width=600
            ), rank=2),
            replace(sprite(
                "B", 90, width=600, bar_available_width=600
            ), rank=1),
        ]
        resolver = BarValueScaleResolver.from_config(config, [start, end])
        frames = MotionEngine().interpolate_sprites(start, end, steps=5)

        self.assertLess(max(bar.width for bar in frames[2]), 600)
        self.assertEqual(
            [resolver.for_sprites(frame).width for frame in frames],
            [600] * 5,
        )

    def test_reference_sequence_grows_while_grid_spacing_contracts(self):
        config = ChartConfig(width=800, left_margin=100, right_margin=100)
        values = (52.22, 52.35, 52.58, 52.87, 53.27)
        endpoint_sets = [[sprite("Leader", value)] for value in values]
        resolver = BarValueScaleResolver.from_config(config, endpoint_sets)
        widths = []
        grid_spacings = []

        for index, sprites in enumerate(endpoint_sets):
            scale = resolver.for_sprites(sprites)
            widths.append(scale.width_for_value(sprites[0].value))
            grid_spacings.append(
                grid_state(
                    width=600 - (index * 35),
                    domain=100,
                    tick_value=20,
                ).scale.width_for_value(20)
            )

        self.assertTrue(all(
            current > previous
            for previous, current in zip(widths, widths[1:])
        ))
        self.assertTrue(all(
            current < previous
            for previous, current in zip(grid_spacings, grid_spacings[1:])
        ))

    def test_nice_domain_transition_does_not_rescale_bars(self):
        config = ChartConfig(width=800, left_margin=100, right_margin=100)
        raw = [sprite("Leader", 52, width=600)]
        bar_scale = BarValueScaleResolver.from_config(
            config, [raw, [sprite("Leader", 90, width=600)]]
        ).for_sprites(raw)
        before = scale_bar_sprites(raw, bar_scale)[0]
        grid_before = grid_state(width=600, domain=60, tick_value=20)
        grid_after = grid_state(width=600, domain=75, tick_value=20)
        after = scale_bar_sprites(raw, bar_scale)[0]

        self.assertEqual((before.x, before.width), (after.x, after.width))
        self.assertNotEqual(grid_before.ticks[0].x, grid_after.ticks[0].x)

    def test_grid_mode_and_tick_count_do_not_define_bar_scale(self):
        raw_sets = [
            [sprite("A", 40, width=600)],
            [sprite("A", 80, width=600)],
        ]
        scales = []
        for mode, tick_count in (("static", 3), ("dynamic", 12)):
            config = ChartConfig(
                width=800,
                left_margin=100,
                right_margin=100,
                value_grid_enabled=True,
                value_grid_mode=mode,
                value_grid_target_tick_count=tick_count,
            )
            bar_resolver = BarValueScaleResolver.from_config(config, raw_sets)
            bar_scale = bar_resolver.for_sprites(raw_sets[0])
            grid = ValueAxisTracker.from_config(config, raw_sets).next(
                raw_sets[0]
            )
            scales.append(bar_scale)
            self.assertIsNotNone(grid)

        self.assertEqual(scales[0], scales[1])

    def test_structural_width_and_aspect_ratio_are_respected(self):
        for width, height, left, right in (
            (1920, 1080, 210, 235),
            (1080, 1920, 260, 120),
        ):
            with self.subTest(size=(width, height)):
                config = ChartConfig(
                    width=width,
                    height=height,
                    left_margin=left,
                    right_margin=right,
                )
                available = config.max_bar_width
                raw = [sprite(
                    "A",
                    80,
                    width=available,
                    bar_available_width=available,
                )]
                scale = BarValueScaleResolver.from_config(
                    config, [raw]
                ).for_sprites(raw)
                bar = scale_bar_sprites(raw, scale)[0]

                self.assertEqual(scale.width, available)
                self.assertEqual(bar.x, left)
                self.assertLessEqual(bar.x + bar.width, left + available)

    def test_resolution_is_deterministic_and_ignores_input_order(self):
        config = ChartConfig(width=800, left_margin=100, right_margin=100)
        first = [sprite("A", 80), sprite("B", 40, y=160)]
        second = list(reversed(first))
        resolver_a = BarValueScaleResolver.from_config(config, [first, second])
        resolver_b = BarValueScaleResolver.from_config(config, [second, first])

        self.assertEqual(resolver_a, resolver_b)
        self.assertEqual(
            resolver_a.for_sprites(first),
            resolver_b.for_sprites(second),
        )


if __name__ == "__main__":
    unittest.main()
