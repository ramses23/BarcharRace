import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd


TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import automation.render_executor as render_executor_module
from automation.brief_loader import load_production_brief
from automation.logo_resolver import LocalLogoResolver
from automation.orchestrator import ProductionOrchestrator
from automation.production_preflight import ProductionPreflightRunner
from automation.project_assembler import ProductionProjectAssembler
from automation.registry import create_default_dataset_builder_registry
from automation.render_executor import ProductionRenderExecutor
from automation.workspace import ProductionWorkspace
from config.dataset_config import DatasetConfig
from config.project_file_loader import load_project_file
from ui.render_controller import start_background_render as real_start_background_render
from validators.dataset_validator import DatasetValidator


EXAMPLE_FILES = (
    Path("production/briefs/examples/national_team_goals_demo.json"),
    Path("production/templates/national_team_goals_demo.json"),
    Path("production/inputs/examples/national_team_goals_source.csv"),
)


class ProductionMvpEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_root = Path(self.temporary_directory.name).resolve()
        self.original_inputs = {
            relative_path: (ROOT_DIR / relative_path).read_bytes()
            for relative_path in EXAMPLE_FILES
        }
        for relative_path in EXAMPLE_FILES:
            destination = self.temp_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT_DIR / relative_path, destination)
        self.copied_inputs = {
            relative_path: (self.temp_root / relative_path).read_bytes()
            for relative_path in EXAMPLE_FILES
        }

    def test_brief_v2_runs_complete_pipeline_in_isolated_worker(self):
        repo_output_before = self.snapshot_tree(ROOT_DIR / "output")
        brief_path = self.temp_root / EXAMPLE_FILES[0]
        brief = load_production_brief(brief_path, root_dir=self.temp_root)
        statuses = []
        handles = []
        original_replace = ProductionWorkspace.replace_status

        def record_status(workspace, data):
            statuses.append(data["state"])
            return original_replace(workspace, data)

        def launch(project_file, *, root_dir):
            handle = real_start_background_render(
                project_file,
                root_dir=root_dir,
                worker_path=ROOT_DIR / "src" / "studio" / "render_worker.py",
            )
            handles.append(handle)
            return handle

        def render_executor_factory(**kwargs):
            return ProductionRenderExecutor(
                poll_interval_seconds=0.02,
                **kwargs,
            )

        network_guard = self.install_network_guard()
        environment = {
            "PYTHONPATH": str(network_guard),
            "PYTHONDONTWRITEBYTECODE": "1",
            "MPLCONFIGDIR": str(self.temp_root / ".matplotlib"),
            "TMP": str(self.temp_root / "tmp"),
            "TEMP": str(self.temp_root / "tmp"),
        }
        (self.temp_root / "tmp").mkdir()
        network_failure = AssertionError("network access attempted by production")

        orchestrator = ProductionOrchestrator(
            create_default_dataset_builder_registry(),
            logo_resolver_component=LocalLogoResolver(),
            project_assembler_component=ProductionProjectAssembler(),
            preflight_runner_component=ProductionPreflightRunner(),
            render_executor_factory=render_executor_factory,
        )
        with mock.patch.object(
            ProductionWorkspace,
            "replace_status",
            autospec=True,
            side_effect=record_status,
        ), mock.patch.object(
            render_executor_module,
            "start_background_render",
            side_effect=launch,
        ), mock.patch.object(
            socket,
            "create_connection",
            side_effect=network_failure,
        ), mock.patch.object(
            socket.socket,
            "connect",
            side_effect=network_failure,
        ), mock.patch.dict(os.environ, environment, clear=False):
            result = orchestrator.run_production(
                brief,
                project_root_dir=self.temp_root,
                workspace_root_dir=(
                    self.temp_root / "output" / ".production_jobs"
                ).resolve(),
                source_root_dir=self.temp_root,
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            statuses,
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
        self.assertEqual(result.preflight_result.status, "ready")
        self.assertIsNone(result.logo_result)
        self.assertTrue((network_guard / "loaded.txt").is_file())

        workspace = result.workspace
        self.assertTrue(workspace.root_path.is_relative_to(self.temp_root))
        expected_manifests = {
            workspace.dataset_build_manifest_path,
            workspace.project_assembly_manifest_path,
            workspace.production_preflight_manifest_path,
            workspace.production_render_manifest_path,
        }
        self.assertTrue(workspace.workspace_manifest_path.is_file())
        self.assertEqual(
            set(workspace.manifests_dir.glob("*.json")),
            expected_manifests,
        )
        self.assertFalse(workspace.logo_resolution_manifest_path.exists())

        build_result = result.dataset_result.build_result
        validated = DatasetValidator(
            DatasetConfig(
                year_column=build_result.period_column,
                name_column=build_result.category_column,
                value_column=build_result.value_column,
            )
        ).validate(pd.read_csv(workspace.dataset_csv_path, encoding="utf-8"))
        self.assertFalse(validated.empty)
        self.assertEqual(len(validated), build_result.row_count)

        project = load_project_file(workspace.project_json_path)
        configured_output = (
            self.temp_root / project.chart_config.output_file
        ).resolve(strict=False)
        self.assertEqual(configured_output, workspace.video_path)

        video = workspace.video_path
        self.assertTrue(video.is_file())
        self.assertGreater(video.stat().st_size, 0)
        self.assertEqual(video.read_bytes()[4:8], b"ftyp")
        video_sha256 = self.sha256(video)
        self.assertEqual(video_sha256, result.render_result.video_sha256)
        render_manifest = self.read_json(workspace.production_render_manifest_path)
        self.assertEqual(render_manifest["video"]["sha256"], video_sha256)
        self.assertEqual(
            render_manifest["video"]["size_bytes"],
            video.stat().st_size,
        )

        status = self.read_json(workspace.status_path)
        self.assertEqual(status["state"], "completed")
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
        for reference in status["artifacts"].values():
            self.assert_portable_reference(reference)

        portable_json_files = (
            workspace.workspace_manifest_path,
            workspace.status_path,
            *sorted(expected_manifests),
        )
        for json_path in portable_json_files:
            text = json_path.read_text(encoding="utf-8")
            with self.subTest(json_path=json_path):
                self.assertNotIn(str(self.temp_root), text)
                self.assertNotIn(self.temp_root.as_posix(), text)
                self.assertNotRegex(text, r"(?i)[a-z]:[\\/]")

        self.assertEqual(tuple(self.temp_root.rglob("*.partial.mp4")), ())
        self.assertEqual(tuple(self.temp_root.rglob("*.tmp")), ())
        self.assertTrue(handles)
        self.assertTrue(all(not handle.is_running() for handle in handles))
        for handle in handles:
            self.assertTrue(handle.status_path.is_relative_to(self.temp_root))
            self.assertTrue(handle.log_path.is_relative_to(self.temp_root))
        self.assertEqual(self.snapshot_tree(ROOT_DIR / "output"), repo_output_before)
        self.assert_inputs_unchanged()

    def install_network_guard(self):
        guard_dir = self.temp_root / "network_guard"
        guard_dir.mkdir()
        (guard_dir / "sitecustomize.py").write_text(
            """from pathlib import Path
import socket

Path(__file__).with_name("loaded.txt").write_text(
    "network disabled\\n", encoding="utf-8"
)

def _blocked(*args, **kwargs):
    raise RuntimeError("network access is disabled in the production E2E")

class _BlockedSocket(socket.socket):
    def connect(self, *args, **kwargs):
        return _blocked(*args, **kwargs)

    def connect_ex(self, *args, **kwargs):
        return _blocked(*args, **kwargs)

socket.create_connection = _blocked
socket.socket = _BlockedSocket
""",
            encoding="utf-8",
            newline="\n",
        )
        return guard_dir

    def assert_inputs_unchanged(self):
        for relative_path in EXAMPLE_FILES:
            with self.subTest(input=relative_path):
                self.assertEqual(
                    (ROOT_DIR / relative_path).read_bytes(),
                    self.original_inputs[relative_path],
                )
                self.assertEqual(
                    (self.temp_root / relative_path).read_bytes(),
                    self.copied_inputs[relative_path],
                )

    def assert_portable_reference(self, reference):
        self.assertIsInstance(reference, str)
        self.assertNotIn("\\", reference)
        self.assertNotIn(":", reference)
        self.assertFalse(Path(reference).is_absolute())
        self.assertNotIn("..", Path(reference).parts)

    @staticmethod
    def read_json(path):
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def sha256(path):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def snapshot_tree(root):
        if not root.exists():
            return ()
        return tuple(
            sorted(
                (
                    path.relative_to(root).as_posix(),
                    path.stat().st_size,
                    path.stat().st_mtime_ns,
                )
                for path in root.rglob("*")
                if path.is_file()
            )
        )


if __name__ == "__main__":
    unittest.main()
