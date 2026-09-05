import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import _test_path
from pipeline.render_job import RenderProfile
from studio.project_storage import atomic_write_json
from studio.render_output import _filesystem_path
from ui.render_controller import (
    BackgroundRender,
    render_result_from_status,
    start_background_render,
)


class RenderControllerTest(unittest.TestCase):
    def test_starts_worker_with_status_and_log_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = root / "project.json"
            project_path.write_text("{}", encoding="utf-8")
            worker_path = root / "worker.py"
            worker_path.write_text("pass\n", encoding="utf-8")
            process = Mock(pid=1234)
            process.poll.return_value = None

            with patch(
                "ui.render_controller.subprocess.Popen",
                return_value=process,
            ) as popen:
                handle = start_background_render(
                    project_path,
                    root_dir=root,
                    worker_path=worker_path,
                )

            command = popen.call_args.args[0]
            self.assertIn(str(project_path.resolve()), command)
            self.assertIn(str(handle.status_path), command)
            self.assertTrue(handle.log_path.is_file())
            self.assertEqual(handle.status()["state"], "starting")
            self.assertTrue(handle.is_running())

    def test_cancel_terminates_tree_and_removes_partial_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            status_path = root / "status.json"
            partial_output = root / ".video.partial.mp4"
            partial_output.write_bytes(b"partial")
            atomic_write_json(
                {
                    "state": "running",
                    "progress": 0.4,
                    "temporary_output": str(partial_output),
                },
                status_path,
            )
            process = Mock(pid=1234)
            process.poll.return_value = None
            handle = BackgroundRender(
                job_id="job",
                project_file=str(root / "project.json"),
                status_path=status_path,
                log_path=root / "render.log",
                process=process,
            )

            with patch("ui.render_controller._terminate_process_tree") as terminate:
                status = handle.cancel()

            terminate.assert_called_once_with(process)
            self.assertEqual(status["state"], "canceled")
            self.assertFalse(partial_output.exists())

    def test_unexpected_exit_preserves_completed_recoverable_partial(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            partial_output = root / ".render.0123456789abcdef.partial.mp4"
            final_output = root / "race.mp4"
            partial_output.write_bytes(b"completed-video")
            handle = self._finished_handle(
                root,
                {
                    "state": "running",
                    "stage": "complete",
                    "progress": 1.0,
                    "temporary_output": str(partial_output),
                    "output_file": str(final_output),
                },
            )

            status = handle.status()

            self.assertEqual(status["state"], "failed")
            self.assertEqual(
                status["message"],
                "Render output could not be finalized.",
            )
            self.assertTrue(status["temporary_output_preserved"])
            self.assertEqual(status["temporary_output_recovery"], "completed")
            self.assertEqual(partial_output.read_bytes(), b"completed-video")
            self.assertIn(str(partial_output), status["error"])
            self.assertIn(str(final_output), status["error"])

    def test_monitoring_failure_cancel_preserves_potentially_recoverable_partial(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            status_path = root / "status.json"
            partial_output = root / ".render.0123456789abcdef.partial.mp4"
            partial_output.write_bytes(b"possibly-complete-video")
            atomic_write_json(
                {
                    "state": "running",
                    "stage": "export_video",
                    "temporary_output": str(partial_output),
                },
                status_path,
            )
            process = Mock(pid=1234)
            process.poll.return_value = None
            handle = BackgroundRender(
                job_id="job",
                project_file=str(root / "project.json"),
                status_path=status_path,
                log_path=root / "render.log",
                process=process,
            )

            with patch("ui.render_controller._terminate_process_tree") as terminate:
                status = handle.cancel(preserve_temporary_output=True)

            terminate.assert_called_once_with(process)
            self.assertEqual(status["state"], "canceled")
            self.assertTrue(status["temporary_output_preserved"])
            self.assertEqual(status["temporary_output_recovery"], "potential")
            self.assertEqual(
                partial_output.read_bytes(),
                b"possibly-complete-video",
            )

    def test_unexpected_exit_preserves_uncertain_partial_without_claiming_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            partial_output = root / ".render.0123456789abcdef.partial.mp4"
            partial_output.write_bytes(b"possibly-incomplete")
            handle = self._finished_handle(
                root,
                {
                    "state": "running",
                    "stage": "export_video",
                    "progress": 0.92,
                    "temporary_output": str(partial_output),
                    "output_file": str(root / "race.mp4"),
                },
            )

            status = handle.status()

            self.assertTrue(partial_output.exists())
            self.assertEqual(status["temporary_output_recovery"], "potential")
            self.assertIn("potentially recoverable", status["error"])
            self.assertNotIn("A recoverable temporary", status["error"])

    def test_unexpected_exit_without_partial_reports_normal_process_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            handle = self._finished_handle(
                root,
                {
                    "state": "running",
                    "stage": "load_data",
                    "temporary_output": str(root / ".render.missing.partial.mp4"),
                },
            )

            status = handle.status()

            self.assertEqual(status["message"], "Render worker exited with code 1.")
            self.assertNotIn("temporary_output_preserved", status)

    @unittest.skipUnless(os.name == "nt", "Windows display paths only")
    def test_controller_recovery_error_never_exposes_extended_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            partial_output = root / ".render.0123456789abcdef.partial.mp4"
            final_output = root / "race.mp4"
            partial_output.write_bytes(b"completed-video")
            handle = self._finished_handle(
                root,
                {
                    "state": "running",
                    "stage": "complete",
                    "temporary_output": _filesystem_path(partial_output),
                    "output_file": _filesystem_path(final_output),
                },
            )

            status = handle.status()

            self.assertNotIn("\\\\?\\", status["error"])
            self.assertIn(str(partial_output), status["error"])
            self.assertIn(str(final_output), status["error"])

    @staticmethod
    def _finished_handle(root, status):
        status_path = root / "status.json"
        atomic_write_json(status, status_path)
        process = Mock(pid=1234)
        process.poll.return_value = 1
        return BackgroundRender(
            job_id="job",
            project_file=str(root / "project.json"),
            status_path=status_path,
            log_path=root / "render.log",
            process=process,
        )

    def test_deserializes_completed_render_result(self):
        status = {
            "state": "completed",
            "result": {
                "frames_rendered": 12,
                "transitions_rendered": 3,
                "removed_frames": 0,
                "output_file": "output/video.mp4",
                "profile": RenderProfile(total_seconds=2.5).__dict__,
            },
        }

        result = render_result_from_status(status)

        self.assertEqual(result.frames_rendered, 12)
        self.assertEqual(result.output_file, "output/video.mp4")
        self.assertEqual(result.profile.total_seconds, 2.5)


if __name__ == "__main__":
    unittest.main()
