import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
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


if __name__ == "__main__":
    unittest.main()
