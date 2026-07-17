import contextlib
import inspect
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from automation.brief_loader import ProductionBriefError, load_production_brief
from config.project_file_loader import load_project_file
from tools import run_production


EXAMPLE_BRIEF = (
    ROOT_DIR
    / "production"
    / "briefs"
    / "examples"
    / "national_team_goals_demo.json"
)
EXAMPLE_TEMPLATE = (
    ROOT_DIR / "production" / "templates" / "national_team_goals_demo.json"
)
EXAMPLE_SOURCE = (
    ROOT_DIR
    / "production"
    / "inputs"
    / "examples"
    / "national_team_goals_source.csv"
)


class FakeOrchestrator:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run_production(self, brief, **kwargs):
        self.calls.append((brief, kwargs))
        return self.result


class RunProductionCliTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()
        self.root = self.temp_path / "root"
        self.root.mkdir()
        self.brief_path = self.root / "brief.json"
        self.brief_path.write_text("{}\n", encoding="utf-8")

    def test_successful_cli_composes_loader_registry_and_orchestrator(self):
        brief = object()
        result = self.fake_result("completed", with_video=True)
        orchestrator = FakeOrchestrator(result)
        options = SimpleNamespace(brief=Path("brief.json"), root=self.root)

        with mock.patch.object(
            run_production,
            "load_production_brief",
            return_value=brief,
        ) as loader, mock.patch.object(
            run_production,
            "create_production_orchestrator",
            return_value=orchestrator,
        ) as factory:
            actual = run_production.run_from_options(options)

        self.assertIs(actual, result)
        loader.assert_called_once_with(self.brief_path, root_dir=self.root)
        factory.assert_called_once_with()
        self.assertEqual(len(orchestrator.calls), 1)
        called_brief, kwargs = orchestrator.calls[0]
        self.assertIs(called_brief, brief)
        self.assertEqual(kwargs["project_root_dir"], self.root)
        self.assertEqual(kwargs["source_root_dir"], self.root)
        self.assertEqual(
            kwargs["workspace_root_dir"],
            (self.root / "output" / ".production_jobs").resolve(),
        )
        self.assertIs(kwargs["progress_callback"], run_production.print_progress)

    def test_success_exit_codes(self):
        for status in ("completed", "preflight_ready"):
            with self.subTest(status=status):
                self.assertEqual(self.main_with_status(status), 0)

    def test_blocked_exit_code(self):
        self.assertEqual(self.main_with_status("blocked"), 2)

    def test_canceled_exit_code(self):
        self.assertEqual(self.main_with_status("canceled"), 3)

    def test_unknown_result_status_is_technical_failure(self):
        self.assertEqual(self.main_with_status("unexpected"), 1)

    def test_missing_brief_returns_technical_failure(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = run_production.main(
                [
                    "--brief",
                    "missing.json",
                    "--root",
                    str(self.root),
                ]
            )

        self.assertEqual(code, 1)
        self.assertIn("Production failed", stderr.getvalue())

    def test_invalid_brief_returns_technical_failure(self):
        stderr = io.StringIO()
        with mock.patch.object(
            run_production,
            "run_from_options",
            side_effect=ProductionBriefError("invalid brief"),
        ), contextlib.redirect_stderr(stderr):
            code = run_production.main(
                ["--brief", "brief.json", "--root", str(self.root)]
            )

        self.assertEqual(code, 1)
        self.assertIn("invalid brief", stderr.getvalue())

    def test_orchestration_failure_returns_technical_failure(self):
        stderr = io.StringIO()
        with mock.patch.object(
            run_production,
            "run_from_options",
            side_effect=RuntimeError("technical failure"),
        ), contextlib.redirect_stderr(stderr):
            code = run_production.main(
                ["--brief", "brief.json", "--root", str(self.root)]
            )

        self.assertEqual(code, 1)
        self.assertIn("technical failure", stderr.getvalue())

        from automation.orchestrator import ProductionOrchestrationError

        with mock.patch.object(
            run_production,
            "run_from_options",
            side_effect=ProductionOrchestrationError("pipeline failed"),
        ), contextlib.redirect_stderr(stderr):
            code = run_production.main(
                ["--brief", "brief.json", "--root", str(self.root)]
            )

        self.assertEqual(code, 1)
        self.assertIn("pipeline failed", stderr.getvalue())

    def test_help_is_available(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            run_production.main(["--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("--brief", stdout.getvalue())
        self.assertIn("--root", stdout.getvalue())

    def test_final_output_lists_required_artifacts(self):
        result = self.fake_result("completed", with_video=True)
        stdout = io.StringIO()

        with mock.patch.object(
            run_production,
            "run_from_options",
            return_value=result,
        ), contextlib.redirect_stdout(stdout):
            code = run_production.main(
                ["--brief", "brief.json", "--root", str(self.root)]
            )

        text = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("State: completed", text)
        self.assertIn("Workspace:", text)
        self.assertIn("Project:", text)
        self.assertIn("Preflight: ready", text)
        self.assertIn("MP4:", text)

    def test_blocked_output_reports_no_mp4(self):
        result = self.fake_result("blocked", with_video=False, preflight="blocked")
        stdout = io.StringIO()

        with mock.patch.object(
            run_production,
            "run_from_options",
            return_value=result,
        ), contextlib.redirect_stdout(stdout):
            code = run_production.main(
                ["--brief", "brief.json", "--root", str(self.root)]
            )

        self.assertEqual(code, 2)
        self.assertIn("MP4: not produced", stdout.getvalue())

    def test_progress_output_is_readable(self):
        progress = SimpleNamespace(
            state="rendering",
            message="Rendering frames.",
            current=3,
            total=10,
        )
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            run_production.print_progress(progress)

        self.assertEqual(stdout.getvalue(), "[rendering] Rendering frames. (3/10)\n")

    def test_cli_is_a_thin_composition_layer(self):
        source = inspect.getsource(run_production)

        for forbidden in (
            ".prepare_dataset(",
            ".resolve(\n",
            ".assemble(",
            "RenderJob",
            "subprocess",
            "streamlit",
            "ffmpeg",
            "pandas",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertEqual(source.count(".run_production("), 1)

    def test_tracked_example_brief_is_valid_v2(self):
        brief = load_production_brief(EXAMPLE_BRIEF, root_dir=ROOT_DIR)

        self.assertEqual(brief.schema_version, 2)
        self.assertEqual(brief.job_id, "national-team-goals-demo")
        self.assertEqual(brief.dataset.source_csv, EXAMPLE_SOURCE.resolve())
        self.assertEqual(brief.project.template_path, EXAMPLE_TEMPLATE.resolve())
        self.assertIsNone(brief.assets.primary_logo_dir)
        self.assertIsNone(brief.assets.secondary_logo_dir)
        self.assertTrue(brief.render.enabled)

    def test_tracked_example_project_is_loadable_and_small(self):
        preset = load_project_file(EXAMPLE_TEMPLATE)

        self.assertEqual(preset.chart_config.width, 320)
        self.assertEqual(preset.chart_config.height, 180)
        self.assertEqual(preset.chart_config.fps, 5)
        self.assertEqual(preset.chart_config.steps_per_transition, 1)
        self.assertEqual(preset.chart_config.frame_output_mode, "ffmpeg_stream")
        self.assertFalse(preset.chart_config.logos_enabled)

    def test_tracked_example_is_independent_of_tests_and_personal_paths(self):
        files = tuple((ROOT_DIR / "production").rglob("*"))
        tracked_files = tuple(path for path in files if path.is_file())
        self.assertGreaterEqual(len(tracked_files), 4)

        for path in tracked_files:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertNotIn("tests/", text)
                self.assertNotIn("tests\\", text)
                self.assertNotIn(str(Path.home()), text)
                self.assertNotIn(str(ROOT_DIR), text)
                self.assertNotRegex(text, r"(?i)[a-z]:[\\/]")

    def test_example_source_is_synthetic_and_bounded(self):
        rows = EXAMPLE_SOURCE.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(rows), 7)
        self.assertIn("Alpha Republic", "\n".join(rows))
        self.assertNotIn("http://", "\n".join(rows))
        self.assertNotIn("https://", "\n".join(rows))

    def main_with_status(self, status):
        result = self.fake_result(
            status,
            with_video=status == "completed",
            preflight="blocked" if status == "blocked" else "ready",
        )
        with mock.patch.object(
            run_production,
            "run_from_options",
            return_value=result,
        ), contextlib.redirect_stdout(io.StringIO()):
            return run_production.main(
                ["--brief", "brief.json", "--root", str(self.root)]
            )

    def fake_result(self, status, *, with_video=False, preflight="ready"):
        workspace = SimpleNamespace(root_path=self.root / "workspace")
        assembly = SimpleNamespace(project_path=self.root / "workspace" / "project.json")
        preflight_result = SimpleNamespace(
            status=preflight,
            manifest_path=self.root / "workspace" / "preflight.json",
        )
        render_result = None
        if status in ("completed", "canceled"):
            render_result = SimpleNamespace(
                status=status,
                video_path=self.root / "workspace" / "video.mp4",
            )
        return SimpleNamespace(
            status=status,
            workspace=workspace,
            assembly_result=assembly,
            preflight_result=preflight_result,
            render_result=render_result if with_video or status == "canceled" else None,
        )


if __name__ == "__main__":
    unittest.main()
