import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
import numpy as np

from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.export_config import ExportConfig
from config.project_file_loader import load_project_data
from core.background_motion import (
    MAX_ACTIVE_SPEED_LINES,
    MAX_EFFECTIVE_SPEED,
    SpeedLineMotionTracker,
    constant_speed_line_positions,
    effective_speed_line_motion,
    left_edge_exit_compressed_positions,
    normalized_leader_change,
    normalized_second_place_change,
    speed_line_emission_interval,
    speed_line_position,
)
from models.bar_sprite import BarSprite
from models.scene import Scene
from pipeline.render_job import RenderJob
from renderer.bar_renderer import BarRenderer
from studio.preview import render_project_preview
from studio.project_builder import build_project_data, project_form_values


def sprite(name, value, *, opacity=1.0):
    return BarSprite(
        name=name,
        value=value,
        color="#123456",
        x=20,
        y=20,
        width=100,
        height=20,
        opacity=opacity,
    )


def visible_line_columns(image):
    return np.flatnonzero(np.max(image[:, :, 3], axis=0) > 0)


class BackgroundSpeedLinesTest(unittest.TestCase):
    def test_spacing_accepts_800_without_changing_the_default(self):
        default_config = ChartConfig()
        config = ChartConfig(
            background_motion="horizontal_speed_lines",
            background_motion_line_spacing=800,
        )
        tracker = SpeedLineMotionTracker.from_config(config)

        self.assertEqual(default_config.background_motion_line_spacing, 160.0)
        self.assertEqual(config.background_motion_line_spacing, 800)
        self.assertEqual(tracker.base_spacing, 800.0)

    def test_constant_schedule_matches_direct_frame_and_moves_only_left(self):
        config = ChartConfig(
            width=320,
            height=180,
            fps=30,
            background_motion="horizontal_speed_lines",
            background_motion_speed=1.0,
            background_motion_line_spacing=80,
            background_motion_line_thickness=1,
        )
        tracker = SpeedLineMotionTracker.from_config(config)
        states = [tracker.next(0.0) for _ in range(12)]
        direct = constant_speed_line_positions(
            frame_index=11,
            fps=config.fps,
            canvas_width=config.width,
            base_speed=config.background_motion_speed,
            base_spacing=config.background_motion_line_spacing,
            line_thickness=config.background_motion_line_thickness,
        )

        self.assertEqual(len(states[-1].line_positions), len(direct))
        np.testing.assert_allclose(states[-1].line_positions, direct)
        for previous, current in zip(states, states[1:]):
            previous_positions = dict(zip(
                previous.emission_frames,
                previous.line_positions,
            ))
            current_positions = dict(zip(
                current.emission_frames,
                current.line_positions,
            ))
            for emission in previous_positions.keys() & current_positions.keys():
                self.assertLess(
                    current_positions[emission],
                    previous_positions[emission],
                )

    def test_initial_frame_is_clear_and_first_line_enters_from_right(self):
        tracker = self._tracker(smoothing=1.0)
        initial = tracker.next(0.0)
        following = tracker.next(0.0)

        self.assertFalse(any(
            -tracker.line_thickness <= position < tracker.canvas_width
            for position in initial.line_positions
        ))
        self.assertIn(tracker.canvas_width, initial.line_positions)
        self.assertAlmostEqual(
            following.line_positions[0],
            tracker.canvas_width - tracker.speed_pixels_per_frame,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            renderer = BarRenderer(
                output_dir=temp_dir,
                config=ChartConfig(
                    width=320,
                    height=180,
                    background_motion="horizontal_speed_lines",
                    background_motion_intensity=1.0,
                ),
            )
            try:
                initial_image = renderer._horizontal_speed_lines_background(
                    0,
                    line_positions=initial.line_positions,
                )
                following_image = renderer._horizontal_speed_lines_background(
                    1,
                    line_positions=following.line_positions,
                )
            finally:
                renderer.close()

        self.assertEqual(len(visible_line_columns(initial_image)), 0)
        self.assertGreater(len(visible_line_columns(following_image)), 0)

    def test_new_lines_spawn_at_right_and_high_response_emits_more_often(self):
        low_tracker = self._tracker(smoothing=1.0)
        high_tracker = self._tracker(smoothing=1.0)
        low_states = [low_tracker.next(0.0) for _ in range(120)]
        high_states = [high_tracker.next(1.0) for _ in range(120)]
        low_emissions = {
            emission
            for state in low_states
            for emission in state.emission_frames
            if emission >= 0.0
        }
        high_emissions = {
            emission
            for state in high_states
            for emission in state.emission_frames
            if emission >= 0.0
        }

        self.assertGreater(len(high_emissions), len(low_emissions))
        self.assertLess(
            high_states[0].emission_interval_frames,
            low_states[0].emission_interval_frames,
        )
        first_seen = {}
        for state in high_states:
            for emission, position in zip(
                state.emission_frames,
                state.line_positions,
            ):
                if emission >= 0.0:
                    first_seen.setdefault(emission, position)
        for emission in high_emissions:
            self.assertEqual(
                speed_line_position(
                    canvas_width=high_tracker.canvas_width,
                    speed_pixels_per_frame=(
                        high_tracker.speed_pixels_per_frame
                    ),
                    current_frame=emission,
                    emission_frame=emission,
                ),
                high_tracker.canvas_width,
            )
            self.assertGreaterEqual(
                first_seen[emission],
                high_tracker.canvas_width
                - high_tracker.speed_pixels_per_frame,
            )
            self.assertLessEqual(first_seen[emission], high_tracker.canvas_width)

    def test_variable_schedule_reconstructs_direct_frame_deterministically(self):
        responses = [*([0.1] * 12), *([0.8] * 24), *([0.2] * 18)]
        sequential_tracker = self._tracker(smoothing=0.14)
        sequential_states = [
            sequential_tracker.next(response) for response in responses
        ]
        reconstructed_tracker = self._tracker(smoothing=0.14)
        reconstructed = None
        for response in responses:
            reconstructed = reconstructed_tracker.next(response)

        self.assertIsNotNone(reconstructed)
        self.assertEqual(
            reconstructed.emission_frames,
            sequential_states[-1].emission_frames,
        )
        self.assertEqual(
            reconstructed.line_positions,
            sequential_states[-1].line_positions,
        )
        self.assertEqual(
            reconstructed.smoothed_response,
            sequential_states[-1].smoothed_response,
        )

    def test_response_changes_do_not_reposition_or_remove_existing_lines(self):
        low_tracker = self._tracker(smoothing=1.0)
        changing_tracker = self._tracker(smoothing=1.0)

        for _ in range(8):
            low_state = low_tracker.next(0.0)
            changing_state = changing_tracker.next(0.0)
        tracked_emissions = set(changing_state.emission_frames)

        for _ in range(8):
            low_state = low_tracker.next(0.0)
            changing_state = changing_tracker.next(1.0)
            low_positions = dict(zip(
                low_state.emission_frames,
                low_state.line_positions,
            ))
            changing_positions = dict(zip(
                changing_state.emission_frames,
                changing_state.line_positions,
            ))
            for emission in tracked_emissions & low_positions.keys():
                self.assertIn(emission, changing_positions)
                self.assertAlmostEqual(
                    changing_positions[emission],
                    low_positions[emission],
                )

        before_slowdown = dict(zip(
            changing_state.emission_frames,
            changing_state.line_positions,
        ))
        slowed = changing_tracker.next(0.0)
        after_slowdown = dict(zip(
            slowed.emission_frames,
            slowed.line_positions,
        ))
        self.assertGreater(
            slowed.emission_interval_frames,
            changing_state.emission_interval_frames,
        )
        for emission, position in before_slowdown.items():
            expected = position - changing_tracker.speed_pixels_per_frame
            if expected >= -changing_tracker.line_thickness:
                self.assertIn(emission, after_slowdown)
                self.assertAlmostEqual(after_slowdown[emission], expected)

    def test_renderer_draws_only_supplied_emissions_without_subdivisions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            renderer = BarRenderer(
                output_dir=temp_dir,
                config=ChartConfig(
                    width=320,
                    height=180,
                    background_motion="horizontal_speed_lines",
                    background_motion_intensity=1.0,
                    background_motion_line_spacing=80,
                    background_motion_line_thickness=1,
                ),
            )
            try:
                image = renderer._horizontal_speed_lines_background(
                    50,
                    line_positions=(40.0, 160.0, 320.0),
                )
            finally:
                renderer.close()

        self.assertEqual(tuple(visible_line_columns(image)), (40, 160))

    def test_lines_exit_left_and_are_not_wrapped_or_removed_early(self):
        tracker = self._tracker(smoothing=1.0)
        positions = []
        disappeared_at = None
        for frame_index in range(180):
            state = tracker.next(0.8 if frame_index < 60 else 0.2)
            by_emission = dict(zip(
                state.emission_frames,
                state.line_positions,
            ))
            if 0.0 in by_emission:
                positions.append(by_emission[0.0])
            elif positions:
                disappeared_at = frame_index
                break

        self.assertIsNotNone(disappeared_at)
        self.assertTrue(all(
            current < previous
            for previous, current in zip(positions, positions[1:])
        ))
        self.assertGreaterEqual(positions[-1], -tracker.line_thickness)
        self.assertLess(
            positions[-1] - tracker.speed_pixels_per_frame,
            -tracker.line_thickness,
        )

    def test_leader_change_is_scale_independent_and_tie_safe(self):
        low = normalized_leader_change(
            [sprite("A", 101), sprite("B", 80)],
            [sprite("A", 100), sprite("B", 80)],
            [sprite("A", 102), sprite("B", 80)],
        )
        high = normalized_leader_change(
            [sprite("A", 125_000_000), sprite("B", 80_000_000)],
            [sprite("A", 100_000_000), sprite("B", 80_000_000)],
            [sprite("A", 150_000_000), sprite("B", 80_000_000)],
        )
        tie = normalized_leader_change(
            [sprite("B", 100), sprite("A", 100), sprite("NaN", math.nan)],
            [sprite("A", 100), sprite("B", 100)],
            [sprite("A", 110), sprite("B", 300)],
        )

        self.assertGreater(high, low)
        self.assertEqual(high, 1.0)
        self.assertTrue(math.isfinite(tie))
        self.assertGreaterEqual(tie, 0.0)
        self.assertLessEqual(tie, 1.0)

    def test_second_place_change_uses_second_rank_and_has_stable_fallback(self):
        current = [
            sprite("Leader", 200),
            sprite("Second", 110),
            sprite("Third", 90),
        ]
        start = [
            sprite("Leader", 200),
            sprite("Second", 100),
            sprite("Third", 90),
        ]
        end = [
            sprite("Leader", 200),
            sprite("Second", 150),
            sprite("Third", 90),
        ]

        self.assertEqual(normalized_leader_change(current, start, end), 0.0)
        self.assertEqual(
            normalized_second_place_change(current, start, end),
            1.0,
        )
        self.assertEqual(
            normalized_second_place_change(
                [sprite("Only", 100)],
                [sprite("Only", 90)],
                [sprite("Only", 110)],
            ),
            0.0,
        )
        self.assertEqual(
            normalized_second_place_change(
                [sprite("Only", 100), sprite("Hidden", 90, opacity=0.0)],
                start,
                end,
            ),
            0.0,
        )

    def test_exit_compression_is_local_bounded_and_never_reverses_motion(self):
        raw = (12.0, 36.0, 72.0, 150.0, 260.0)
        compressed = left_edge_exit_compressed_positions(
            raw,
            canvas_width=320,
            base_spacing=80,
            enabled=True,
            strength=1.0,
        )

        self.assertLess(compressed[0], raw[0])
        self.assertLess(compressed[1], raw[1])
        self.assertLess(
            compressed[1] - compressed[0],
            raw[1] - raw[0],
        )
        self.assertEqual(compressed[3:], raw[3:])
        self.assertEqual(
            left_edge_exit_compressed_positions(
                raw,
                canvas_width=320,
                base_spacing=80,
                enabled=False,
                strength=1.0,
            ),
            raw,
        )

        transformed = [
            left_edge_exit_compressed_positions(
                (position,),
                canvas_width=320,
                base_spacing=80,
                enabled=True,
                strength=1.0,
            )[0]
            for position in range(90, -1, -3)
        ]
        self.assertTrue(all(
            current < previous
            for previous, current in zip(transformed, transformed[1:])
        ))

    def test_smoothing_approaches_and_releases_target_gradually(self):
        tracker = SpeedLineMotionTracker(
            fps=30,
            base_speed=1.0,
            base_spacing=160,
            line_thickness=2,
            response_mode="leader_acceleration",
            response_strength=1.0,
        )

        first = tracker.next(1.0)
        second = tracker.next(1.0)
        for _ in range(30):
            high = tracker.next(1.0)
        released = tracker.next(0.0)

        self.assertGreater(first.smoothed_response, 0.0)
        self.assertLess(first.smoothed_response, 1.0)
        self.assertGreater(second.smoothed_response, first.smoothed_response)
        self.assertGreater(high.smoothed_response, second.smoothed_response)
        self.assertLess(released.smoothed_response, high.smoothed_response)
        self.assertGreater(released.smoothed_response, 0.0)

    def test_emission_interval_reacts_to_data_and_is_safely_bounded(self):
        low_speed, low_spacing = effective_speed_line_motion(
            base_speed=1.0,
            base_spacing=160,
            line_thickness=2,
            response=0.0,
            response_strength=1.0,
        )
        high_speed, high_spacing = effective_speed_line_motion(
            base_speed=1.0,
            base_spacing=160,
            line_thickness=2,
            response=1.0,
            response_strength=1.0,
        )
        clamped_speed, clamped_spacing = effective_speed_line_motion(
            base_speed=999,
            base_spacing=0,
            line_thickness=20,
            response=999,
            response_strength=999,
        )

        low_interval = speed_line_emission_interval(
            fps=30,
            canvas_width=1920,
            base_speed=1.0,
            base_spacing=160,
            line_thickness=2,
            response=0.0,
            response_strength=1.0,
        )
        high_interval = speed_line_emission_interval(
            fps=30,
            canvas_width=1920,
            base_speed=1.0,
            base_spacing=160,
            line_thickness=2,
            response=1.0,
            response_strength=1.0,
        )
        dense_tracker = SpeedLineMotionTracker(
            fps=30,
            base_speed=4.0,
            base_spacing=24,
            line_thickness=1,
            response_mode="leader_acceleration",
            response_strength=2.0,
            smoothing=1.0,
            canvas_width=7680,
        )
        dense_states = [dense_tracker.next(1.0) for _ in range(500)]

        self.assertEqual(high_speed, low_speed)
        self.assertEqual(high_spacing, low_spacing)
        self.assertEqual(high_spacing, 160.0)
        self.assertLess(high_interval, low_interval)
        self.assertLessEqual(clamped_speed, MAX_EFFECTIVE_SPEED)
        self.assertGreaterEqual(clamped_spacing, 48.0)
        self.assertTrue(all(
            len(state.line_positions) <= MAX_ACTIVE_SPEED_LINES
            for state in dense_states
        ))

    def test_line_color_thickness_and_canvas_dimensions_are_applied(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            thin_renderer = BarRenderer(
                output_dir=temp_dir,
                config=ChartConfig(
                    width=320,
                    height=180,
                    background_motion="horizontal_speed_lines",
                    background_motion_intensity=1.0,
                    background_motion_line_spacing=80,
                    background_motion_line_thickness=1,
                    background_motion_line_color="#FF2200",
                ),
            )
            thick_renderer = BarRenderer(
                output_dir=temp_dir,
                config=ChartConfig(
                    width=320,
                    height=180,
                    background_motion="horizontal_speed_lines",
                    background_motion_intensity=1.0,
                    background_motion_line_spacing=80,
                    background_motion_line_thickness=6,
                    background_motion_line_color="#FF2200",
                ),
            )
            vertical_renderer = BarRenderer(
                output_dir=temp_dir,
                config=ChartConfig(
                    width=1080,
                    height=1920,
                    background_motion="horizontal_speed_lines",
                    background_motion_line_spacing=80,
                ),
            )
            try:
                thin = thin_renderer._horizontal_speed_lines_background(
                    0, line_positions=(0.0, 80.0, 160.0, 240.0)
                )
                thick = thick_renderer._horizontal_speed_lines_background(
                    0, line_positions=(0.0, 80.0, 160.0, 240.0)
                )
                vertical = vertical_renderer._horizontal_speed_lines_background(
                    0, line_positions=(0.0, 80.0, 160.0, 240.0)
                )
            finally:
                thin_renderer.close()
                thick_renderer.close()
                vertical_renderer.close()

        self.assertEqual(thin.shape, (180, 320, 4))
        self.assertEqual(vertical.shape, (1920, 1080, 4))
        self.assertGreater(np.count_nonzero(thick[:, :, 3]), 0)
        self.assertGreater(
            np.count_nonzero(thick[:, :, 3]),
            np.count_nonzero(thin[:, :, 3]),
        )
        colored_pixel = thick[0, 0]
        self.assertGreater(colored_pixel[0], 240)
        self.assertLess(colored_pixel[1], 50)
        self.assertEqual(colored_pixel[3], 255)

    def test_background_motion_is_composed_below_all_chart_content(self):
        renderer = BarRenderer(config=ChartConfig(
            width=320,
            height=180,
            dpi=72,
            left_margin=20,
            right_margin=20,
            background_color_override="#000000",
            background_motion="horizontal_speed_lines",
            background_motion_intensity=1.0,
            background_motion_line_thickness=3,
            background_motion_line_color="#FFFFFF",
            title_enabled=False,
            subtitle_enabled=False,
            time_label_enabled=False,
            source_label_enabled=False,
            category_labels_enabled=False,
            value_labels_enabled=False,
        ))
        scene = Scene(
            title="",
            bars=[BarSprite(
                name="Bar",
                value=1,
                color="#FF0000",
                x=20,
                y=90,
                width=280,
                height=30,
            )],
            background_motion_line_positions=(100.0,),
        )
        try:
            rgba = np.frombuffer(
                renderer.render_rgba(scene),
                dtype=np.uint8,
            ).reshape((180, 320, 4))
            background_zorder = renderer._background_motion_artist.get_zorder()
            bar_content_artist = next(
                artist
                for artist in (
                    renderer._advanced_composite_artist,
                    renderer._gradient_artist,
                    renderer._bar_artists[0].bar,
                )
                if artist is not None
            )
            content_zorders = (
                renderer._text_background_artist.get_zorder(),
                renderer._logo_composite_artist.get_zorder(),
                renderer._text_bar_artist.get_zorder(),
                renderer._text_foreground_artist.get_zorder(),
                renderer._fun_fact_artist.get_zorder(),
                renderer._short_overlay_artist.get_zorder(),
                bar_content_artist.get_zorder(),
            )
        finally:
            renderer.close()

        self.assertTrue(all(
            background_zorder < zorder for zorder in content_zorders
        ))
        self.assertGreater(rgba[90, 100, 0], 240)
        self.assertLess(rgba[90, 100, 1], 20)
        self.assertLess(rgba[90, 100, 2], 20)

    def test_builder_loader_and_form_values_preserve_speed_line_settings(self):
        data = self._project_data(
            background_motion="horizontal_speed_lines",
            background_motion_speed=1.4,
            background_motion_intensity=0.45,
            background_motion_line_spacing=144,
            background_motion_line_thickness=5,
            background_motion_line_color="#12AB34",
            background_motion_response="second_place_acceleration",
            background_motion_response_strength=1.7,
            background_motion_exit_compression=True,
            background_motion_exit_compression_strength=0.7,
        )

        config = load_project_data(data).chart_config
        values = project_form_values(data)

        self.assertEqual(config.background_motion, "horizontal_speed_lines")
        self.assertEqual(config.background_motion_line_color, "#12AB34")
        self.assertEqual(config.background_motion_line_thickness, 5)
        self.assertEqual(
            config.background_motion_response,
            "second_place_acceleration",
        )
        self.assertEqual(config.background_motion_response_strength, 1.7)
        self.assertTrue(config.background_motion_exit_compression)
        self.assertEqual(config.background_motion_exit_compression_strength, 0.7)
        self.assertEqual(values["background_motion_line_spacing"], 144)
        self.assertEqual(config.steps_per_transition, 30)

    def test_render_job_attaches_smoothed_response_without_changing_steps(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path = root / "data.csv"
            csv_path.write_text(
                "year,country,value\n"
                "2000,A,100\n2000,B,80\n"
                "2001,A,160\n2001,B,90\n",
                encoding="utf-8",
            )
            chart = ChartConfig(
                frames_dir=str(root / "frames"),
                output_file=str(root / "video.mp4"),
                frame_output_mode="png_sequence",
                steps_per_transition=4,
                background_motion="horizontal_speed_lines",
                background_motion_response="second_place_acceleration",
                background_motion_exit_compression=True,
            )

            with patch("pipeline.render_job.BarRenderer") as renderer_class:
                with patch("pipeline.render_job.VideoExporter"):
                    with patch("builtins.print"):
                        result = RenderJob(
                            config=chart,
                            data_source_config=DataSourceConfig(
                                source_type="csv",
                                csv_path=str(csv_path),
                            ),
                            dataset_config=DatasetConfig(),
                        ).run()

            scenes = [
                call.args[0]
                for call in renderer_class.return_value.render.call_args_list
            ]
            responses = [scene.background_motion_response for scene in scenes]
            line_positions = [
                scene.background_motion_line_positions for scene in scenes
            ]
            self.assertEqual(result.frames_rendered, 4)
            self.assertEqual(chart.steps_per_transition, 4)
            self.assertGreater(responses[-1], responses[0])
            self.assertTrue(all(math.isfinite(value) for value in responses))
            self.assertTrue(all(value is not None for value in line_positions))
            self.assertFalse(any(
                position < chart.width
                for position in line_positions[0]
            ))

            preview_data = self._project_data(
                csv_path="data.csv",
                steps_per_transition=4,
                background_motion="horizontal_speed_lines",
                background_motion_response="second_place_acceleration",
                background_motion_exit_compression=True,
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
                    transition_progress=0.5,
                )
            preview_scene = preview_renderer.return_value.render.call_args.args[0]
            self.assertEqual(
                preview_scene.background_motion_line_positions,
                scenes[2].background_motion_line_positions,
            )
            self.assertEqual(
                preview_scene.background_motion_response,
                scenes[2].background_motion_response,
            )

    def test_short_preview_receives_line_color_thickness_and_vertical_canvas(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            csv_path = root / "data.csv"
            csv_path.write_text(
                "year,country,value\n2000,A,100\n2001,A,150\n",
                encoding="utf-8",
            )
            data = self._project_data(
                csv_path="data.csv",
                background_motion="horizontal_speed_lines",
                background_motion_line_color="#12AB34",
                background_motion_line_thickness=5,
                background_motion_response="leader_acceleration",
                export_settings={"mode": "short"},
            )

            with patch("studio.preview.BarRenderer") as renderer_class:
                renderer_class.return_value.render.return_value = str(
                    root / "preview.png"
                )
                render_project_preview(
                    root / "project.json",
                    output_dir=root / "output" / "previews",
                    root_dir=root,
                    project_data=data,
                    preview_mode="transition",
                    year=2000,
                    transition_progress=0.5,
                )

            config = renderer_class.call_args.kwargs["config"]
            scene = renderer_class.return_value.render.call_args.args[0]
            self.assertEqual((config.width, config.height), (1080, 1920))
            self.assertEqual(config.background_motion_line_color, "#12AB34")
            self.assertEqual(config.background_motion_line_thickness, 5)
            self.assertIsNotNone(scene.background_motion_line_positions)
            self.assertGreater(len(scene.background_motion_line_positions), 0)
            self.assertGreater(scene.background_motion_response, 0.0)

    def test_legacy_modes_remain_available_with_off_as_default(self):
        self.assertEqual(ChartConfig().background_motion, "off")
        forward = ChartConfig(background_motion="forward_motion")
        self.assertEqual(forward.background_motion, "forward_motion")

    @staticmethod
    def _tracker(*, smoothing=1.0):
        return SpeedLineMotionTracker(
            fps=30,
            base_speed=1.0,
            base_spacing=80,
            line_thickness=1,
            response_mode="leader_acceleration",
            response_strength=1.0,
            smoothing=smoothing,
            canvas_width=320,
        )

    @staticmethod
    def _project_data(**overrides):
        defaults = dict(
            name="speed_lines",
            csv_path="data.csv",
            year_column="year",
            name_column="country",
            value_column="value",
            title="Speed lines",
            source_label="Source",
            output_file="output.mp4",
            frames_dir="frames",
            layout_preset="youtube_1080p",
            theme="clean_report",
            typography_preset="studio",
            value_format="decimal",
            fps=30,
            steps_per_transition=30,
            top_n=5,
            max_visible_bars=5,
        )
        defaults.update(overrides)
        return build_project_data(**defaults)


if __name__ == "__main__":
    unittest.main()
