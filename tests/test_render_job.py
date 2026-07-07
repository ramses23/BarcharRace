import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from config.bar_selection_config import BarSelectionConfig
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from models.bar_sprite import BarSprite
from pipeline.render_job import RenderJob


class RenderJobTest(unittest.TestCase):
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
            self.assertGreaterEqual(result.profile.export_video_seconds, 0.0)
            self.assertGreaterEqual(result.profile.total_seconds, 0.0)

            self.assertEqual(renderer.render.call_count, 2)
            self.assertEqual(
                renderer.render.call_args_list[0].kwargs["filename"],
                "frame_0000.png",
            )
            self.assertEqual(
                renderer.render.call_args_list[1].kwargs["filename"],
                "frame_0001.png",
            )
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
