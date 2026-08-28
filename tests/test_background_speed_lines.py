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
    MAX_EFFECTIVE_SPEED,
    SpeedLineMotionTracker,
    effective_speed_line_motion,
    normalized_leader_change,
)
from models.bar_sprite import BarSprite
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


class BackgroundSpeedLinesTest(unittest.TestCase):
    def test_constant_lines_are_deterministic_and_move_by_frame(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            renderer = BarRenderer(
                output_dir=temp_dir,
                config=ChartConfig(
                    width=320,
                    height=180,
                    fps=30,
                    background_motion="horizontal_speed_lines",
                    background_motion_speed=1.0,
                    background_motion_line_spacing=80,
                ),
            )
            try:
                first = renderer._horizontal_speed_lines_background(10)
                repeated = renderer._horizontal_speed_lines_background(10)
                later = renderer._horizontal_speed_lines_background(11)
            finally:
                renderer.close()

        self.assertTrue(np.array_equal(first, repeated))
        self.assertFalse(np.array_equal(first, later))

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

    def test_response_increases_speed_compresses_spacing_and_clamps(self):
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

        self.assertGreater(high_speed, low_speed)
        self.assertLess(high_spacing, low_spacing)
        self.assertLessEqual(clamped_speed, MAX_EFFECTIVE_SPEED)
        self.assertGreaterEqual(clamped_spacing, 48.0)

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
                    0, phase=0.0
                )
                thick = thick_renderer._horizontal_speed_lines_background(
                    0, phase=0.0
                )
                vertical = vertical_renderer._horizontal_speed_lines_background(
                    0, phase=0.0
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

    def test_builder_loader_and_form_values_preserve_speed_line_settings(self):
        data = self._project_data(
            background_motion="horizontal_speed_lines",
            background_motion_speed=1.4,
            background_motion_intensity=0.45,
            background_motion_line_spacing=144,
            background_motion_line_thickness=5,
            background_motion_line_color="#12AB34",
            background_motion_response="leader_acceleration",
            background_motion_response_strength=1.7,
        )

        config = load_project_data(data).chart_config
        values = project_form_values(data)

        self.assertEqual(config.background_motion, "horizontal_speed_lines")
        self.assertEqual(config.background_motion_line_color, "#12AB34")
        self.assertEqual(config.background_motion_line_thickness, 5)
        self.assertEqual(config.background_motion_response, "leader_acceleration")
        self.assertEqual(config.background_motion_response_strength, 1.7)
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
                background_motion_response="leader_acceleration",
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
            phases = [scene.background_motion_phase for scene in scenes]
            self.assertEqual(result.frames_rendered, 4)
            self.assertEqual(chart.steps_per_transition, 4)
            self.assertGreater(responses[-1], responses[0])
            self.assertTrue(all(math.isfinite(value) for value in responses))
            self.assertEqual(phases[0], 0.0)
            self.assertGreater(phases[-1], phases[0])

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
            self.assertIsNotNone(scene.background_motion_phase)
            self.assertGreater(scene.background_motion_response, 0.0)

    def test_legacy_modes_remain_available_with_off_as_default(self):
        self.assertEqual(ChartConfig().background_motion, "off")
        forward = ChartConfig(background_motion="forward_motion")
        self.assertEqual(forward.background_motion, "forward_motion")

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
