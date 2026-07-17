import hashlib
import inspect
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest import mock

import pandas as pd


TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import automation.production_preflight as production_preflight_module
from automation.brief_loader import load_production_brief
from automation.logo_resolver import LocalLogoResolver
from automation.orchestrator import ProductionOrchestrator
from automation.production_preflight import (
    PRODUCTION_PREFLIGHT_MANIFEST_SCHEMA_VERSION,
    ProductionPreflightError,
    ProductionPreflightIssue,
    ProductionPreflightResult,
    ProductionPreflightRunner,
)
from automation.project_assembler import (
    ProductionProjectAssembler,
    ProjectAssemblyOptions,
)
from automation.registry import create_default_dataset_builder_registry
from automation.workspace import ProductionWorkspace
from studio import render_preflight


FIXTURES_DIR = TESTS_DIR / "automation" / "fixtures"
VALID_BRIEF_PATH = FIXTURES_DIR / "valid_production_brief.json"
TEMPLATE_FIXTURE_PATH = FIXTURES_DIR / "automation_project_template.json"


class ProductionPreflightRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()
        self.project_root = self.temp_path / "production-root"
        self.project_root.mkdir()
        self.assembly_result = self.prepare_assembly(self.project_root)
        self.runner = ProductionPreflightRunner()

    def test_real_preflight_succeeds_with_assembled_project(self):
        result = self.run_real()

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.error_count, 0)
        self.assertTrue(result.ffmpeg_available)
        self.assertTrue(result.manifest_path.is_file())

    def test_ready_result_when_no_errors(self):
        result = self.run_mocked(self.ready_checks())

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.errors, ())

    def test_blocked_result_does_not_raise(self):
        checks = self.ready_checks() + (
            self.check("dataset", "Dataset", "error", "Dataset is invalid."),
        )

        result = self.run_mocked(checks)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.error_count, 1)
        self.assertTrue(result.manifest_path.is_file())

    def test_warning_does_not_block(self):
        checks = self.ready_checks() + (
            self.check("logos", "Category logos", "warning", "One logo is missing."),
        )

        result = self.run_mocked(checks)

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.warning_count, 1)

    def test_result_is_frozen(self):
        result = self.run_mocked(self.ready_checks())

        with self.assertRaises(FrozenInstanceError):
            result.status = "blocked"

    def test_issue_is_frozen(self):
        issue = ProductionPreflightIssue("logos", "Logos", "warning", "Missing.")

        with self.assertRaises(FrozenInstanceError):
            issue.message = "changed"

    def test_errors_and_warnings_are_immutable_tuples(self):
        checks = self.ready_checks() + (
            self.check("z-error", "Z error", "error", "Blocked."),
            self.check("z-warning", "Z warning", "warning", "Warning."),
        )

        result = self.run_mocked(checks)

        self.assertIsInstance(result.errors, tuple)
        self.assertIsInstance(result.warnings, tuple)
        self.assertIsInstance(result.errors[0], ProductionPreflightIssue)
        self.assertIsInstance(result.warnings[0], ProductionPreflightIssue)

    def test_result_retains_no_mutable_or_internal_preflight_objects(self):
        result = self.run_mocked(self.ready_checks())

        self.assertFalse(
            any(
                isinstance(
                    value,
                    (dict, list, set, render_preflight.RenderPreflight),
                )
                for value in result.__dict__.values()
            )
        )

    def test_error_and_warning_counts_are_correct(self):
        checks = self.ready_checks() + (
            self.check("first", "First", "error", "First error."),
            self.check("second", "Second", "error", "Second error."),
            self.check("warning", "Warning", "warning", "One warning."),
        )

        result = self.run_mocked(checks)

        self.assertEqual(result.error_count, 2)
        self.assertEqual(result.warning_count, 1)

    def test_ffmpeg_available_from_ok_check(self):
        result = self.run_mocked(self.ready_checks(ffmpeg_available=True))

        self.assertTrue(result.ffmpeg_available)

    def test_ffmpeg_unavailable_from_error_check(self):
        result = self.run_mocked(self.ready_checks(ffmpeg_available=False))

        self.assertFalse(result.ffmpeg_available)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0].key, "ffmpeg")

    def test_result_paths_are_absolute_and_canonical(self):
        result = self.run_mocked(self.ready_checks())
        workspace = self.assembly_result.workspace

        self.assertEqual(result.project_path, workspace.project_json_path)
        self.assertEqual(
            result.manifest_path,
            workspace.production_preflight_manifest_path,
        )
        self.assertEqual(result.output_path, workspace.video_path)
        self.assertTrue(result.project_path.is_absolute())
        self.assertTrue(result.manifest_path.is_absolute())
        self.assertTrue(result.output_path.is_absolute())

    def test_manifest_uses_independent_version_one(self):
        result = self.run_mocked(self.ready_checks())
        manifest = self.manifest(result)

        self.assertEqual(PRODUCTION_PREFLIGHT_MANIFEST_SCHEMA_VERSION, 1)
        self.assertEqual(manifest["production_preflight_manifest_schema_version"], 1)

    def test_manifest_records_ready_status(self):
        manifest = self.manifest(self.run_mocked(self.ready_checks()))

        self.assertEqual(manifest["status"], "ready")
        self.assertEqual(manifest["errors"], [])

    def test_manifest_records_blocked_status(self):
        checks = self.ready_checks() + (
            self.check("periods", "Timeline", "error", "Only one period."),
        )
        manifest = self.manifest(self.run_mocked(checks))

        self.assertEqual(manifest["status"], "blocked")
        self.assertEqual(manifest["error_count"], 1)

    def test_manifest_records_project_hash(self):
        result = self.run_mocked(self.ready_checks())
        manifest = self.manifest(result)

        self.assertEqual(manifest["project"]["sha256"], self.sha256(result.project_path))

    def test_manifest_records_output_path(self):
        result = self.run_mocked(self.ready_checks())
        manifest = self.manifest(result)

        self.assertEqual(
            manifest["render_output"]["path"],
            result.output_path.relative_to(self.project_root).as_posix(),
        )

    def test_requires_project_assembly_result(self):
        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.runner.run(
                assembly_result=object(),
                project_root_dir=self.project_root.resolve(),
            )

    def test_rejects_relative_project_root(self):
        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks(), project_root_dir=Path("relative"))

    def test_rejects_missing_project_root(self):
        missing = (self.temp_path / "missing-root").resolve()

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks(), project_root_dir=missing)

    def test_rejects_project_root_file(self):
        root_file = self.temp_path / "root-file"
        root_file.write_text("file", encoding="utf-8")

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks(), project_root_dir=root_file.resolve())

    def test_rejects_workspace_and_project_outside_root(self):
        other_root = self.temp_path / "other-root"
        other_root.mkdir()

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks(), project_root_dir=other_root.resolve())

    def test_rejects_missing_project(self):
        self.assembly_result.project_path.unlink()

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

    def test_rejects_project_directory(self):
        self.assembly_result.project_path.unlink()
        self.assembly_result.project_path.mkdir()

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

    def test_rejects_project_hash_mismatch(self):
        changed = replace(self.assembly_result, project_sha256="0" * 64)

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks(), assembly_result=changed)

    def test_rejects_project_size_mismatch(self):
        changed = replace(
            self.assembly_result,
            project_size_bytes=self.assembly_result.project_size_bytes + 1,
        )

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks(), assembly_result=changed)

    def test_rejects_missing_assembly_manifest(self):
        self.assembly_result.manifest_path.unlink()

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

    def test_rejects_assembly_manifest_directory(self):
        self.assembly_result.manifest_path.unlink()
        self.assembly_result.manifest_path.mkdir()

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

    def test_rejects_tampered_assembly_manifest(self):
        manifest = self.read_json(self.assembly_result.manifest_path)
        manifest["project"]["sha256"] = "0" * 64
        self.write_json(manifest, self.assembly_result.manifest_path)

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

    def test_rejects_missing_dataset(self):
        self.assembly_result.dataset_path.unlink()

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

    def test_rejects_dataset_directory(self):
        self.assembly_result.dataset_path.unlink()
        self.assembly_result.dataset_path.mkdir()

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

    def test_rejects_dataset_hash_mismatch_from_manifest(self):
        manifest = self.read_json(self.assembly_result.manifest_path)
        manifest["dataset"]["sha256"] = "0" * 64
        self.write_json(manifest, self.assembly_result.manifest_path)

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

    def test_rejects_missing_referenced_logo(self):
        self.logo_paths[0].unlink()

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

    def test_rejects_missing_logo_resolution_manifest(self):
        self.assembly_result.workspace.logo_resolution_manifest_path.unlink()

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

    def test_rejects_non_dataset_ready_status(self):
        status = self.read_json(self.assembly_result.workspace.status_path)
        status["state"] = "failed"
        self.write_json(status, self.assembly_result.workspace.status_path)

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

    def test_rejects_status_for_other_job(self):
        status = self.read_json(self.assembly_result.workspace.status_path)
        status["job_id"] = "other-job"
        self.write_json(status, self.assembly_result.workspace.status_path)

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

    def test_rejects_preexisting_preflight_manifest_without_overwrite(self):
        path = self.assembly_result.workspace.production_preflight_manifest_path
        path.write_text("existing manifest", encoding="utf-8")

        with self.assertRaisesRegex(ProductionPreflightError, "validation"):
            self.run_mocked(self.ready_checks())

        self.assertEqual(path.read_text(encoding="utf-8"), "existing manifest")

    def test_reloads_project_before_running_preflight(self):
        with mock.patch.object(
            production_preflight_module,
            "load_project_file",
            wraps=production_preflight_module.load_project_file,
        ) as loader:
            self.run_mocked(self.ready_checks())

        loader.assert_called_once_with(self.assembly_result.project_path)

    def test_project_reload_failure_is_contextualized(self):
        with mock.patch.object(
            production_preflight_module,
            "load_project_file",
            side_effect=ValueError("project invalid"),
        ):
            with self.assertRaisesRegex(
                ProductionPreflightError,
                "validation",
            ) as caught:
                self.run_mocked(self.ready_checks())

        self.assertIsInstance(caught.exception.__cause__, ValueError)

    def test_run_render_preflight_is_invoked_exactly_once(self):
        with mock.patch.object(
            render_preflight,
            "run_render_preflight",
            return_value=self.raw_preflight(self.ready_checks()),
        ) as run:
            self.runner.run(
                assembly_result=self.assembly_result,
                project_root_dir=self.project_root.resolve(),
            )

        run.assert_called_once_with(
            self.assembly_result.project_path,
            root_dir=self.project_root.resolve(),
        )

    def test_preflight_exception_is_contextualized_with_cause(self):
        with mock.patch.object(
            render_preflight,
            "run_render_preflight",
            side_effect=OSError("preflight failed"),
        ):
            with self.assertRaisesRegex(
                ProductionPreflightError,
                "preflight",
            ) as caught:
                self.runner.run(
                    assembly_result=self.assembly_result,
                    project_root_dir=self.project_root.resolve(),
                )

        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertFalse(
            self.assembly_result.workspace.production_preflight_manifest_path.exists()
        )

    def test_invalid_preflight_result_is_technical_failure(self):
        with mock.patch.object(
            render_preflight,
            "run_render_preflight",
            return_value=object(),
        ):
            with self.assertRaisesRegex(ProductionPreflightError, "adaptation"):
                self.runner.run(
                    assembly_result=self.assembly_result,
                    project_root_dir=self.project_root.resolve(),
                )

    def test_invalid_preflight_check_is_technical_failure(self):
        invalid = render_preflight.RenderPreflight(
            str(self.assembly_result.project_path),
            (object(),),
        )

        with mock.patch.object(
            render_preflight,
            "run_render_preflight",
            return_value=invalid,
        ):
            with self.assertRaisesRegex(ProductionPreflightError, "adaptation"):
                self.runner.run(
                    assembly_result=self.assembly_result,
                    project_root_dir=self.project_root.resolve(),
                )

    def test_unknown_check_level_is_technical_failure(self):
        checks = (
            self.check("future", "Future", "notice", "Unknown level."),
        )

        with self.assertRaisesRegex(ProductionPreflightError, "adaptation"):
            self.run_mocked(checks)

    def test_manifest_publication_failure_is_contextualized(self):
        with mock.patch.object(
            ProductionWorkspace,
            "publish_production_preflight_manifest",
            side_effect=OSError("publication failed"),
        ):
            with self.assertRaisesRegex(
                ProductionPreflightError,
                "manifest",
            ) as caught:
                self.run_mocked(self.ready_checks())

        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertFalse(
            self.assembly_result.workspace.production_preflight_manifest_path.exists()
        )

    def test_failure_after_complete_publication_is_considered_published(self):
        original = ProductionWorkspace.publish_production_preflight_manifest

        def publish_then_raise(workspace, data):
            original(workspace, data)
            raise OSError("temporary cleanup failed")

        with mock.patch.object(
            ProductionWorkspace,
            "publish_production_preflight_manifest",
            new=publish_then_raise,
        ):
            result = self.run_mocked(self.ready_checks())

        self.assertEqual(result.status, "ready")
        self.assertTrue(result.manifest_path.is_file())

    def test_partial_manifest_is_removed_after_publication_failure(self):
        path = self.assembly_result.workspace.production_preflight_manifest_path

        def publish_partial(_workspace, _data):
            path.write_text("{partial", encoding="utf-8")
            raise OSError("publication failed")

        with mock.patch.object(
            ProductionWorkspace,
            "publish_production_preflight_manifest",
            new=publish_partial,
        ):
            with self.assertRaises(ProductionPreflightError):
                self.run_mocked(self.ready_checks())

        self.assertFalse(path.exists())

    def test_partial_cleanup_failure_preserves_original_cause(self):
        path = self.assembly_result.workspace.production_preflight_manifest_path
        original_unlink = Path.unlink

        def publish_partial(_workspace, _data):
            path.write_text("{partial", encoding="utf-8")
            raise OSError("publication failed")

        def fail_manifest_unlink(candidate, *args, **kwargs):
            if candidate == path:
                raise PermissionError("cleanup blocked")
            return original_unlink(candidate, *args, **kwargs)

        with mock.patch.object(
            ProductionWorkspace,
            "publish_production_preflight_manifest",
            new=publish_partial,
        ), mock.patch.object(Path, "unlink", new=fail_manifest_unlink):
            with self.assertRaises(ProductionPreflightError) as caught:
                self.run_mocked(self.ready_checks())

        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertTrue(
            any(
                "cleanup" in note.casefold()
                for note in caught.exception.__cause__.__notes__
            )
        )
        path.unlink(missing_ok=True)

    def test_project_dataset_logos_and_status_are_unchanged(self):
        paths = (
            self.assembly_result.project_path,
            self.assembly_result.dataset_path,
            self.assembly_result.manifest_path,
            self.assembly_result.workspace.logo_resolution_manifest_path,
            self.assembly_result.workspace.status_path,
            *self.logo_paths,
        )
        before = {path: path.read_bytes() for path in paths}

        self.run_mocked(self.ready_checks())

        self.assertEqual({path: path.read_bytes() for path in paths}, before)

    def test_blocked_preflight_does_not_modify_inputs(self):
        paths = (
            self.assembly_result.project_path,
            self.assembly_result.dataset_path,
            self.assembly_result.workspace.status_path,
        )
        before = {path: path.read_bytes() for path in paths}
        checks = self.ready_checks() + (
            self.check("periods", "Timeline", "error", "Blocked."),
        )

        result = self.run_mocked(checks)

        self.assertEqual(result.status, "blocked")
        self.assertEqual({path: path.read_bytes() for path in paths}, before)

    def test_status_remains_dataset_ready(self):
        before = self.assembly_result.workspace.status_path.read_bytes()

        self.run_mocked(self.ready_checks())

        self.assertEqual(self.assembly_result.workspace.status_path.read_bytes(), before)
        self.assertEqual(json.loads(before)["state"], "dataset_ready")

    def test_no_mp4_or_frames_are_created(self):
        workspace = self.assembly_result.workspace

        self.run_mocked(self.ready_checks())

        self.assertFalse(workspace.video_path.exists())
        self.assertEqual(tuple(workspace.render_dir.iterdir()), ())

    def test_result_preserves_raw_message_but_manifest_sanitizes_root(self):
        raw_message = f"Missing image: {self.project_root / 'backgrounds' / 'missing.png'}"
        checks = self.ready_checks() + (
            self.check("background", "Background", "error", raw_message),
        )

        result = self.run_mocked(checks)
        manifest = self.manifest(result)

        self.assertEqual(result.errors[0].message, raw_message)
        self.assertNotIn(str(self.project_root), manifest["errors"][0]["message"])
        self.assertIn("<project_root>", manifest["errors"][0]["message"])

    def test_manifest_omits_external_absolute_path_details(self):
        checks = self.ready_checks() + (
            self.check(
                "background",
                "Background",
                "error",
                "Missing image: C:/Users/example/private.png",
            ),
        )

        manifest = self.manifest(self.run_mocked(checks))

        self.assertNotIn("C:/Users", manifest["errors"][0]["message"])
        self.assertIn("omitted", manifest["errors"][0]["message"])

    def test_manifest_paths_are_relative_posix(self):
        result = self.run_mocked(self.ready_checks())
        manifest = self.manifest(result)

        for value in (
            manifest["project"]["path"],
            manifest["render_output"]["path"],
        ):
            with self.subTest(value=value):
                self.assertNotIn("\\", value)
                self.assertNotIn(":", value)
                self.assertFalse(Path(value).is_absolute())
                self.assertNotIn("..", Path(value).parts)

    def test_manifest_contains_no_personal_machine_or_time_data(self):
        text = self.run_mocked(self.ready_checks()).manifest_path.read_text(
            encoding="utf-8"
        )

        self.assertNotIn(str(self.project_root), text)
        self.assertNotIn("timestamp", text.casefold())
        self.assertNotIn("created_at", text.casefold())
        self.assertNotIn("pid", text.casefold())

    def test_manifest_json_is_utf8_without_bom_and_ends_in_lf(self):
        payload = self.run_mocked(self.ready_checks()).manifest_path.read_bytes()

        self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(payload.endswith(b"\n"))
        payload.decode("utf-8")

    def test_manifest_issue_order_is_deterministic(self):
        checks = self.ready_checks() + (
            self.check("zeta", "Zeta", "error", "Last."),
            self.check("alpha", "Alpha", "error", "First."),
            self.check("z-warning", "Z warning", "warning", "Last warning."),
            self.check("a-warning", "A warning", "warning", "First warning."),
        )

        manifest = self.manifest(self.run_mocked(checks))

        self.assertEqual(
            [issue["key"] for issue in manifest["errors"]],
            ["alpha", "zeta"],
        )
        self.assertEqual(
            [issue["key"] for issue in manifest["warnings"]],
            ["a-warning", "z-warning"],
        )

    def test_manifests_are_deterministic_across_equivalent_roots(self):
        first_root = self.temp_path / "first-root"
        second_root = self.temp_path / "second-root"
        first_root.mkdir()
        second_root.mkdir()
        first_assembly = self.prepare_assembly(first_root)
        second_assembly = self.prepare_assembly(second_root)

        with mock.patch.object(
            render_preflight,
            "run_render_preflight",
            side_effect=(
                self.raw_preflight(self.ready_checks(), first_assembly.project_path),
                self.raw_preflight(self.ready_checks(), second_assembly.project_path),
            ),
        ):
            first = self.runner.run(
                assembly_result=first_assembly,
                project_root_dir=first_root.resolve(),
            )
            second = self.runner.run(
                assembly_result=second_assembly,
                project_root_dir=second_root.resolve(),
            )

        self.assertEqual(first.manifest_path.read_bytes(), second.manifest_path.read_bytes())

    def test_success_leaves_no_temporary_files(self):
        self.run_mocked(self.ready_checks())

        self.assertEqual(tuple(self.project_root.rglob("*.tmp")), ())

    def test_failure_leaves_no_temporary_files(self):
        with mock.patch.object(
            ProductionWorkspace,
            "publish_production_preflight_manifest",
            side_effect=OSError("publication failed"),
        ):
            with self.assertRaises(ProductionPreflightError):
                self.run_mocked(self.ready_checks())

        self.assertEqual(tuple(self.project_root.rglob("*.tmp")), ())

    def test_runner_uses_no_network(self):
        with mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network attempted"),
        ), mock.patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("network attempted"),
        ):
            self.run_mocked(self.ready_checks())

    def test_runner_starts_no_subprocess_or_ffmpeg(self):
        with mock.patch.object(
            subprocess,
            "run",
            side_effect=AssertionError("subprocess attempted"),
        ), mock.patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("subprocess attempted"),
        ):
            self.run_real()

    def test_module_has_no_future_runtime_dependencies(self):
        source = inspect.getsource(production_preflight_module).casefold()

        for forbidden in (
            "pipeline.render_job",
            "render_worker",
            "video_exporter",
            "streamlit",
            "subprocess",
            "os.environ",
            "git ",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_manual_full_pipeline_integration(self):
        integration_root = self.temp_path / "manual-integration"
        integration_root.mkdir()
        assembly = self.prepare_assembly(integration_root)
        status_before = assembly.workspace.status_path.read_bytes()

        result = self.runner.run(
            assembly_result=assembly,
            project_root_dir=integration_root.resolve(),
        )

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.error_count, 0)
        self.assertTrue(result.ffmpeg_available)
        self.assertTrue(result.manifest_path.is_file())
        self.assertEqual(assembly.workspace.status_path.read_bytes(), status_before)
        self.assertEqual(json.loads(status_before)["state"], "dataset_ready")
        self.assertFalse(assembly.output_path.exists())

    @property
    def logo_paths(self):
        project = self.read_json(self.assembly_result.project_path)
        paths = []
        for style in project.get("categories", {}).values():
            for field_name in ("logo", "secondary_logo"):
                value = style.get(field_name)
                if value:
                    paths.append((self.project_root / value).resolve())
        return tuple(paths)

    def prepare_assembly(self, project_root):
        project_root = Path(project_root).resolve()
        template_path = project_root / "templates" / "automation_template.json"
        template_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATE_FIXTURE_PATH, template_path)
        brief = load_production_brief(VALID_BRIEF_PATH, root_dir=ROOT_DIR)
        dataset_result = ProductionOrchestrator(
            create_default_dataset_builder_registry()
        ).prepare_dataset(
            brief,
            workspace_root_dir=project_root / "jobs",
            source_root_dir=ROOT_DIR,
        )
        build = dataset_result.build_result
        dataframe = pd.read_csv(build.csv_path)
        category = sorted(dataframe[build.category_column].unique())[0]
        logo_source = project_root / "local-logos"
        logo_source.mkdir()
        (logo_source / f"{category}.png").write_bytes(b"synthetic-logo")
        logo_result = LocalLogoResolver().resolve(
            dataset_csv=build.csv_path,
            category_column=build.category_column,
            workspace=dataset_result.workspace,
            primary_logo_dir=logo_source.resolve(),
            missing_policy="allow",
        )
        return ProductionProjectAssembler().assemble(
            dataset_result=dataset_result,
            template_project_path=template_path.resolve(),
            project_root_dir=project_root,
            options=ProjectAssemblyOptions(
                project_name="preflight_project",
                title="Production Preflight",
                source_label="Source: synthetic integration data",
            ),
            logo_result=logo_result,
        )

    def run_real(self):
        return self.runner.run(
            assembly_result=self.assembly_result,
            project_root_dir=self.project_root.resolve(),
        )

    def run_mocked(
        self,
        checks,
        *,
        assembly_result=None,
        project_root_dir=None,
    ):
        assembly = assembly_result or self.assembly_result
        raw_result = self.raw_preflight(checks, assembly.project_path)
        with mock.patch.object(
            render_preflight,
            "run_render_preflight",
            return_value=raw_result,
        ):
            return self.runner.run(
                assembly_result=assembly,
                project_root_dir=project_root_dir or self.project_root.resolve(),
            )

    def ready_checks(self, *, ffmpeg_available=True):
        ffmpeg = (
            self.check("ffmpeg", "FFmpeg", "ok", "Available at C:/tools/ffmpeg.exe.")
            if ffmpeg_available
            else self.check(
                "ffmpeg",
                "FFmpeg",
                "error",
                "FFmpeg was not found on PATH.",
            )
        )
        return (
            self.check("project", "Project JSON", "ok", "Configuration is valid."),
            self.check("data_source", "Data source", "ok", "Loaded 10 rows."),
            self.check("dataset", "Dataset", "ok", "Required columns are valid."),
            self.check("periods", "Timeline", "ok", "4 distinct periods."),
            ffmpeg,
            self.check("output", "Video output", "ok", "Output is writable."),
        )

    @staticmethod
    def check(key, label, level, message):
        return render_preflight.PreflightCheck(key, label, level, message)

    def raw_preflight(self, checks, project_path=None):
        return render_preflight.RenderPreflight(
            str(project_path or self.assembly_result.project_path),
            tuple(checks),
        )

    @staticmethod
    def manifest(result):
        return ProductionPreflightRunnerTest.read_json(result.manifest_path)

    @staticmethod
    def read_json(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def write_json(data, path):
        Path(path).write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    @staticmethod
    def sha256(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
if __name__ == "__main__":
    unittest.main()
