import hashlib
import inspect
import json
import socket
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import automation.render_executor as render_executor_module
from automation.brief_loader import load_production_brief
from automation.models import FrozenParameters
from automation.orchestrator import ProductionOrchestrator
from automation.production_preflight import (
    PRODUCTION_PREFLIGHT_MANIFEST_SCHEMA_VERSION,
    ProductionPreflightIssue,
    ProductionPreflightResult,
    ProductionPreflightRunner,
)
from automation.project_assembler import (
    PROJECT_ASSEMBLY_MANIFEST_SCHEMA_VERSION,
    ProductionProjectAssembler,
    ProjectAssemblyOptions,
    ProjectAssemblyResult,
)
from automation.registry import create_default_dataset_builder_registry
from automation.render_executor import (
    PRODUCTION_RENDER_MANIFEST_SCHEMA_VERSION,
    ProductionRenderError,
    ProductionRenderExecutor,
    ProductionRenderProgress,
    ProductionRenderResult,
)
from automation.workspace import ProductionWorkspace
from pipeline.render_job import RenderProfile
from ui.render_controller import start_background_render as real_start_background_render


FIXTURES_DIR = TESTS_DIR / "automation" / "fixtures"
VALID_BRIEF_PATH = FIXTURES_DIR / "valid_production_brief.json"


class FakeBackgroundRender:
    def __init__(self, statuses, *, on_status=None):
        self.statuses = list(statuses)
        self.on_status = on_status
        self.status_calls = 0
        self.cancel_calls = 0
        self.pid = 1234
        self.status_path = Path("worker-status.json")
        self.log_path = Path("render.log")

    def status(self):
        index = min(self.status_calls, len(self.statuses) - 1)
        value = self.statuses[index]
        self.status_calls += 1
        if self.on_status is not None:
            self.on_status(value)
        return value

    def is_running(self):
        return False

    def cancel(self):
        self.cancel_calls += 1
        return {
            "state": "canceled",
            "stage": "canceled",
            "message": "Render canceled by the user.",
            "progress": 0.25,
            "current": 1,
            "total": 4,
        }


class ProductionRenderExecutorTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()
        self.project_root = self.temp_path / "production-root"
        self.project_root.mkdir()
        self.context = self.make_context(self.project_root)

    def test_success_uses_existing_controller_and_reconstruction_api(self):
        handle = self.success_handle(self.context)
        progress = []
        executor = ProductionRenderExecutor(
            poll_interval_seconds=0,
            progress_callback=progress.append,
        )
        real_adapter = render_executor_module.render_result_from_status

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ) as start, mock.patch.object(
            render_executor_module,
            "render_result_from_status",
            wraps=real_adapter,
        ) as adapt:
            result = executor.run(
                assembly_result=self.context.assembly,
                preflight_result=self.context.preflight,
                project_root_dir=self.project_root,
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.frame_count, 2)
        self.assertEqual(result.fps, 5)
        self.assertEqual(result.duration_seconds, 0.4)
        start.assert_called_once_with(
            self.context.workspace.project_json_path,
            root_dir=self.project_root,
        )
        adapt.assert_called_once()
        self.assertGreaterEqual(handle.status_calls, 2)
        self.assertEqual([item.state for item in progress], ["running", "completed"])
        self.assertTrue(all(isinstance(item, ProductionRenderProgress) for item in progress))

    def test_worker_is_launched_exactly_once(self):
        handle = self.success_handle(self.context)

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ) as start:
            self.run_executor()

        start.assert_called_once()

    def test_blocked_preflight_starts_nothing_and_creates_nothing(self):
        issue = ProductionPreflightIssue(
            "ffmpeg",
            "FFmpeg",
            "error",
            "FFmpeg unavailable.",
        )
        blocked = replace(
            self.context.preflight,
            status="blocked",
            errors=(issue,),
            error_count=1,
        )

        with mock.patch.object(render_executor_module, "start_background_render") as start:
            with self.assertRaises(ProductionRenderError) as raised:
                self.run_executor(preflight=blocked)

        self.assertEqual(raised.exception.stage, "validation")
        start.assert_not_called()
        self.assertFalse(self.context.workspace.video_path.exists())
        self.assertFalse(
            self.context.workspace.production_render_manifest_path.exists()
        )

    def test_assembly_and_preflight_from_different_workspaces_are_rejected(self):
        other = self.make_context(self.project_root, job_id="other-render-job")

        with mock.patch.object(render_executor_module, "start_background_render") as start:
            with self.assertRaises(ProductionRenderError):
                self.run_executor(preflight=other.preflight)

        start.assert_not_called()

    def test_project_changed_after_preflight_is_rejected(self):
        self.context.workspace.project_json_path.write_text(
            self.context.workspace.project_json_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
            newline="\n",
        )

        with mock.patch.object(render_executor_module, "start_background_render") as start:
            with self.assertRaises(ProductionRenderError) as raised:
                self.run_executor()

        self.assertIsInstance(raised.exception.__cause__, ValueError)
        start.assert_not_called()

    def test_incorrect_configured_output_is_rejected(self):
        assembly = self.rewrite_project_output("render/wrong.mp4")

        with mock.patch.object(render_executor_module, "start_background_render") as start:
            with self.assertRaises(ProductionRenderError) as raised:
                self.run_executor(assembly=assembly)

        self.assertIn("workspace.video_path", str(raised.exception.__cause__))
        start.assert_not_called()

    def test_preexisting_video_is_rejected(self):
        self.context.workspace.video_path.write_bytes(b"existing")

        with mock.patch.object(render_executor_module, "start_background_render") as start:
            with self.assertRaises(ProductionRenderError):
                self.run_executor()

        start.assert_not_called()
        self.assertEqual(self.context.workspace.video_path.read_bytes(), b"existing")

    def test_preexisting_manifest_is_rejected(self):
        self.context.workspace.publish_production_render_manifest({"existing": True})

        with mock.patch.object(render_executor_module, "start_background_render") as start:
            with self.assertRaises(ProductionRenderError):
                self.run_executor()

        start.assert_not_called()

    def test_preexisting_partial_is_rejected(self):
        partial = self.context.workspace.render_dir / ".video.partial.mp4"
        partial.write_bytes(b"partial")

        with mock.patch.object(render_executor_module, "start_background_render") as start:
            with self.assertRaises(ProductionRenderError):
                self.run_executor()

        start.assert_not_called()

    def test_worker_error_preserves_structured_information(self):
        handle = FakeBackgroundRender(
            (
                {
                    "state": "failed",
                    "stage": "failed",
                    "message": "Render failed.",
                    "error": "RuntimeError: synthetic failure",
                    "progress": 0.4,
                    "current": 2,
                    "total": 5,
                },
            )
        )

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ):
            with self.assertRaises(ProductionRenderError) as raised:
                self.run_executor()

        error = raised.exception
        self.assertEqual(error.stage, "worker")
        self.assertEqual(error.worker_state, "failed")
        self.assertEqual(error.worker_message, "Render failed.")
        self.assertEqual(error.worker_error, "RuntimeError: synthetic failure")
        self.assertIsInstance(error.__cause__, RuntimeError)
        self.assertFalse(self.context.workspace.video_path.exists())
        self.assertFalse(
            self.context.workspace.production_render_manifest_path.exists()
        )

    def test_failed_worker_with_partial_still_raises_production_render_error(self):
        partial = self.context.workspace.render_dir / ".video.job.partial.mp4"

        def create_partial(_status):
            partial.write_bytes(b"partial")

        handle = FakeBackgroundRender(
            (
                {
                    "state": "failed",
                    "stage": "failed",
                    "message": "Render failed.",
                    "error": "RuntimeError: synthetic failure",
                    "progress": 0.4,
                    "current": 2,
                    "total": 5,
                },
            ),
            on_status=create_partial,
        )

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ):
            with self.assertRaises(ProductionRenderError) as raised:
                self.run_executor()

        self.assertEqual(raised.exception.stage, "worker")
        self.assertIsInstance(raised.exception.__cause__, FileExistsError)
        self.assertTrue(partial.exists())

    def test_cancellation_uses_background_render_cancel(self):
        handle = FakeBackgroundRender(
            (
                {
                    "state": "running",
                    "stage": "render_frames",
                    "message": "Rendering.",
                    "progress": 0.25,
                    "current": 1,
                    "total": 4,
                },
            )
        )
        executor = ProductionRenderExecutor(
            poll_interval_seconds=0,
            cancel_requested=lambda: True,
        )

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ):
            result = executor.run(
                assembly_result=self.context.assembly,
                preflight_result=self.context.preflight,
                project_root_dir=self.project_root,
            )

        self.assertEqual(handle.cancel_calls, 1)
        self.assertEqual(result.status, "canceled")
        self.assertIsNone(result.video_sha256)
        self.assertIsNone(result.profile)
        manifest = self.read_json(result.manifest_path)
        self.assertEqual(manifest["result"], {"status": "canceled"})
        self.assertIsNone(manifest["video"])

    def test_missing_mp4_after_reported_success_is_error(self):
        handle = self.success_handle(self.context, create_video=False)

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ):
            with self.assertRaises(ProductionRenderError) as raised:
                self.run_executor()

        self.assertEqual(raised.exception.stage, "adaptation")
        self.assertIsInstance(raised.exception.__cause__, FileNotFoundError)

    def test_mp4_directory_after_reported_success_is_error(self):
        def create_directory(status):
            if status.get("state") == "completed" and not self.context.workspace.video_path.exists():
                self.context.workspace.video_path.mkdir()

        handle = FakeBackgroundRender(
            self.success_statuses(self.context),
            on_status=create_directory,
        )

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ):
            with self.assertRaises(ProductionRenderError) as raised:
                self.run_executor()

        self.assertIn("not a regular file", str(raised.exception.__cause__))

    def test_residual_partial_after_success_is_error(self):
        partial = self.context.workspace.render_dir / ".video.job.partial.mp4"

        def create_outputs(status):
            if status.get("state") == "completed":
                self.context.workspace.video_path.write_bytes(b"video")
                partial.write_bytes(b"partial")

        handle = FakeBackgroundRender(
            self.success_statuses(self.context),
            on_status=create_outputs,
        )

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ):
            with self.assertRaises(ProductionRenderError):
                self.run_executor()

        self.assertTrue(partial.exists())
        self.assertFalse(
            self.context.workspace.production_render_manifest_path.exists()
        )

    def test_video_hash_and_size_are_correct(self):
        payload = b"deterministic-video-payload"
        handle = self.success_handle(self.context, video_payload=payload)

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ):
            result = self.run_executor()

        self.assertEqual(result.video_sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(result.video_size_bytes, len(payload))
        manifest = self.read_json(result.manifest_path)
        self.assertEqual(manifest["video"]["sha256"], result.video_sha256)
        self.assertEqual(manifest["video"]["size_bytes"], len(payload))

    def test_manifest_is_relative_deterministic_and_machine_neutral(self):
        first_handle = self.success_handle(self.context, video_payload=b"same")
        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=first_handle,
        ):
            first = self.run_executor()
        first_payload = first.manifest_path.read_bytes()

        second_root = self.temp_path / "equivalent-root"
        second_root.mkdir()
        second = self.make_context(second_root)
        second_handle = self.success_handle(second, video_payload=b"same")
        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=second_handle,
        ):
            second_result = ProductionRenderExecutor(poll_interval_seconds=0).run(
                assembly_result=second.assembly,
                preflight_result=second.preflight,
                project_root_dir=second_root,
            )

        self.assertEqual(first_payload, second_result.manifest_path.read_bytes())
        manifest_text = first_payload.decode("utf-8")
        self.assertNotIn(str(self.project_root), manifest_text)
        self.assertNotIn("timestamp", manifest_text.casefold())
        self.assertNotIn("pid", manifest_text.casefold())
        manifest = json.loads(manifest_text)
        for value in (
            manifest["project"]["path"],
            manifest["preflight"]["path"],
            manifest["video"]["path"],
        ):
            self.assertNotIn("\\", value)
            self.assertNotIn(":", value)
            self.assertNotIn("..", PurePathParts(value))

    def test_manifest_is_utf8_without_bom_and_ends_in_lf(self):
        handle = self.success_handle(self.context)
        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ):
            result = self.run_executor()

        payload = result.manifest_path.read_bytes()
        self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(payload.endswith(b"\n"))
        payload.decode("utf-8")

    def test_manifest_publication_failure_preserves_valid_mp4(self):
        payload = b"valid-video"
        handle = self.success_handle(self.context, video_payload=payload)

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ), mock.patch.object(
            ProductionWorkspace,
            "publish_production_render_manifest",
            side_effect=OSError("publication failed"),
        ):
            with self.assertRaises(ProductionRenderError) as raised:
                self.run_executor()

        self.assertEqual(raised.exception.stage, "manifest")
        self.assertEqual(self.context.workspace.video_path.read_bytes(), payload)
        self.assertFalse(
            self.context.workspace.production_render_manifest_path.exists()
        )

    def test_partial_manifest_is_removed_after_publication_failure(self):
        handle = self.success_handle(self.context)
        manifest_path = self.context.workspace.production_render_manifest_path

        def publish_partial(_workspace, _data):
            manifest_path.write_text("{partial", encoding="utf-8")
            raise OSError("publication failed")

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ), mock.patch.object(
            ProductionWorkspace,
            "publish_production_render_manifest",
            new=publish_partial,
        ):
            with self.assertRaises(ProductionRenderError):
                self.run_executor()

        self.assertFalse(manifest_path.exists())
        self.assertTrue(self.context.workspace.video_path.is_file())

    def test_project_dataset_preflight_logos_and_status_are_unchanged(self):
        workspace = self.context.workspace
        paths = (
            self.context.assembly.project_path,
            self.context.assembly.dataset_path,
            self.context.assembly.manifest_path,
            self.context.preflight.manifest_path,
            workspace.status_path,
            workspace.workspace_manifest_path,
        )
        before = {path: path.read_bytes() for path in paths}
        logo_tree_before = tuple(workspace.logos_dir.rglob("*"))
        handle = self.success_handle(self.context)

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ):
            self.run_executor()

        self.assertEqual({path: path.read_bytes() for path in paths}, before)
        self.assertEqual(tuple(workspace.logos_dir.rglob("*")), logo_tree_before)

    def test_general_status_change_during_render_is_rejected(self):
        handle = self.success_handle(self.context)
        original_action = handle.on_status

        def mutate_status(status):
            original_action(status)
            if status.get("state") == "completed":
                self.context.workspace.replace_status({"state": "rendering"})

        handle.on_status = mutate_status
        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ):
            with self.assertRaises(ProductionRenderError) as raised:
                self.run_executor()

        self.assertIn("general production status", str(raised.exception.__cause__))

    def test_result_is_deeply_immutable(self):
        handle = self.success_handle(self.context)
        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ):
            result = self.run_executor()

        self.assertIsInstance(result, ProductionRenderResult)
        self.assertIsInstance(result.warnings, tuple)
        self.assertIsInstance(result.profile, RenderProfile)
        with self.assertRaises(FrozenInstanceError):
            result.status = "canceled"
        with self.assertRaises(FrozenInstanceError):
            result.profile.total_seconds = 99
        self.assertFalse(
            any(isinstance(value, (dict, list, set)) for value in result.__dict__.values())
        )

    def test_executor_does_not_import_or_call_forbidden_surfaces(self):
        source = inspect.getsource(render_executor_module)
        lowered = source.casefold()

        self.assertNotIn("streamlit", lowered)
        self.assertNotIn("renderjob", source)
        self.assertNotIn("subprocess", lowered)
        self.assertNotIn("ffmpeg", lowered)
        self.assertNotIn("git ", lowered)

    def test_executor_uses_no_network(self):
        handle = self.success_handle(self.context)
        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            return_value=handle,
        ), mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network attempted"),
        ), mock.patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("network attempted"),
        ):
            self.run_executor()

    def test_real_minimal_pipeline_generates_valid_mp4(self):
        integration_root = self.temp_path / "real-integration"
        integration_root.mkdir()
        template_path = integration_root / "templates" / "tiny.json"
        template_path.parent.mkdir()
        self.write_json(self.tiny_project_data(integration_root, "placeholder"), template_path)

        loaded_brief = load_production_brief(VALID_BRIEF_PATH, root_dir=ROOT_DIR)
        brief = replace(
            loaded_brief,
            job_id="tiny-render-integration",
            dataset=replace(
                loaded_brief.dataset,
                parameters=FrozenParameters.from_mapping(
                    {
                        "duplicate_policy": "warn",
                        "end_year": 2001,
                        "mode": "cumulative",
                        "start_year": 2000,
                    }
                ),
            ),
        )
        dataset_result = ProductionOrchestrator(
            create_default_dataset_builder_registry()
        ).prepare_dataset(
            brief,
            workspace_root_dir=integration_root / "jobs",
            source_root_dir=ROOT_DIR,
        )
        assembly = ProductionProjectAssembler().assemble(
            dataset_result=dataset_result,
            template_project_path=template_path.resolve(),
            project_root_dir=integration_root.resolve(),
            options=ProjectAssemblyOptions(
                project_name="tiny_render",
                title="Tiny Render",
                source_label="Source: integration fixture",
            ),
        )
        preflight = ProductionPreflightRunner().run(
            assembly_result=assembly,
            project_root_dir=integration_root.resolve(),
        )
        self.assertEqual(preflight.status, "ready")
        status_before = assembly.workspace.status_path.read_bytes()
        handles = []

        def launch(project_file, *, root_dir):
            handle = real_start_background_render(
                project_file,
                root_dir=root_dir,
                worker_path=ROOT_DIR / "src" / "studio" / "render_worker.py",
            )
            handles.append(handle)
            return handle

        with mock.patch.object(
            render_executor_module,
            "start_background_render",
            side_effect=launch,
        ) as start:
            result = ProductionRenderExecutor(poll_interval_seconds=0.02).run(
                assembly_result=assembly,
                preflight_result=preflight,
                project_root_dir=integration_root.resolve(),
            )

        start.assert_called_once()
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.frame_count, 1)
        self.assertEqual(result.transitions_rendered, 1)
        self.assertEqual(result.fps, 5)
        self.assertEqual(result.duration_seconds, 0.2)
        self.assertGreater(result.video_size_bytes, 0)
        payload = result.video_path.read_bytes()
        self.assertEqual(payload[4:8], b"ftyp")
        self.assertEqual(assembly.workspace.status_path.read_bytes(), status_before)
        self.assertFalse(handles[0].is_running())
        self.assertEqual(tuple(assembly.workspace.render_dir.glob("*.partial.mp4")), ())
        self.assertEqual(tuple(integration_root.rglob("*.tmp")), ())

    def run_executor(self, *, assembly=None, preflight=None):
        return ProductionRenderExecutor(poll_interval_seconds=0).run(
            assembly_result=assembly or self.context.assembly,
            preflight_result=preflight or self.context.preflight,
            project_root_dir=self.project_root,
        )

    def make_context(self, project_root, *, job_id="render-test-job"):
        project_root = Path(project_root).resolve()
        workspace = ProductionWorkspace.create(
            job_id=job_id,
            root_dir=project_root / "jobs",
        )
        workspace.dataset_csv_path.write_text(
            "period,category,value\n2000,Alpha,1\n2001,Alpha,2\n",
            encoding="utf-8",
            newline="\n",
        )
        template_path = project_root / "templates" / f"{job_id}.json"
        template_path.parent.mkdir(exist_ok=True)
        project_data = self.tiny_project_data(project_root, job_id)
        self.write_json(project_data, template_path)
        self.write_json(project_data, workspace.project_json_path)
        project_sha256 = self.sha256(workspace.project_json_path)
        project_size = workspace.project_json_path.stat().st_size
        project_reference = workspace.project_json_path.relative_to(project_root).as_posix()
        output_reference = workspace.video_path.relative_to(project_root).as_posix()
        workspace.publish_project_assembly_manifest(
            {
                "project_assembly_manifest_schema_version": (
                    PROJECT_ASSEMBLY_MANIFEST_SCHEMA_VERSION
                ),
                "project": {
                    "path": project_reference,
                    "sha256": project_sha256,
                    "size_bytes": project_size,
                },
                "output": {"path": output_reference},
            }
        )
        assembly = ProjectAssemblyResult(
            workspace=workspace,
            project_path=workspace.project_json_path,
            manifest_path=workspace.project_assembly_manifest_path,
            template_path=template_path.resolve(),
            dataset_path=workspace.dataset_csv_path,
            output_path=workspace.video_path,
            project_sha256=project_sha256,
            project_size_bytes=project_size,
            category_count=1,
            primary_logo_count=0,
            secondary_logo_count=0,
            warnings=(),
        )
        workspace.publish_production_preflight_manifest(
            {
                "production_preflight_manifest_schema_version": (
                    PRODUCTION_PREFLIGHT_MANIFEST_SCHEMA_VERSION
                ),
                "project": {
                    "path": project_reference,
                    "sha256": project_sha256,
                },
                "render_output": {"path": output_reference},
                "status": "ready",
                "ffmpeg_available": True,
                "error_count": 0,
                "warning_count": 0,
                "errors": [],
                "warnings": [],
            }
        )
        preflight = ProductionPreflightResult(
            workspace=workspace,
            project_path=workspace.project_json_path,
            manifest_path=workspace.production_preflight_manifest_path,
            status="ready",
            errors=(),
            warnings=(),
            output_path=workspace.video_path,
            ffmpeg_available=True,
            error_count=0,
            warning_count=0,
        )
        return SimpleNamespace(
            workspace=workspace,
            assembly=assembly,
            preflight=preflight,
        )

    def rewrite_project_output(self, output_reference):
        project_path = self.context.workspace.project_json_path
        project = self.read_json(project_path)
        project["chart"]["output_file"] = output_reference
        self.write_json(project, project_path)
        project_sha256 = self.sha256(project_path)
        project_size = project_path.stat().st_size
        assembly_manifest = self.read_json(self.context.assembly.manifest_path)
        assembly_manifest["project"]["sha256"] = project_sha256
        assembly_manifest["project"]["size_bytes"] = project_size
        self.write_json(assembly_manifest, self.context.assembly.manifest_path)
        preflight_manifest = self.read_json(self.context.preflight.manifest_path)
        preflight_manifest["project"]["sha256"] = project_sha256
        self.write_json(preflight_manifest, self.context.preflight.manifest_path)
        return replace(
            self.context.assembly,
            project_sha256=project_sha256,
            project_size_bytes=project_size,
        )

    def success_handle(self, context, *, create_video=True, video_payload=b"video"):
        def create_output(status):
            if (
                create_video
                and status.get("state") == "completed"
                and not context.workspace.video_path.exists()
            ):
                context.workspace.video_path.write_bytes(video_payload)

        return FakeBackgroundRender(
            self.success_statuses(context),
            on_status=create_output,
        )

    @staticmethod
    def success_statuses(context):
        return (
            {
                "state": "running",
                "stage": "render_frames",
                "message": "Rendering frames.",
                "progress": 0.5,
                "current": 1,
                "total": 2,
            },
            {
                "state": "completed",
                "stage": "complete",
                "message": "Video rendered successfully.",
                "progress": 1.0,
                "current": 2,
                "total": 2,
                "result": {
                    "frames_rendered": 2,
                    "transitions_rendered": 1,
                    "removed_frames": 0,
                    "output_file": str(context.workspace.video_path),
                    "profile": asdict(RenderProfile(total_seconds=0.5)),
                },
            },
        )

    @staticmethod
    def tiny_project_data(project_root, job_id):
        workspace_root = project_root / "jobs" / job_id
        return {
            "schema_version": 1,
            "name": "tiny_render_project",
            "base_preset": "csv_sample",
            "chart": {
                "title": "Tiny render",
                "output_file": (workspace_root / "render" / "video.mp4")
                .relative_to(project_root)
                .as_posix(),
                "frames_dir": (workspace_root / "render" / "frames")
                .relative_to(project_root)
                .as_posix(),
                "layout_preset": "compact_dashboard",
                "width": 320,
                "height": 180,
                "dpi": 100,
                "left_margin": 80,
                "right_margin": 24,
                "top_margin": 55,
                "bottom_margin": 28,
                "bar_height": 22,
                "bar_gap": 4,
                "title_y": 12,
                "subtitle_y": 30,
                "time_label_x": 260,
                "time_label_y": 145,
                "source_x": 80,
                "source_y": 165,
                "title_font_size": 12,
                "subtitle_font_size": 8,
                "time_label_font_size": 18,
                "source_font_size": 7,
                "label_font_size": 8,
                "value_font_size": 8,
                "rank_labels_enabled": False,
                "logos_enabled": False,
                "bar_shadow_enabled": False,
                "bar_gradient_enabled": False,
                "frame_output_mode": "ffmpeg_stream",
                "fps": 5,
                "steps_per_transition": 1,
                "max_visible_bars": 2,
            },
            "animation": {
                "easing": "linear",
                "enter_exit": False,
                "value_smoothing": True,
                "motion_mode": "transition_easing",
            },
            "selection": {
                "top_n": 2,
                "aggregate_other": False,
            },
            "data_source": {
                "source_type": "csv",
                "csv_path": (workspace_root / "dataset" / "dataset.csv")
                .relative_to(project_root)
                .as_posix(),
                "source_label_override": "Source: tiny fixture",
            },
            "dataset": {
                "year_column": "period",
                "name_column": "category",
                "value_column": "value",
            },
        }

    @staticmethod
    def read_json(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def write_json(data, path):
        Path(path).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    @staticmethod
    def sha256(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def PurePathParts(value):
    return Path(value).parts


if __name__ == "__main__":
    unittest.main()
