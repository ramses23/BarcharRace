import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import _test_path
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from pipeline.render_job import RenderProfile, RenderResult
from studio.render_worker import run_worker


class RenderWorkerTest(unittest.TestCase):
    def test_promotes_partial_video_only_after_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = root / "project.json"
            project_path.write_text("{}", encoding="utf-8")
            status_path = root / "status.json"
            preset = SimpleNamespace(
                chart_config=ChartConfig(output_file="output/video.mp4"),
                data_source_config=DataSourceConfig(),
                dataset_config=DatasetConfig(),
            )

            class SuccessfulRenderJob:
                def __init__(self, config, **_):
                    self.config = config

                def run(self):
                    Path(self.config.output_file).write_bytes(b"complete-video")
                    return RenderResult(
                        frames_rendered=2,
                        transitions_rendered=1,
                        removed_frames=0,
                        output_file=self.config.output_file,
                        profile=RenderProfile(total_seconds=1.0),
                    )

            with patch(
                "studio.render_worker.load_project_file",
                return_value=preset,
            ), patch(
                "studio.render_worker.RenderJob",
                SuccessfulRenderJob,
            ):
                return_code = run_worker(
                    project_path,
                    root,
                    status_path,
                    "job123",
                )

            final_output = root / "output" / "video.mp4"
            self.assertEqual(return_code, 0)
            self.assertEqual(final_output.read_bytes(), b"complete-video")
            self.assertFalse(
                (root / "output" / ".video.job123.partial.mp4").exists()
            )
            self.assertIn('"state": "completed"', status_path.read_text())

    def test_failure_preserves_previous_video_and_removes_partial(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = root / "project.json"
            project_path.write_text("{}", encoding="utf-8")
            status_path = root / "status.json"
            final_output = root / "output" / "video.mp4"
            final_output.parent.mkdir(parents=True, exist_ok=True)
            final_output.write_bytes(b"previous-video")
            preset = SimpleNamespace(
                chart_config=ChartConfig(output_file="output/video.mp4"),
                data_source_config=DataSourceConfig(),
                dataset_config=DatasetConfig(),
            )

            class FailingRenderJob:
                def __init__(self, config, **_):
                    self.config = config

                def run(self):
                    Path(self.config.output_file).write_bytes(b"partial-video")
                    raise RuntimeError("render failed")

            with patch(
                "studio.render_worker.load_project_file",
                return_value=preset,
            ), patch(
                "studio.render_worker.RenderJob",
                FailingRenderJob,
            ), patch(
                "studio.render_worker.traceback.print_exc",
            ):
                return_code = run_worker(
                    project_path,
                    root,
                    status_path,
                    "job456",
                )

            self.assertEqual(return_code, 1)
            self.assertEqual(final_output.read_bytes(), b"previous-video")
            self.assertFalse(
                (root / "output" / ".video.job456.partial.mp4").exists()
            )
            self.assertIn('"state": "failed"', status_path.read_text())


if __name__ == "__main__":
    unittest.main()
