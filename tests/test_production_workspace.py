import hashlib
import inspect
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

import pandas as pd


TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from automation.builders import NationalTeamGoalsDatasetBuilder
from automation.workspace import (
    DEFAULT_PRODUCTION_JOBS_ROOT,
    PRODUCTION_STATUS_SCHEMA_VERSION,
    WORKSPACE_SCHEMA_VERSION,
    ProductionWorkspace,
)
from config.dataset_config import DatasetConfig
from validators.dataset_validator import DatasetValidator


FIXTURE_PATH = (
    TESTS_DIR
    / "automation"
    / "fixtures"
    / "national_team_goals_source.csv"
)


class ProductionWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()
        self.jobs_root = self.temp_path / "jobs"

    def create(self, job_id="job7", root_dir=None):
        return ProductionWorkspace.create(
            job_id=job_id,
            root_dir=root_dir or self.jobs_root,
        )

    @staticmethod
    def read_json(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def test_create_builds_complete_standard_structure(self):
        workspace = self.create()

        self.assertTrue(workspace.root_path.is_dir())
        for directory in workspace.directories:
            self.assertTrue(directory.is_dir())
        self.assertTrue(workspace.status_path.is_file())
        self.assertTrue(workspace.workspace_manifest_path.is_file())
        self.assertEqual(
            {path.name for path in workspace.root_path.iterdir()},
            {
                "input",
                "dataset",
                "logos",
                "project",
                "render",
                "logs",
                "manifests",
                "status.json",
                "workspace_manifest.json",
            },
        )

    def test_normal_construction_has_no_filesystem_effects(self):
        root_path = self.jobs_root / "job7"
        workspace = ProductionWorkspace(job_id="job7", root_path=root_path)

        self.assertEqual(workspace.root_path, root_path.resolve())
        self.assertFalse(root_path.exists())

    def test_all_exposed_paths_are_absolute_and_resolved(self):
        workspace = self.create()

        for path in self._all_paths(workspace):
            self.assertTrue(path.is_absolute())
            self.assertEqual(path, path.resolve())

    def test_all_exposed_paths_remain_inside_workspace(self):
        workspace = self.create()

        for path in self._all_paths(workspace):
            self.assertTrue(
                path == workspace.root_path
                or path.is_relative_to(workspace.root_path)
            )

    def test_canonical_artifact_paths_are_reserved_without_creating_files(self):
        workspace = self.create()

        self.assertEqual(workspace.source_csv_path, workspace.input_dir / "source.csv")
        self.assertEqual(
            workspace.dataset_csv_path,
            workspace.dataset_dir / "dataset.csv",
        )
        self.assertEqual(
            workspace.dataset_build_manifest_path,
            workspace.manifests_dir / "dataset_build.json",
        )
        self.assertEqual(
            workspace.project_json_path,
            workspace.project_dir / "project.json",
        )
        self.assertEqual(workspace.video_path, workspace.render_dir / "video.mp4")
        self.assertEqual(
            workspace.production_log_path,
            workspace.logs_dir / "production.log",
        )
        for path in (
            workspace.source_csv_path,
            workspace.dataset_csv_path,
            workspace.dataset_build_manifest_path,
            workspace.project_json_path,
            workspace.video_path,
            workspace.production_log_path,
        ):
            self.assertFalse(path.exists())

    def test_manifest_has_independent_version_one_and_relative_paths(self):
        workspace = self.create("national-team-goals-1900-2025")

        self.assertEqual(
            self.read_json(workspace.workspace_manifest_path),
            {
                "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
                "job_id": "national-team-goals-1900-2025",
                "paths": {
                    "input": "input",
                    "dataset": "dataset",
                    "logos": "logos",
                    "project": "project",
                    "render": "render",
                    "logs": "logs",
                    "manifests": "manifests",
                    "status": "status.json",
                },
            },
        )
        self.assertEqual(WORKSPACE_SCHEMA_VERSION, 1)

    def test_initial_status_has_independent_version_and_created_state(self):
        workspace = self.create("national-team-goals-1900-2025")

        self.assertEqual(
            self.read_json(workspace.status_path),
            {
                "production_status_schema_version": PRODUCTION_STATUS_SCHEMA_VERSION,
                "job_id": "national-team-goals-1900-2025",
                "state": "created",
                "stage": "workspace",
                "message": "Production workspace created.",
            },
        )
        self.assertEqual(PRODUCTION_STATUS_SCHEMA_VERSION, 1)

    def test_manifest_is_deterministic_across_roots(self):
        first = self.create("same_job", self.temp_path / "first")
        second = self.create("same_job", self.temp_path / "second")

        self.assertEqual(
            first.workspace_manifest_path.read_bytes(),
            second.workspace_manifest_path.read_bytes(),
        )

    def test_initial_status_is_deterministic_across_roots(self):
        first = self.create("same_job", self.temp_path / "first")
        second = self.create("same_job", self.temp_path / "second")

        self.assertEqual(first.status_path.read_bytes(), second.status_path.read_bytes())

    def test_empty_job_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-empty"):
            self.create("")

    def test_job_id_with_spaces_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "only lowercase"):
            self.create("mi trabajo")

    def test_job_id_with_forward_slash_is_rejected(self):
        with self.assertRaises(ValueError):
            self.create("job/otro")

    def test_job_id_with_backslash_is_rejected(self):
        with self.assertRaises(ValueError):
            self.create("job\\otro")

    def test_job_id_with_parent_traversal_is_rejected(self):
        for job_id in ("..", "../otro", "job..otro"):
            with self.subTest(job_id=job_id), self.assertRaises(ValueError):
                self.create(job_id)

    def test_absolute_path_job_ids_are_rejected(self):
        for job_id in (str(self.temp_path), r"C:\job", "C:"):
            with self.subTest(job_id=job_id), self.assertRaises(ValueError):
                self.create(job_id)

    def test_windows_reserved_job_ids_are_rejected(self):
        for job_id in ("con", "prn", "aux", "nul", "com1", "com9", "lpt1", "lpt9"):
            with self.subTest(job_id=job_id), self.assertRaisesRegex(
                ValueError,
                "Windows-reserved",
            ):
                self.create(job_id)

    def test_overlong_job_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "64"):
            self.create("a" * 65)

    def test_hyphens_and_underscores_are_accepted_exactly(self):
        job_id = "national_team-goals_001"
        workspace = self.create(job_id)

        self.assertEqual(workspace.job_id, job_id)
        self.assertEqual(workspace.root_path.name, job_id)

    def test_second_creation_with_same_id_fails(self):
        self.create()

        with self.assertRaises(FileExistsError):
            self.create()

    def test_second_creation_preserves_existing_workspace_content(self):
        first = self.create()
        marker = first.logs_dir / "keep.txt"
        marker.write_text("preserve me", encoding="utf-8")
        manifest = first.workspace_manifest_path.read_bytes()

        with self.assertRaises(FileExistsError):
            self.create()

        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me")
        self.assertEqual(first.workspace_manifest_path.read_bytes(), manifest)

    def test_one_job_cannot_affect_another(self):
        first = self.create("job1")
        second = self.create("job2")
        marker = first.input_dir / "keep.txt"
        marker.write_text("first", encoding="utf-8")

        self.assertNotEqual(first.root_path, second.root_path)
        self.assertEqual(marker.read_text(encoding="utf-8"), "first")
        self.assertTrue(second.root_path.exists())

    def test_subdirectory_creation_failure_rolls_back_job_only(self):
        with mock.patch.object(
            ProductionWorkspace,
            "_create_subdirectory",
            side_effect=OSError("subdirectory failure"),
        ):
            with self.assertRaisesRegex(OSError, "subdirectory failure"):
                self.create()

        self.assertTrue(self.jobs_root.is_dir())
        self.assertFalse((self.jobs_root / "job7").exists())

    def test_manifest_write_failure_rolls_back_job(self):
        original = ProductionWorkspace._write_json_exclusive

        def fail_manifest(data, destination):
            if destination.name == "workspace_manifest.json":
                raise OSError("manifest failure")
            return original(data, destination)

        with mock.patch.object(
            ProductionWorkspace,
            "_write_json_exclusive",
            side_effect=fail_manifest,
        ):
            with self.assertRaisesRegex(OSError, "manifest failure"):
                self.create()

        self.assertFalse((self.jobs_root / "job7").exists())

    def test_status_write_failure_rolls_back_job(self):
        original = ProductionWorkspace._write_json_exclusive

        def fail_status(data, destination):
            if destination.name == "status.json":
                raise OSError("status failure")
            return original(data, destination)

        with mock.patch.object(
            ProductionWorkspace,
            "_write_json_exclusive",
            side_effect=fail_status,
        ):
            with self.assertRaisesRegex(OSError, "status failure"):
                self.create()

        self.assertFalse((self.jobs_root / "job7").exists())

    def test_json_cleanup_failure_does_not_hide_publication_error(self):
        destination = self.temp_path / "result.json"
        with (
            mock.patch(
                "automation.workspace.os.link",
                side_effect=OSError("original publication failure"),
            ),
            mock.patch.object(
                Path,
                "unlink",
                side_effect=PermissionError("cleanup lock"),
            ),
        ):
            with self.assertRaisesRegex(OSError, "Atomic JSON publication") as context:
                ProductionWorkspace._write_json_exclusive(
                    {"value": 1},
                    destination,
                )

        self.assertIsInstance(context.exception.__cause__, OSError)
        self.assertIn("original publication failure", str(context.exception.__cause__))
        self.assertIn("cleanup also failed", " ".join(context.exception.__notes__))
        self.assertFalse(destination.exists())
        for temporary_path in self.temp_path.glob(".*.tmp"):
            temporary_path.unlink()

    def test_rollback_failure_does_not_hide_original_error(self):
        with (
            mock.patch.object(
                ProductionWorkspace,
                "_create_subdirectory",
                side_effect=OSError("original creation failure"),
            ),
            mock.patch.object(
                ProductionWorkspace,
                "_rollback_created_workspace",
                side_effect=PermissionError("rollback lock"),
            ),
        ):
            with self.assertRaisesRegex(OSError, "original creation failure") as context:
                self.create()

        self.assertIn("rollback also failed", " ".join(context.exception.__notes__))
        shutil.rmtree(self.jobs_root / "job7")

    def test_rollback_never_removes_root_dir(self):
        with mock.patch.object(
            ProductionWorkspace,
            "_create_subdirectory",
            side_effect=OSError("failure"),
        ):
            with self.assertRaises(OSError):
                self.create()

        self.assertTrue(self.jobs_root.is_dir())

    def test_rollback_never_removes_other_jobs(self):
        existing = self.create("existing")
        marker = existing.logs_dir / "keep.txt"
        marker.write_text("safe", encoding="utf-8")

        with mock.patch.object(
            ProductionWorkspace,
            "_create_subdirectory",
            side_effect=OSError("failure"),
        ):
            with self.assertRaises(OSError):
                self.create("failing")

        self.assertEqual(marker.read_text(encoding="utf-8"), "safe")
        self.assertFalse((self.jobs_root / "failing").exists())

    def test_successful_creation_leaves_no_temporary_files(self):
        workspace = self.create()

        self.assertEqual(list(workspace.root_path.rglob("*.tmp")), [])

    def test_creation_has_zero_network_access(self):
        with (
            mock.patch.object(
                urllib.request,
                "urlopen",
                side_effect=AssertionError("network access attempted"),
            ),
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network access attempted"),
            ),
        ):
            self.create()

    def test_creation_executes_no_subprocesses(self):
        with (
            mock.patch.object(
                subprocess,
                "run",
                side_effect=AssertionError("subprocess attempted"),
            ),
            mock.patch.object(
                subprocess,
                "Popen",
                side_effect=AssertionError("subprocess attempted"),
            ),
        ):
            self.create()

    def test_json_files_are_utf8_without_bom(self):
        workspace = self.create()

        for path in (workspace.workspace_manifest_path, workspace.status_path):
            content = path.read_bytes()
            self.assertFalse(content.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(content.decode("utf-8"), path.read_text(encoding="utf-8"))

    def test_json_files_end_with_one_lf_newline(self):
        workspace = self.create()

        for path in (workspace.workspace_manifest_path, workspace.status_path):
            content = path.read_bytes()
            self.assertTrue(content.endswith(b"\n"))
            self.assertFalse(content.endswith(b"\n\n"))
            self.assertNotIn(b"\r", content)

    def test_json_tree_contains_no_machine_specific_paths(self):
        workspace = self.create()
        serialized = (
            workspace.workspace_manifest_path.read_text(encoding="utf-8")
            + workspace.status_path.read_text(encoding="utf-8")
        )

        self.assertNotIn(str(self.temp_path), serialized)
        self.assertNotIn(str(Path.home()), serialized)

    def test_default_root_is_under_ignored_output_directory(self):
        self.assertEqual(
            DEFAULT_PRODUCTION_JOBS_ROOT,
            (ROOT_DIR / "output" / ".production_jobs").resolve(),
        )
        self.assertIn("output/", (ROOT_DIR / ".gitignore").read_text(encoding="utf-8"))

    def test_builder_integrates_by_canonical_dataset_path_only(self):
        workspace = self.create("builder_integration")
        builder = NationalTeamGoalsDatasetBuilder()
        source_hash = hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest()

        result = builder.build(
            source_csv=FIXTURE_PATH,
            output_csv=workspace.dataset_csv_path,
            start_year=2000,
            end_year=2003,
            mode="cumulative",
            expected_source_sha256=source_hash,
            duplicate_policy="allow",
        )

        self.assertEqual(result.csv_path, workspace.dataset_csv_path)
        self.assertTrue(result.csv_path.is_relative_to(workspace.root_path))
        validated = DatasetValidator(
            DatasetConfig(
                year_column="year",
                name_column="country",
                value_column="value",
            )
        ).validate(pd.read_csv(result.csv_path))
        self.assertFalse(validated.empty)
        builder_source = inspect.getsource(sys.modules[builder.__class__.__module__])
        self.assertNotIn("ProductionWorkspace", builder_source)
        self.assertNotIn("automation.workspace", builder_source)

    @staticmethod
    def _all_paths(workspace):
        return (
            workspace.root_path,
            *workspace.directories,
            workspace.status_path,
            workspace.workspace_manifest_path,
            workspace.source_csv_path,
            workspace.dataset_csv_path,
            workspace.dataset_build_manifest_path,
            workspace.project_json_path,
            workspace.video_path,
            workspace.production_log_path,
        )


if __name__ == "__main__":
    unittest.main()
