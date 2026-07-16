import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from config.bar_selection_config import BarSelectionConfig
from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from models.bar_sprite import BarSprite
from pipeline.render_job import RenderJob


class RenderJobTest(unittest.TestCase):
    def test_continuous_motion_renders_boundary_once_and_includes_final_year(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "sample.csv"
            csv_path.write_text(
                "year,country,value\n2000,USA,100\n2001,USA,120\n",
                encoding="utf-8",
            )
            config = ChartConfig(
                frames_dir=str(temp_path / "frames"),
                output_file=str(temp_path / "video.mp4"),
                steps_per_transition=2,
                frame_output_mode="png_sequence",
                animation=AnimationConfig(motion_mode="continuous"),
            )

            with patch("pipeline.render_job.BarRenderer") as renderer_class:
                with patch("pipeline.render_job.VideoExporter"):
                    with patch("builtins.print"):
                        result = RenderJob(
                            config=config,
                            data_source_config=DataSourceConfig(
                                source_type="csv",
                                csv_path=str(csv_path),
                            ),
                            dataset_config=DatasetConfig(),
                        ).run()

            self.assertEqual(result.frames_rendered, 3)
            self.assertEqual(renderer_class.return_value.render.call_count, 3)

    def test_streams_rgba_frames_without_cleaning_or_exporting_pngs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "sample.csv"
            csv_path.write_text(
                "year,country,value\n2000,USA,100\n2001,USA,110\n",
                encoding="utf-8",
            )
            chart_config = ChartConfig(
                frames_dir=str(temp_path / "frames"),
                output_file=str(temp_path / "video.mp4"),
                steps_per_transition=2,
                frame_output_mode="ffmpeg_stream",
            )
            data_source_config = DataSourceConfig(
                source_type="csv",
                csv_path=str(csv_path),
            )

            with patch("pipeline.render_job.clean_frame_directory") as clean:
                with patch("pipeline.render_job.BarRenderer") as renderer_class:
                    with patch("pipeline.render_job.VideoExporter") as exporter_class:
                        with patch("builtins.print"):
                            renderer = renderer_class.return_value
                            renderer.render_rgba.side_effect = [b"frame-0", b"frame-1"]
                            exporter = exporter_class.return_value
                            process = exporter.open_stream.return_value

                            result = RenderJob(
                                config=chart_config,
                                data_source_config=data_source_config,
                                dataset_config=DatasetConfig(),
                            ).run()

            self.assertEqual(result.frames_rendered, 2)
            self.assertEqual(result.removed_frames, 0)
            clean.assert_not_called()
            renderer.render.assert_not_called()
            self.assertEqual(renderer.render_rgba.call_count, 2)
            self.assertEqual(
                [call.args[0] for call in process.stdin.write.call_args_list],
                [b"frame-0", b"frame-1"],
            )
            exporter.finish_stream.assert_called_once_with(process)
            exporter.export.assert_not_called()

    def test_runs_pipeline_and_returns_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "sample.csv"
            frames_dir = temp_path / "frames"
            output_file = temp_path / "video.mp4"

            csv_path.write_text(
                "\n".join(
                    [
                        "year,country,value",
                        "2000,USA,100",
                        "2000,Mexico,80",
                        "2001,USA,90",
                        "2001,Mexico,95",
                    ]
                ),
                encoding="utf-8",
            )

            frames_dir.mkdir()
            (frames_dir / "frame_9999.png").write_text("old", encoding="utf-8")

            chart_config = ChartConfig(
                frames_dir=str(frames_dir),
                output_file=str(output_file),
                steps_per_transition=2,
                frame_output_mode="png_sequence",
            )
            data_source_config = DataSourceConfig(
                source_type="csv",
                csv_path=str(csv_path),
            )

            with patch("pipeline.render_job.BarRenderer") as renderer_class:
                with patch("pipeline.render_job.VideoExporter") as exporter_class:
                    with patch("builtins.print"):
                        renderer = renderer_class.return_value
                        exporter = exporter_class.return_value

                        result = RenderJob(
                            config=chart_config,
                            data_source_config=data_source_config,
                            dataset_config=DatasetConfig(),
                        ).run()

            self.assertEqual(result.frames_rendered, 2)
            self.assertEqual(result.transitions_rendered, 1)
            self.assertEqual(result.removed_frames, 1)
            self.assertEqual(result.output_file, str(output_file))
            self.assertGreaterEqual(result.profile.load_data_seconds, 0.0)
            self.assertGreaterEqual(result.profile.validate_data_seconds, 0.0)
            self.assertGreaterEqual(result.profile.build_timeline_seconds, 0.0)
            self.assertGreaterEqual(result.profile.cleanup_seconds, 0.0)
            self.assertGreaterEqual(result.profile.precompute_sprites_seconds, 0.0)
            self.assertGreaterEqual(result.profile.render_frames_seconds, 0.0)
            self.assertGreaterEqual(result.profile.draw_frames_seconds, 0.0)
            self.assertGreaterEqual(result.profile.save_frames_seconds, 0.0)
            self.assertGreaterEqual(result.profile.export_video_seconds, 0.0)
            self.assertGreaterEqual(result.profile.total_seconds, 0.0)
            self.assertLessEqual(
                result.profile.draw_frames_seconds + result.profile.save_frames_seconds,
                result.profile.render_frames_seconds,
            )
            self.assertAlmostEqual(
                result.average_frame_seconds,
                result.profile.render_frames_seconds / result.frames_rendered,
            )

            self.assertEqual(renderer.render.call_count, 2)
            self.assertEqual(
                renderer.render.call_args_list[0].kwargs["filename"],
                "frame_0000.png",
            )
            self.assertEqual(
                renderer.render.call_args_list[1].kwargs["filename"],
                "frame_0001.png",
            )
            renderer.close.assert_called_once_with()
            exporter.export.assert_called_once_with()

    def test_applies_bar_selection_before_rendering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "sample.csv"
            frames_dir = temp_path / "frames"
            output_file = temp_path / "video.mp4"

            csv_path.write_text(
                "\n".join(
                    [
                        "year,country,value",
                        "2000,USA,100",
                        "2000,Mexico,80",
                        "2000,Canada,60",
                        "2001,USA,90",
                        "2001,Mexico,95",
                        "2001,Canada,70",
                    ]
                ),
                encoding="utf-8",
            )

            chart_config = ChartConfig(
                frames_dir=str(frames_dir),
                output_file=str(output_file),
                steps_per_transition=2,
                frame_output_mode="png_sequence",
                selection=BarSelectionConfig(
                    top_n=1,
                    aggregate_other=True,
                    other_label="Other",
                ),
            )
            data_source_config = DataSourceConfig(
                source_type="csv",
                csv_path=str(csv_path),
            )

            with patch("pipeline.render_job.BarRenderer") as renderer_class:
                with patch("pipeline.render_job.VideoExporter"):
                    with patch("builtins.print"):
                        renderer = renderer_class.return_value

                        RenderJob(
                            config=chart_config,
                            data_source_config=data_source_config,
                            dataset_config=DatasetConfig(),
                        ).run()

            first_scene = renderer.render.call_args_list[0].args[0]
            visible_bars = [bar for bar in first_scene.bars if bar.opacity > 0]
            first_frame_names = [bar.name for bar in visible_bars]
            first_frame_values = {bar.name: bar.value for bar in visible_bars}

            self.assertEqual(first_frame_names, ["USA", "Other"])
            self.assertEqual(first_frame_values["Other"], 140)

    def test_applies_category_labels_and_colors_before_rendering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "sample.csv"
            frames_dir = temp_path / "frames"
            output_file = temp_path / "video.mp4"

            csv_path.write_text(
                "\n".join(
                    [
                        "year,country,value",
                        "2000,Coal,100",
                        "2000,Solar,50",
                        "2001,Coal,110",
                        "2001,Solar,60",
                    ]
                ),
                encoding="utf-8",
            )

            chart_config = ChartConfig(
                frames_dir=str(frames_dir),
                output_file=str(output_file),
                steps_per_transition=2,
                frame_output_mode="png_sequence",
            )
            data_source_config = DataSourceConfig(
                source_type="csv",
                csv_path=str(csv_path),
            )

            with patch("pipeline.render_job.BarRenderer") as renderer_class:
                with patch("pipeline.render_job.VideoExporter"):
                    with patch("builtins.print"):
                        renderer = renderer_class.return_value

                        RenderJob(
                            config=chart_config,
                            data_source_config=data_source_config,
                            dataset_config=DatasetConfig(
                                category_labels={"Coal": "Carbon"},
                                category_colors={"Coal": "#333333"},
                            ),
                        ).run()

            first_scene = renderer.render.call_args_list[0].args[0]
            bars_by_name = {bar.name: bar for bar in first_scene.bars}

            self.assertIn("Carbon", bars_by_name)
            self.assertEqual(bars_by_name["Carbon"].color, "#333333")
            self.assertIn("Solar", bars_by_name)

    def test_reports_render_progress(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "sample.csv"
            frames_dir = temp_path / "frames"
            output_file = temp_path / "video.mp4"

            csv_path.write_text(
                "\n".join(
                    [
                        "year,country,value",
                        "2000,USA,100",
                        "2001,USA,110",
                    ]
                ),
                encoding="utf-8",
            )

            chart_config = ChartConfig(
                frames_dir=str(frames_dir),
                output_file=str(output_file),
                steps_per_transition=2,
                frame_output_mode="png_sequence",
            )
            data_source_config = DataSourceConfig(
                source_type="csv",
                csv_path=str(csv_path),
            )
            progress_events = []

            with patch("pipeline.render_job.BarRenderer"):
                with patch("pipeline.render_job.VideoExporter"):
                    with patch("builtins.print"):
                        RenderJob(
                            config=chart_config,
                            data_source_config=data_source_config,
                            dataset_config=DatasetConfig(),
                            progress_callback=progress_events.append,
                        ).run()

            self.assertEqual(progress_events[0].stage, "load_data")
            self.assertEqual(progress_events[-1].stage, "complete")
            self.assertEqual(progress_events[-1].progress, 1.0)

            frame_events = [
                event
                for event in progress_events
                if event.stage == "render_frames" and event.current
            ]
            self.assertEqual([event.current for event in frame_events], [1, 2])
            self.assertTrue(all(event.total == 2 for event in frame_events))
            self.assertTrue(
                all(
                    earlier.progress <= later.progress
                    for earlier, later in zip(progress_events, progress_events[1:])
                )
            )

    def test_precomputes_sprites_once_per_year(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "sample.csv"
            frames_dir = temp_path / "frames"
            output_file = temp_path / "video.mp4"

            csv_path.write_text(
                "\n".join(
                    [
                        "year,country,value",
                        "2000,USA,100",
                        "2001,USA,110",
                        "2002,USA,120",
                    ]
                ),
                encoding="utf-8",
            )

            chart_config = ChartConfig(
                frames_dir=str(frames_dir),
                output_file=str(output_file),
                steps_per_transition=2,
                frame_output_mode="png_sequence",
            )
            data_source_config = DataSourceConfig(
                source_type="csv",
                csv_path=str(csv_path),
            )

            def build_sprites(bars):
                return [
                    BarSprite(
                        name=bar.name,
                        value=bar.value,
                        color="#123456",
                        x=100,
                        y=index * 20,
                        width=bar.value,
                        height=10,
                        rank=index + 1,
                    )
                    for index, bar in enumerate(bars)
                ]

            with patch("pipeline.render_job.BarSelector") as selector_class:
                with patch("pipeline.render_job.LayoutEngine") as layout_class:
                    with patch("pipeline.render_job.BarRenderer") as renderer_class:
                        with patch("pipeline.render_job.VideoExporter"):
                            with patch("builtins.print"):
                                selector = selector_class.return_value
                                selector.select.side_effect = lambda bars: bars

                                layout = layout_class.return_value
                                layout.build.side_effect = build_sprites

                                renderer = renderer_class.return_value

                                RenderJob(
                                    config=chart_config,
                                    data_source_config=data_source_config,
                                    dataset_config=DatasetConfig(),
                                ).run()

            self.assertEqual(selector.select.call_count, 3)
            self.assertEqual(layout.build.call_count, 3)
            self.assertEqual(renderer.render.call_count, 4)


if __name__ == "__main__":
    unittest.main()
