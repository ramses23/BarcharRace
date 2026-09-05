import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import _test_path
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.export_config import ExportConfig
from pipeline.render_job import RenderProfile, RenderResult
from studio.render_output import RenderOutputPromotionError, _filesystem_path
from studio.render_worker import _progress_writer, run_worker


class RenderWorkerTest(unittest.TestCase):
    def test_progress_status_failure_does_not_abort_render_callback(self):
        progress = SimpleNamespace(
            stage="render_frames",
            message="Drawing frames.",
            progress=0.25,
            current=1,
            total=4,
        )
        callback = _progress_writer(
            Path("status.json"),
            {"job_id": "job123"},
            minimum_interval=0,
        )

        with patch(
            "studio.render_worker.atomic_write_json",
            side_effect=PermissionError("temporarily locked"),
        ), patch("studio.render_worker.print") as warning:
            callback(progress)

        warning.assert_called_once()

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
                    rendered_paths.append(Path(config.output_file))

                def run(self):
                    Path(self.config.output_file).write_bytes(b"complete-video")
                    return RenderResult(
                        frames_rendered=2,
                        transitions_rendered=1,
                        removed_frames=0,
                        output_file=self.config.output_file,
                        profile=RenderProfile(total_seconds=1.0),
                    )

            rendered_paths = []
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
            self.assertEqual(len(rendered_paths), 1)
            self.assertEqual(rendered_paths[0].parent, final_output.parent)
            self.assertRegex(
                rendered_paths[0].name,
                r"^\.render\.[0-9a-f]{16}\.partial\.mp4$",
            )
            self.assertEqual(tuple(final_output.parent.glob("*.partial.mp4")), ())
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
            self.assertEqual(tuple(final_output.parent.glob("*.partial.mp4")), ())
            self.assertIn('"state": "failed"', status_path.read_text())

    def test_promotion_failure_preserves_completed_partial_and_previous_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = root / "project.json"
            project_path.write_text("{}", encoding="utf-8")
            status_path = root / "status.json"
            final_output = root / "output" / "video.mp4"
            final_output.parent.mkdir(parents=True)
            final_output.write_bytes(b"previous-video")
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

            def fail_promotion(partial_path, destination_path):
                cause = FileNotFoundError(
                    2,
                    "synthetic missing path",
                    _filesystem_path(partial_path),
                    3,
                    _filesystem_path(destination_path),
                )
                raise RenderOutputPromotionError(
                    partial_path,
                    destination_path,
                    cause,
                )

            with patch(
                "studio.render_worker.load_project_file",
                return_value=preset,
            ), patch(
                "studio.render_worker.RenderJob",
                SuccessfulRenderJob,
            ), patch(
                "studio.render_worker.promote_render_output",
                side_effect=fail_promotion,
            ), patch(
                "studio.render_worker.traceback.print_exception",
            ) as print_exception:
                return_code = run_worker(
                    project_path,
                    root,
                    status_path,
                    "job-promotion-failure",
                )

            partials = tuple(final_output.parent.glob("*.partial.mp4"))
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(return_code, 1)
            self.assertEqual(final_output.read_bytes(), b"previous-video")
            self.assertEqual(len(partials), 1)
            self.assertEqual(partials[0].read_bytes(), b"complete-video")
            self.assertEqual(status["state"], "failed")
            self.assertEqual(
                status["message"],
                "Render completed but final file promotion failed.",
            )
            self.assertTrue(status["temporary_output_preserved"])
            self.assertEqual(Path(status["temporary_output"]), partials[0])
            self.assertIn(str(partials[0]), status["error"])
            self.assertIn(str(final_output), status["error"])
            self.assertIn("WinError 3", status["error"])
            self.assertIn("synthetic missing path", status["error"])
            self.assertNotIn("\\\\?\\", status["error"])
            self.assertFalse(print_exception.call_args.kwargs["chain"])

    def test_short_render_uses_suffixed_output_and_preserves_standard_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = root / "project.json"
            project_path.write_text("{}", encoding="utf-8")
            status_path = root / "status.json"
            standard_output = root / "output" / "race.mp4"
            standard_output.parent.mkdir(parents=True)
            standard_output.write_bytes(b"standard-video")
            preset = SimpleNamespace(
                chart_config=ChartConfig(output_file="output/race.mp4"),
                data_source_config=DataSourceConfig(),
                dataset_config=DatasetConfig(),
                export_config=ExportConfig(mode="short"),
            )

            class SuccessfulShortRenderJob:
                def __init__(self, config, **kwargs):
                    self.config = config
                    self.output_file_is_effective = kwargs[
                        "output_file_is_effective"
                    ]

                def run(self):
                    Path(self.config.output_file).write_bytes(b"short-video")
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
                SuccessfulShortRenderJob,
            ):
                return_code = run_worker(
                    project_path,
                    root,
                    status_path,
                    "job789",
                )

            short_output = root / "output" / "race_short.mp4"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(return_code, 0)
            self.assertEqual(standard_output.read_bytes(), b"standard-video")
            self.assertEqual(short_output.read_bytes(), b"short-video")
            self.assertEqual(tuple(short_output.parent.glob("*.partial.mp4")), ())
            self.assertEqual(
                Path(status["output_file"]).resolve(),
                short_output.resolve(),
            )
            self.assertEqual(
                Path(status["result"]["output_file"]).resolve(),
                short_output.resolve(),
            )


if __name__ == "__main__":
    unittest.main()
