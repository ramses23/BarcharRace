import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from math import ceil

import _test_path
import pandas as pd

from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from config.dataset_config import DatasetConfig
from config.fun_fact_config import FunFactConfig
from core.bar_selector import BarSelector
from core.bar_value_scale import (
    BarValueScaleResolver,
    progressive_growth_envelope,
)
from core.layout_engine import LayoutEngine
from core.motion_engine import MotionEngine
from core.timeline import Timeline
from core.value_axis import ValueAxisTracker
from models.bar_sprite import BarSprite
from studio.preview import _preview_value_scales
from studio.value_axis_preview import (
    clear_value_axis_preview_cache,
    get_preview_value_axis_bundle,
    get_value_axis_preview_resolver,
    value_axis_preview_cache_info,
)


def sprite(name, value, width, *, available=900.0, opacity=1.0, color="#123456"):
    return BarSprite(
        name=name,
        value=value,
        color=color,
        x=200,
        y=200,
        width=width,
        height=42,
        opacity=opacity,
        bar_available_width=available,
    )


def sequential_states(config, sprite_sets):
    tracker = ValueAxisTracker.from_config(config, sprite_sets)
    if len(sprite_sets) < 2:
        return [tracker.next(sprite_sets[0])]
    motion = MotionEngine(animation_config=config.animation)
    states = []
    for index in range(len(sprite_sets) - 1):
        if config.animation.continuous_motion:
            frames = motion.interpolate_sprites_continuous(
                sprite_sets[index - 1] if index > 0 else sprite_sets[index],
                sprite_sets[index],
                sprite_sets[index + 1],
                (
                    sprite_sets[index + 2]
                    if index + 2 < len(sprite_sets)
                    else sprite_sets[index + 1]
                ),
                steps=config.steps_per_transition,
                include_start=index == 0,
            )
        else:
            frames = motion.interpolate_sprites(
                sprite_sets[index],
                sprite_sets[index + 1],
                steps=config.steps_per_transition,
            )
        states.extend(tracker.next(frame) for frame in frames)
    return states


