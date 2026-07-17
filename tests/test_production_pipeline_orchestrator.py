import hashlib
import inspect
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import automation.orchestrator as orchestrator_module
from automation.brief_loader import load_production_brief
from automation.logo_resolver import LocalLogoResolver
from automation.orchestrator import (
    ProductionOrchestrationError,
    ProductionOrchestrator,
    ProductionRunProgress,
    ProductionRunResult,
)
from automation.production_preflight import ProductionPreflightRunner
from automation.project_assembler import ProductionProjectAssembler
from automation.registry import create_default_dataset_builder_registry
from automation.render_executor import (
    ProductionRenderProgress,
    ProductionRenderResult,
)
from automation.workspace import ProductionWorkspace
from pipeline.render_job import RenderProfile
from studio import render_preflight


SOURCE_FIXTURE = (
    TESTS_DIR / "automation" / "fixtures" / "national_team_goals_source.csv"
)
TEMPLATE_FIXTURE = (
    TESTS_DIR / "automation" / "fixtures" / "automation_project_template.json"
)


class FakeRenderExecutor:
    def __init__(self, *, status="completed", error=None, progress_callback=None):
        self.status = status
        self.error = error
        self.progress_callback = progress_callback
        self.run_calls = 0

    def run(self, *, assembly_result, preflight_result, project_root_dir):
        self.run_calls += 1
        if self.progress_callback is not None:
            self.progress_callback(
                ProductionRenderProgress(
                    state="running",
                    stage="render_frames",
                    message="Rendering synthetic worker frames.",
                    progress=0.5,
                    current=1,
                    total=2,
                )
            )
        if self.error is not None:
            raise self.error

        workspace = assembly_result.workspace
        if self.status == "completed":
            payload = b"synthetic-complete-video"
            workspace.video_path.write_bytes(payload)
            video_sha256 = hashlib.sha256(payload).hexdigest()
            video_size = len(payload)
            frame_count = 2
            transitions = 1
            fps = 5
            duration = 0.4
            profile = RenderProfile(total_seconds=0.1)
            video_manifest = {
                "path": workspace.video_path.relative_to(project_root_dir).as_posix(),
                "sha256": video_sha256,
                "size_bytes": video_size,
            }
        else:
            video_sha256 = None
            video_size = None
            frame_count = None
            transitions = None
            fps = None
            duration = None
            profile = None
            video_manifest = None

        workspace.publish_production_render_manifest(
            {
                "production_render_manifest_schema_version": 1,
                "project": {
                    "path": assembly_result.project_path.relative_to(
                        project_root_dir
                    ).as_posix(),
                    "sha256": assembly_result.project_sha256,
                },
                "preflight": {
                    "path": preflight_result.manifest_path.relative_to(
                        project_root_dir
                    ).as_posix(),
                    "status": preflight_result.status,
                },
                "video": video_manifest,
                "result": {"status": self.status},
                "warnings": [],
            }
        )
        return ProductionRenderResult(
            workspace=workspace,
            project_path=workspace.project_json_path,
            video_path=workspace.video_path,
            manifest_path=workspace.production_render_manifest_path,
            status=self.status,
            video_sha256=video_sha256,
            video_size_bytes=video_size,
            frame_count=frame_count,
            transitions_rendered=transitions,
            fps=fps,
            duration_seconds=duration,
            profile=profile,
            warnings=(),
        )


class RenderExecutorFactoryProbe:
    def __init__(self, *, status="completed", error=None):
        self.status = status
        self.error = error
        self.calls = 0
        self.progress_callback = None
        self.cancel_requested = None
        self.executor = None

    def __call__(self, *, progress_callback, cancel_requested):
        self.calls += 1
        self.progress_callback = progress_callback
        self.cancel_requested = cancel_requested
        self.executor = FakeRenderExecutor(
            status=self.status,
            error=self.error,
            progress_callback=progress_callback,
        )
        return self.executor


class ProductionPipelineOrchestratorTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()
        self.project_root = self.temp_path / "project-root"
        self.project_root.mkdir()
        self.jobs_root = (self.project_root / "output" / ".production_jobs").resolve()
        self.source_path = self.project_root / "production" / "inputs" / "source.csv"
        self.source_path.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE_FIXTURE, self.source_path)
        self.template_path = (
            self.project_root / "production" / "templates" / "template.json"
        )
        self.template_path.parent.mkdir(parents=True)
        shutil.copyfile(TEMPLATE_FIXTURE, self.template_path)

    def test_complete_flow_with_render(self):
        progress = []
        factory = RenderExecutorFactoryProbe()

        result = self.run_pipeline(
            render_factory=factory,
            progress_callback=progress.append,
        )

        self.assertIsInstance(result, ProductionRunResult)
        self.assertEqual(result.status, "completed")
        self.assertIsNone(result.logo_result)
        self.assertEqual(result.preflight_result.status, "ready")
        self.assertEqual(result.render_result.status, "completed")
        self.assertTrue(result.workspace.video_path.is_file())
        self.assertEqual(factory.calls, 1)
        self.assertEqual(factory.executor.run_calls, 1)
        self.assertEqual(
            [event.state for event in progress],
            [
                "dataset_running",
                "dataset_ready",
                "assets_ready",
                "project_ready",
                "preflight_ready",
                "rendering",
                "rendering",
                "completed",
            ],
        )

    def test_flow_without_logo_directories_skips_resolver(self):
        resolver = mock.Mock(wraps=LocalLogoResolver())

        result = self.run_pipeline(logo_resolver=resolver)

        resolver.resolve.assert_not_called()
        self.assertIsNone(result.logo_result)
        status = self.read_json(result.status_path)
        self.assertEqual(status["state"], "completed")

    def test_flow_with_local_logo_directory_invokes_resolver_once(self):
        logo_dir = self.project_root / "production" / "logos"
        logo_dir.mkdir()
        (logo_dir / "Alpha Republic.png").write_bytes(b"synthetic-logo")
        resolver = mock.Mock(wraps=LocalLogoResolver())

        result = self.run_pipeline(
            logo_resolver=resolver,
            primary_logo_dir="production/logos",
        )

        resolver.resolve.assert_called_once()
        self.assertIsNotNone(result.logo_result)
        self.assertTrue(result.logo_result.manifest_path.is_file())
        self.assertGreaterEqual(len(result.logo_result.primary_assets), 1)

    def test_flow_without_render_ends_preflight_ready(self):
        factory = RenderExecutorFactoryProbe()

        result = self.run_pipeline(render_enabled=False, render_factory=factory)

        self.assertEqual(result.status, "preflight_ready")
        self.assertIsNone(result.render_result)
        self.assertFalse(result.workspace.video_path.exists())
        factory_call_count = factory.calls
        self.assertEqual(factory_call_count, 0)
        self.assertEqual(self.read_json(result.status_path)["state"], "preflight_ready")

    def test_blocked_preflight_returns_without_render(self):
        factory = RenderExecutorFactoryProbe()
        checks = (
            render_preflight.PreflightCheck(
                "dataset",
                "Dataset",
                "error",
                "Synthetic blocking error.",
            ),
        )

        with mock.patch.object(
            render_preflight,
            "run_render_preflight",
            return_value=render_preflight.RenderPreflight("project.json", checks),
        ):
            result = self.run_pipeline(render_factory=factory)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.preflight_result.status, "blocked")
        self.assertIsNone(result.render_result)
        self.assertEqual(factory.calls, 0)
        self.assertFalse(result.workspace.video_path.exists())
        self.assertEqual(self.read_json(result.status_path)["state"], "blocked")

    def test_canceled_render_ends_canceled(self):
        cancel_requested = mock.Mock(return_value=True)
        factory = RenderExecutorFactoryProbe(status="canceled")

        result = self.run_pipeline(
            render_factory=factory,
            cancel_requested=cancel_requested,
        )

        self.assertEqual(result.status, "canceled")
        self.assertEqual(result.render_result.status, "canceled")
        self.assertIs(factory.cancel_requested, cancel_requested)
        self.assertFalse(result.workspace.video_path.exists())
        status = self.read_json(result.status_path)
        self.assertEqual(status["state"], "canceled")
        self.assertIn("render_manifest", status["artifacts"])
        self.assertNotIn("video", status["artifacts"])

    def test_each_component_is_invoked_exactly_once(self):
        logo_dir = self.project_root / "production" / "logos"
        logo_dir.mkdir()
        (logo_dir / "Alpha Republic.png").write_bytes(b"logo")
        resolver = mock.Mock(wraps=LocalLogoResolver())
        assembler = mock.Mock(wraps=ProductionProjectAssembler())
        preflight = mock.Mock(wraps=ProductionPreflightRunner())
        factory = RenderExecutorFactoryProbe()

        result = self.run_pipeline(
            logo_resolver=resolver,
            project_assembler=assembler,
            preflight_runner=preflight,
            render_factory=factory,
            primary_logo_dir="production/logos",
        )

        self.assertEqual(result.status, "completed")
        resolver.resolve.assert_called_once()
        assembler.assemble.assert_called_once()
        preflight.run.assert_called_once()
        self.assertEqual(factory.calls, 1)
        self.assertEqual(factory.executor.run_calls, 1)

    def test_general_statuses_are_published_in_valid_order(self):
        history = []
        original_replace = ProductionWorkspace.replace_status

        def record_status(workspace, data):
            history.append(data["state"])
            return original_replace(workspace, data)

        with mock.patch.object(
            ProductionWorkspace,
            "replace_status",
            autospec=True,
            side_effect=record_status,
        ):
            result = self.run_pipeline()

        self.assertEqual(
            history,
            [
                "dataset_running",
                "dataset_ready",
                "assets_ready",
                "project_ready",
                "preflight_ready",
                "rendering",
                "completed",
            ],
        )
        self.assertEqual(self.read_json(result.status_path)["state"], "completed")

    def test_final_status_has_only_relative_available_artifacts(self):
        result = self.run_pipeline()
        status = self.read_json(result.status_path)

        self.assertEqual(
            tuple(status["artifacts"]),
            (
                "dataset",
                "dataset_manifest",
                "project",
                "project_manifest",
                "preflight_manifest",
                "video",
                "render_manifest",
            ),
        )
        for value in status["artifacts"].values():
            self.assertNotIn("\\", value)
            self.assertNotIn(":", value)
            self.assertNotIn("..", Path(value).parts)
            self.assertFalse(Path(value).is_absolute())
        status_text = result.status_path.read_text(encoding="utf-8")
        self.assertNotIn(str(self.project_root), status_text)
        self.assertNotIn("timestamp", status_text.casefold())
        self.assertNotIn("pid", status_text.casefold())

    def test_dataset_failure_does_not_invoke_later_components(self):
        assembler = mock.Mock(wraps=ProductionProjectAssembler())
        orchestrator = self.orchestrator(project_assembler=assembler)
        brief = self.load_brief(job_id="dataset-failure")
        error = ProductionOrchestrationError("directed dataset failure")

        with mock.patch.object(
            ProductionOrchestrator,
            "prepare_dataset",
            autospec=True,
            side_effect=error,
        ):
            with self.assertRaises(ProductionOrchestrationError) as raised:
                orchestrator.run_production(
                    brief,
                    project_root_dir=self.project_root,
                    workspace_root_dir=self.jobs_root,
                    source_root_dir=self.project_root,
                )

        self.assertIs(raised.exception, error)
        assembler.assemble.assert_not_called()

    def test_assets_failure_records_failed_status_and_preserves_dataset(self):
        resolver = mock.Mock()
        resolver.resolve.side_effect = RuntimeError("assets failed")
        logo_dir = self.project_root / "production" / "logos"
        logo_dir.mkdir()
        brief = self.load_brief(
            job_id="assets-failure",
            primary_logo_dir="production/logos",
        )

        with self.assertRaises(ProductionOrchestrationError) as raised:
            self.orchestrator(logo_resolver=resolver).run_production(
                brief,
                project_root_dir=self.project_root,
                workspace_root_dir=self.jobs_root,
                source_root_dir=self.project_root,
            )

        self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        workspace = self.jobs_root / brief.job_id
        self.assertTrue((workspace / "dataset" / "dataset.csv").is_file())
        self.assertEqual(self.read_json(workspace / "status.json")["stage"], "assets")

    def test_project_failure_records_failed_status(self):
        assembler = mock.Mock()
        assembler.assemble.side_effect = RuntimeError("project failed")

        with self.assertRaises(ProductionOrchestrationError) as raised:
            self.run_pipeline(project_assembler=assembler)

        self.assertEqual(raised.exception.__cause__.args[0], "project failed")
        status = self.only_workspace_status()
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["stage"], "project")
        self.assertEqual(status["error"]["type"], "RuntimeError")

    def test_preflight_failure_records_failed_status_and_preserves_project(self):
        preflight = mock.Mock()
        preflight.run.side_effect = RuntimeError("preflight failed")

        with self.assertRaises(ProductionOrchestrationError):
            self.run_pipeline(preflight_runner=preflight)

        workspace = self.only_workspace_path()
        self.assertTrue((workspace / "project" / "project.json").is_file())
        status = self.read_json(workspace / "status.json")
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["stage"], "preflight")

    def test_render_failure_records_failed_status_and_preserves_prior_artifacts(self):
        factory = RenderExecutorFactoryProbe(error=RuntimeError("render failed"))

        with self.assertRaises(ProductionOrchestrationError) as raised:
            self.run_pipeline(render_factory=factory)

        self.assertEqual(raised.exception.__cause__.args[0], "render failed")
        workspace = self.only_workspace_path()
        self.assertTrue((workspace / "project" / "project.json").is_file())
        self.assertTrue(
            (workspace / "manifests" / "production_preflight.json").is_file()
        )
        status = self.read_json(workspace / "status.json")
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["stage"], "render")

    def test_failed_status_write_does_not_hide_stage_error(self):
        assembler = mock.Mock()
        original_error = RuntimeError("project failed")
        assembler.assemble.side_effect = original_error
        original_replace = ProductionWorkspace.replace_status

        def fail_failed_status(workspace, data):
            if data.get("state") == "failed":
                raise OSError("failed status write failed")
            return original_replace(workspace, data)

        with mock.patch.object(
            ProductionWorkspace,
            "replace_status",
            autospec=True,
            side_effect=fail_failed_status,
        ):
            with self.assertRaises(ProductionOrchestrationError) as raised:
                self.run_pipeline(project_assembler=assembler)

        self.assertIs(raised.exception.__cause__, original_error)
        self.assertIn("failed production status", " ".join(original_error.__notes__))

    def test_progress_values_are_immutable_and_bounded(self):
        progress = []

        self.run_pipeline(progress_callback=progress.append)

        self.assertTrue(all(isinstance(item, ProductionRunProgress) for item in progress))
        self.assertTrue(all(0 <= item.progress <= 1 for item in progress))
        self.assertTrue(all(isinstance(item.artifacts, tuple) for item in progress))
        with self.assertRaises(FrozenInstanceError):
            progress[-1].state = "changed"

    def test_result_is_deeply_immutable(self):
        result = self.run_pipeline()

        with self.assertRaises(FrozenInstanceError):
            result.status = "blocked"
        self.assertFalse(
            any(isinstance(value, (dict, list, set)) for value in result.__dict__.values())
        )

    def test_prepare_dataset_remains_available_for_v1(self):
        brief_data = self.brief_data(job_id="dataset-only")
        brief_data["production_brief_schema_version"] = 1
        del brief_data["assets"]
        del brief_data["project"]
        del brief_data["render"]
        brief = load_production_brief(
            self.write_brief(brief_data, name="v1.json"),
            root_dir=self.project_root,
        )

        result = self.orchestrator().prepare_dataset(
            brief,
            workspace_root_dir=self.jobs_root,
            source_root_dir=self.project_root,
        )

        self.assertTrue(result.build_result.csv_path.is_file())
        self.assertEqual(self.read_json(result.status_path)["state"], "dataset_ready")
        self.assertFalse(result.workspace.project_json_path.exists())

    def test_run_production_rejects_v1_without_workspace(self):
        data = self.brief_data(job_id="v1-rejected")
        data["production_brief_schema_version"] = 1
        del data["assets"]
        del data["project"]
        del data["render"]
        brief = load_production_brief(
            self.write_brief(data, name="v1-rejected.json"),
            root_dir=self.project_root,
        )

        with self.assertRaisesRegex(ProductionOrchestrationError, "preflight"):
            self.orchestrator().run_production(
                brief,
                project_root_dir=self.project_root,
                workspace_root_dir=self.jobs_root,
                source_root_dir=self.project_root,
            )

        self.assertFalse(self.jobs_root.exists())

    def test_complete_orchestration_uses_no_network(self):
        failure = AssertionError("network attempted")
        with mock.patch.object(
            socket,
            "create_connection",
            side_effect=failure,
        ), mock.patch.object(
            socket.socket,
            "connect",
            side_effect=failure,
        ):
            self.run_pipeline()

    def test_orchestrator_has_no_ui_git_ffmpeg_or_direct_render_job(self):
        source = inspect.getsource(orchestrator_module)
        lowered = source.casefold()

        self.assertNotIn("streamlit", lowered)
        self.assertNotIn("renderjob", source)
        self.assertNotIn("ffmpeg", lowered)
        self.assertNotIn("subprocess", lowered)
        self.assertNotIn("git ", lowered)

    def test_fake_render_does_not_spawn_processes(self):
        with mock.patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("subprocess attempted"),
        ), mock.patch.object(
            subprocess,
            "run",
            side_effect=AssertionError("subprocess attempted"),
        ):
            self.run_pipeline()

    def run_pipeline(
        self,
        *,
        render_enabled=True,
        render_factory=None,
        logo_resolver=None,
        project_assembler=None,
        preflight_runner=None,
        progress_callback=None,
        cancel_requested=None,
        primary_logo_dir=None,
    ):
        brief = self.load_brief(
            render_enabled=render_enabled,
            primary_logo_dir=primary_logo_dir,
        )
        orchestrator = self.orchestrator(
            render_factory=render_factory,
            logo_resolver=logo_resolver,
            project_assembler=project_assembler,
            preflight_runner=preflight_runner,
        )
        return orchestrator.run_production(
            brief,
            project_root_dir=self.project_root,
            workspace_root_dir=self.jobs_root,
            source_root_dir=self.project_root,
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
        )

    def orchestrator(
        self,
        *,
        render_factory=None,
        logo_resolver=None,
        project_assembler=None,
        preflight_runner=None,
    ):
        return ProductionOrchestrator(
            create_default_dataset_builder_registry(),
            logo_resolver_component=logo_resolver,
            project_assembler_component=project_assembler,
            preflight_runner_component=preflight_runner,
            render_executor_factory=render_factory or RenderExecutorFactoryProbe(),
        )

    def load_brief(
        self,
        *,
        job_id="pipeline-job",
        render_enabled=True,
        primary_logo_dir=None,
    ):
        data = self.brief_data(
            job_id=job_id,
            render_enabled=render_enabled,
            primary_logo_dir=primary_logo_dir,
        )
        return load_production_brief(
            self.write_brief(data),
            root_dir=self.project_root,
        )

    def brief_data(
        self,
        *,
        job_id="pipeline-job",
        render_enabled=True,
        primary_logo_dir=None,
    ):
        return {
            "production_brief_schema_version": 2,
            "job_id": job_id,
            "dataset": {
                "builder": "national_team_goals",
                "source_csv": "production/inputs/source.csv",
                "expected_source_sha256": None,
                "parameters": {
                    "start_year": 2000,
                    "end_year": 2001,
                    "mode": "cumulative",
                    "duplicate_policy": "warn",
                },
            },
            "assets": {
                "primary_logo_dir": primary_logo_dir,
                "secondary_logo_dir": None,
                "missing_policy": "allow",
            },
            "project": {
                "template": "production/templates/template.json",
                "name": "pipeline_project",
                "title": "Pipeline Project",
                "source_label": "Source: synthetic pipeline fixture",
            },
            "render": {"enabled": render_enabled},
        }

    def write_brief(self, data, *, name="brief.json"):
        path = self.project_root / "production" / name
        path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return path

    def only_workspace_path(self):
        workspaces = tuple(self.jobs_root.iterdir())
        self.assertEqual(len(workspaces), 1)
        return workspaces[0]

    def only_workspace_status(self):
        return self.read_json(self.only_workspace_path() / "status.json")

    @staticmethod
    def read_json(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