class ValueAxisPreviewCacheTest(unittest.TestCase):
    def setUp(self):
        clear_value_axis_preview_cache()

    def _config(self, **changes):
        config = ChartConfig(
            width=1920,
            height=1080,
            left_margin=240,
            right_margin=240,
            steps_per_transition=9,
            value_grid_enabled=True,
            value_grid_mode="dynamic",
            value_grid_target_tick_count=5,
            animation=AnimationConfig(
                easing="ease_out_cubic",
                enter_exit=True,
                value_smoothing=True,
                motion_mode="continuous",
            ),
        )
        return replace(config, **changes)

    def _history(self, *, available=900.0):
        # Includes leader changes, an exact tie, entry/exit, and rise/fall/rise.
        return (
            (
                sprite("A", 100, 700, available=available),
                sprite("B", 70, 490, available=available),
                sprite("D", 45, 315, available=available),
            ),
            (
                sprite("A", 145, 760, available=available),
                sprite("B", 145, 760, available=available),
                sprite("C", 40, 210, available=available),
            ),
            (
                sprite("A", 82, 500, available=available),
                sprite("B", 125, 760, available=available),
                sprite("C", 90, 547, available=available),
            ),
            (
                sprite("A", 190, 800, available=available),
                sprite("B", 110, 463, available=available),
                sprite("C", 95, 400, available=available),
            ),
        )

    def _timeline_fixture(self):
        dataset = DatasetConfig()
        frame = pd.DataFrame({
            "year": [
                2000, 2000, 2000,
                2001, 2001, 2001,
                2002, 2002, 2002,
                2003, 2003, 2003,
            ],
            "country": ["A", "B", "C"] * 4,
            "value": [
                100.0, 70.0, 45.0,
                145.0, 145.0, 40.0,
                82.0, 125.0, 90.0,
                190.0, 110.0, 95.0,
            ],
        })
        timeline = Timeline(frame, dataset)
        return timeline, timeline.get_years(), FunFactConfig()

    @staticmethod
    def _all_frames(config, sprite_sets):
        motion = MotionEngine(animation_config=config.animation)
        frames = []
        for index in range(len(sprite_sets) - 1):
            frames.extend(motion.interpolate_sprites_continuous(
                sprite_sets[index - 1] if index > 0 else sprite_sets[index],
                sprite_sets[index],
                sprite_sets[index + 1],
                (
                    sprite_sets[index + 2]
                    if index + 2 < len(sprite_sets)
                    else sprite_sets[index + 1]
                ),
                steps=config.steps_per_transition,
                include_start=index == 0,
            ))
        return frames

    def _preview_scale_at(self, config, timeline, years, fun_fact, frame_index):
        selector = BarSelector(config.selection)
        layout = LayoutEngine(config, fun_fact)
        sprite_sets = tuple(
            layout.build(selector.select(timeline.get_frame(year)))
            for year in years
        )
        frames = self._all_frames(config, sprite_sets)
        scale, axis = _preview_value_scales(
            timeline=timeline,
            selector=selector,
            layout=layout,
            chart_config=config,
            years=years,
            target_frame_index=frame_index,
            target_sprites=frames[frame_index],
        )
        fresh = BarValueScaleResolver.from_config(
            config, sprite_sets
        ).for_sprites(frames[frame_index], frame_index=frame_index)
        return scale, axis, fresh, frames[frame_index], sprite_sets

    def test_warm_axis_bundle_uses_current_bar_scale_for_all_full_width_points(self):
        timeline, years, fun_fact = self._timeline_fixture()
        base = self._config(start_bars_at_zero=True)
        first_bundle = None
        first_axis = None
        sequence = (0.5, 0.75, 0.5, 0.25, 1.0, 0.75)

        for point in sequence:
            config = replace(base, leader_full_width_point=point)
            selector = BarSelector(config.selection)
            layout = LayoutEngine(config, fun_fact)
            bundle = get_preview_value_axis_bundle(
                config, timeline, years, selector, layout
            )
            if first_bundle is None:
                first_bundle = bundle
            else:
                self.assertIs(bundle, first_bundle)

            frame_count = (len(years) - 1) * config.steps_per_transition + 1
            last = frame_count - 1
            target = ceil(point * last)
            indexes = tuple(dict.fromkeys((
                1,
                max(0, target - 1),
                target,
                min(last, target + 1),
                last,
            )))
            for frame_index in indexes:
                with self.subTest(point=point, frame=frame_index):
                    scale, axis, fresh, sprites, _ = self._preview_scale_at(
                        config, timeline, years, fun_fact, frame_index
                    )
                    self.assertEqual(scale, fresh)
                    if first_axis is None and frame_index == 1:
                        first_axis = axis
                    elif frame_index == 1:
                        self.assertEqual(axis, first_axis)

                    leader = max(sprite.value for sprite in sprites)
                    if frame_index >= target:
                        self.assertAlmostEqual(
                            scale.width_for_value(leader), scale.width
                        )
                    non_leaders = [
                        sprite.value for sprite in sprites
                        if 0.0 < sprite.value < leader
                    ]
                    if frame_index >= target and non_leaders:
                        value = non_leaders[0]
                        self.assertAlmostEqual(
                            scale.width_for_value(value)
                            / scale.width_for_value(leader),
                            value / leader,
                        )

        info = value_axis_preview_cache_info()
        self.assertEqual(info["bundle_misses"], 1)
        self.assertGreater(info["bundle_hits"], 1)

    def test_growth_envelope_never_uses_previous_warm_bundle_configuration(self):
        timeline, years, fun_fact = self._timeline_fixture()
        base = self._config(start_bars_at_zero=True)
        last = (len(years) - 1) * base.steps_per_transition
        frame_index = round(0.6 * last)

        for previous, current in ((0.5, 0.75), (0.75, 0.5), (0.25, 1.0)):
            clear_value_axis_preview_cache()
            self._preview_scale_at(
                replace(base, leader_full_width_point=previous),
                timeline,
                years,
                fun_fact,
                frame_index,
            )
            scale, axis, fresh, _, _ = self._preview_scale_at(
                replace(base, leader_full_width_point=current),
                timeline,
                years,
                fun_fact,
                frame_index,
            )
            with self.subTest(previous=previous, current=current):
                self.assertEqual(scale, fresh)
                self.assertAlmostEqual(
                    scale.growth_envelope,
                    progressive_growth_envelope(
                        scale.timeline_progress,
                        current,
                        enabled=True,
                    ),
                )
                if current > scale.timeline_progress:
                    self.assertLess(scale.growth_envelope, 1.0)
                self.assertIsNotNone(axis)
                self.assertEqual(value_axis_preview_cache_info()["bundle_misses"], 1)

    def test_start_zero_and_axis_modes_use_current_bar_scale_with_warm_cache(self):
        timeline, years, fun_fact = self._timeline_fixture()
        frame_index = 1
        for mode in ("dynamic", "static"):
            base = self._config(
                value_grid_mode=mode,
                leader_full_width_point=0.75,
                start_bars_at_zero=False,
            )
            without_zero, axis_before, fresh_before, _, _ = self._preview_scale_at(
                base, timeline, years, fun_fact, frame_index
            )
            with_zero, axis_after, fresh_after, _, _ = self._preview_scale_at(
                replace(base, start_bars_at_zero=True),
                timeline,
                years,
                fun_fact,
                frame_index,
            )
            with self.subTest(mode=mode):
                self.assertEqual(without_zero, fresh_before)
                self.assertEqual(with_zero, fresh_after)
                self.assertNotEqual(
                    without_zero.leader_occupancy,
                    with_zero.leader_occupancy,
                )
                self.assertEqual(axis_before, axis_after)

    def test_random_access_matches_every_sequential_frame_exactly(self):
        for animation in (
            AnimationConfig(
                easing="ease_out_cubic",
                enter_exit=True,
                value_smoothing=True,
                motion_mode="continuous",
            ),
            AnimationConfig(
                easing="smoothstep",
                enter_exit=False,
                value_smoothing=False,
                motion_mode="transition_easing",
            ),
        ):
            with self.subTest(mode=animation.motion_mode):
                config = self._config(animation=animation)
                history = self._history()
                expected = sequential_states(config, history)
                resolver = get_value_axis_preview_resolver(config, history)
                order = [
                    len(expected) - 1,
                    0,
                    len(expected) // 2,
                    len(expected) // 4,
                    (len(expected) * 3) // 4,
                ]
                order.extend(index for index in range(len(expected)))
                for index in order:
                    self.assertEqual(resolver.state_at(index), expected[index])

    def test_dynamic_direction_and_history_match_after_random_lookup(self):
        config = self._config()
        history = self._history()
        expected = sequential_states(config, history)
        resolver = get_value_axis_preview_resolver(config, history)
        actual = [resolver.state_at(index) for index in reversed(range(len(expected)))]
        actual.reverse()
        self.assertEqual(actual, expected)

        movement_directions = []
        for previous, current in zip(actual, actual[1:]):
            previous_ticks = {tick.value: tick.x for tick in previous.ticks}
            shared = [
                tick for tick in current.ticks
                if tick.value > 0.0 and tick.value in previous_ticks
            ]
            if shared:
                movement_directions.append(tuple(
                    tick.x - previous_ticks[tick.value] for tick in shared
                ))
        self.assertTrue(any(any(delta < 0.0 for delta in item) for item in movement_directions))
        self.assertTrue(any(any(delta > 0.0 for delta in item) for item in movement_directions))

    def test_static_semantic_and_aspect_ratios_match_sequential(self):
        cases = (
            self._config(value_grid_mode="static"),
            self._config(start_bars_at_zero=True, leader_full_width_point=0.5),
            self._config(
                width=1080,
                height=1920,
                left_margin=180,
                right_margin=120,
                top_margin=330,
                bottom_margin=180,
            ),
        )
        for config in cases:
            with self.subTest(size=(config.width, config.height), mode=config.value_grid_mode):
                history = self._history(available=config.max_bar_width)
                expected = sequential_states(config, history)
                resolver = get_value_axis_preview_resolver(config, history)
                for index in (0, len(expected) // 2, len(expected) - 1):
                    self.assertEqual(resolver.state_at(index), expected[index])

    def test_snapshot_restore_has_no_hidden_mutable_history(self):
        config = self._config()
        history = self._history()
        motion = MotionEngine(config.animation)
        frames = motion.interpolate_sprites_continuous(
            history[0], history[0], history[1], history[2],
            steps=config.steps_per_transition,
        )
        tracker = ValueAxisTracker.from_config(config, history)
        for frame in frames[:5]:
            tracker.next(frame)
        snapshot = tracker.snapshot()
        expected = tracker.next(frames[5])
        restored = ValueAxisTracker.from_config(config, history).restore(snapshot)
        self.assertEqual(restored.next(frames[5]), expected)

    def test_cache_hits_for_frame_and_appearance_only_changes(self):
        config = self._config(start_bars_at_zero=True, leader_full_width_point=0.5)
        history = self._history()
        first = get_value_axis_preview_resolver(config, history)
        first.state_at(5)
        appearance_variants = (
            replace(config, bar_fill_color_start="#ABCDEF"),
            replace(config, background_color_override="#010203"),
            replace(config, value_grid_line_color="#FEDCBA"),
            replace(config, label_text_color="#AABBCC"),
            replace(config, value_text_color="#CCBBAA"),
            replace(config, source_text_color="#445566"),
            replace(config, time_label_text_color="#778899"),
            replace(config, bar_logo_border_color="#111111"),
            replace(config, logo_size=config.logo_size + 20),
            replace(config, label_font_size=config.label_font_size + 5),
            replace(config, bar_gap=config.bar_gap + 7),
            replace(
                config,
                animation=replace(
                    config.animation,
                    rank_movement_duration=0.4,
                ),
            ),
            # Both values keep SemanticDataScale active; the ValueAxis math is
            # unchanged although BarValueScale occupancy is resolved separately.
            replace(config, leader_full_width_point=0.75),
        )
        for variant in appearance_variants:
            with self.subTest(variant=variant):
                self.assertIs(
                    get_value_axis_preview_resolver(variant, history),
                    first,
                )
        self.assertIs(get_value_axis_preview_resolver(config, history), first)
        first.state_at(17)
        info = value_axis_preview_cache_info()
        self.assertEqual(info["misses"], 1)
        self.assertEqual(info["entries"], 1)
        self.assertGreaterEqual(info["hits"], len(appearance_variants) + 1)

    def test_numerical_and_structural_changes_invalidate(self):
        config = self._config()
        history = self._history()
        baseline = get_value_axis_preview_resolver(config, history)
        changed_history = list(history)
        changed_history[1] = tuple(
            replace(item, value=item.value + 1) if item.name == "A" else item
            for item in changed_history[1]
        )
        variants = (
            (config, tuple(changed_history)),
            (replace(config, animation=replace(config.animation, value_smoothing=False)), history),
            (replace(config, value_grid_mode="static"), history),
            (replace(config, value_grid_target_tick_count=7), history),
            (replace(config, right_margin=config.right_margin + 10), history),
        )
        for variant_config, variant_history in variants:
            with self.subTest(config=variant_config):
                self.assertIsNot(
                    get_value_axis_preview_resolver(
                        variant_config, variant_history
                    ),
                    baseline,
                )

    def test_preview_bundle_survives_reruns_and_ignores_overlay_appearance(self):
        config = self._config()
        dataset = DatasetConfig(category_colors={"A": "#111111"})
        frame = pd.DataFrame({
            "year": [2000, 2000, 2001, 2001],
            "country": ["A", "B", "A", "B"],
            "value": [100.0, 80.0, 120.0, 70.0],
        })
        timeline = Timeline(frame, dataset)
        selector = BarSelector(config.selection)
        overlay = FunFactConfig(
            enabled=True,
            layout="editorial_floating",
            editorial_layout_mode="overlay",
            editorial_background_color="#222222",
            editorial_bar_clearance=16,
        )
        first = get_preview_value_axis_bundle(
            config,
            timeline,
            timeline.get_years(),
            selector,
            LayoutEngine(config, overlay),
        )
        same = get_preview_value_axis_bundle(
            replace(config, background_color_override="#010203", bar_gap=19),
            Timeline(frame.copy(), replace(dataset, category_colors={"A": "#FFFFFF"})),
            timeline.get_years(),
            selector,
            LayoutEngine(
                replace(config, background_color_override="#010203", bar_gap=19),
                replace(
                    overlay,
                    editorial_background_color="#EEEEEE",
                    editorial_bar_clearance=99,
                    editorial_protect_top_n=8,
                ),
            ),
        )
        self.assertIs(same, first)
        info = value_axis_preview_cache_info()
        self.assertEqual(info["bundle_misses"], 1)
        self.assertEqual(info["bundle_hits"], 1)

        changed_frame = frame.copy()
        changed_frame.loc[changed_frame["year"] == 2001, "value"] += 1
        changed = get_preview_value_axis_bundle(
            config,
            Timeline(changed_frame, dataset),
            timeline.get_years(),
            selector,
            LayoutEngine(config, overlay),
        )
        self.assertIsNot(changed, first)

    def test_cross_project_keys_and_bounded_lru_eviction(self):
        config = self._config()
        resolvers = []
        for offset in range(6):
            history = tuple(
                tuple(replace(item, value=item.value + offset) for item in period)
                for period in self._history()
            )
            resolvers.append(get_value_axis_preview_resolver(config, history))
        info = value_axis_preview_cache_info()
        self.assertEqual(info["entries"], info["max_entries"])
        self.assertEqual(info["max_entries"], 4)
        first_again = get_value_axis_preview_resolver(config, self._history())
        self.assertIsNot(first_again, resolvers[0])

    def test_checkpoint_and_exact_state_memos_are_bounded(self):
        config = self._config(steps_per_transition=300)
        history = self._history()
        resolver = get_value_axis_preview_resolver(config, history)
        for index in range(100):
            resolver.state_at(index)
        info = value_axis_preview_cache_info()
        self.assertLessEqual(info["memoized_states"], 64)
        self.assertLessEqual(info["checkpoints"], 101)
        self.assertEqual(info["max_checkpoints_per_resolver"], 512)

    def test_concurrent_random_reads_are_deterministic(self):
        config = self._config(steps_per_transition=40)
        history = self._history()
        expected = sequential_states(config, history)
        resolver = get_value_axis_preview_resolver(config, history)
        indexes = [0, 1, 17, 41, 79, len(expected) - 1] * 4
        with ThreadPoolExecutor(max_workers=4) as executor:
            actual = list(executor.map(resolver.state_at, indexes))
        self.assertEqual(actual, [expected[index] for index in indexes])


if __name__ == "__main__":
    unittest.main()
