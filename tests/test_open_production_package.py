import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import chdir
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

import _test_path
from src.tools import open_production_package
from studio.production_package_binding import (
    BINDING_FILENAME,
    binding_path_for_package,
)
from studio.project_bundle import build_project_bundle


class OpenProductionPackageCommandTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="barchart-open-package-"
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()
        self.exported = self._build_bundle(self.temp_path / "source")
        self.zip_path = self.temp_path / self.exported.filename
        self.zip_path.write_bytes(self.exported.data)
        self.folder_path = self.temp_path / "package-folder"
        self.folder_path.mkdir()
        with zipfile.ZipFile(io.BytesIO(self.exported.data)) as archive:
            archive.extractall(self.folder_path)

    def test_no_launch_imports_real_zip_without_subprocess(self):
        root = self._new_root("zip-root")
        stdout = io.StringIO()

        with mock.patch.object(
            open_production_package.subprocess,
            "run",
        ) as launch, contextlib.redirect_stdout(stdout):
            exit_code = open_production_package.main(
                [
                    str(self.zip_path),
                    "--root",
                    str(root),
                    "--no-launch",
                ]
            )

        self.assertEqual(exit_code, 0)
        launch.assert_not_called()
        self.assertTrue((root / "projects" / "command_project.json").is_file())
        self.assertTrue(
            (root / "projects" / "imported" / "command_project").is_dir()
        )
        summary = stdout.getvalue()
        self.assertIn("Project: command_project", summary)
        self.assertIn(
            "Editable path: projects/command_project.json",
            summary,
        )
        self.assertIn("Imported files:", summary)
        self.assertIn("Imported size:", summary)

    def test_no_launch_imports_real_folder_without_subprocess(self):
        root = self._new_root("folder-root")
        relative_folder = self.folder_path.relative_to(self.temp_path)

        with chdir(self.temp_path), mock.patch.object(
            open_production_package.subprocess,
            "run",
        ) as launch, contextlib.redirect_stdout(io.StringIO()):
            exit_code = open_production_package.main(
                [
                    str(relative_folder),
                    "--root",
                    str(root),
                    "--no-launch",
                ]
            )

        self.assertEqual(exit_code, 0)
        launch.assert_not_called()
        self.assertTrue((root / "projects" / "command_project.json").is_file())
        self.assertTrue(
            (root / "projects" / "imported" / "command_project").is_dir()
        )

    def test_invalid_package_fails_without_launching_streamlit(self):
        root = self._new_root("invalid-root")
        invalid_zip = self.temp_path / "invalid.zip"
        invalid_zip.write_bytes(b"not a zip")
        stderr = io.StringIO()

        with mock.patch.object(
            open_production_package.subprocess,
            "run",
        ) as launch, contextlib.redirect_stderr(stderr):
            exit_code = open_production_package.main(
                [
                    str(invalid_zip),
                    "--root",
                    str(root),
                ]
            )

        self.assertNotEqual(exit_code, 0)
        launch.assert_not_called()
        self.assertIn("Could not open production package", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_launch_uses_current_python_explicit_root_and_autoload_env(self):
        root = self._new_root("launch-root")
        app_path = root / open_production_package.PROJECT_STUDIO_PATH
        app_path.parent.mkdir(parents=True)
        app_path.write_text("# test entrypoint\n", encoding="utf-8")
        completed = subprocess.CompletedProcess(args=[], returncode=0)

        with mock.patch.object(
            open_production_package.subprocess,
            "run",
            return_value=completed,
        ) as launch, contextlib.redirect_stdout(io.StringIO()):
            exit_code = open_production_package.main(
                [
                    str(self.zip_path),
                    "--root",
                    str(root),
                    "--port",
                    "8765",
                    "--headless",
                ]
            )

        self.assertEqual(exit_code, 0)
        launch.assert_called_once()
        command = launch.call_args.args[0]
        options = launch.call_args.kwargs
        self.assertEqual(
            command,
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "src/ui/project_studio.py",
                "--server.port=8765",
                "--server.headless=true",
            ],
        )
        self.assertEqual(options["cwd"], root.resolve())
        self.assertFalse(options["shell"])
        self.assertFalse(options["check"])
        environment = options["env"]
        self.assertEqual(
            environment[open_production_package.AUTOLOAD_PROJECT_ENV],
            "projects/command_project.json",
        )
        token = environment[open_production_package.AUTOLOAD_TOKEN_ENV]
        self.assertRegex(token, r"^[0-9a-f]{32}$")

    def test_second_open_reuses_exact_project_without_importing_again(self):
        root = self._new_root("linked-root")
        first_stdout = io.StringIO()
        with contextlib.redirect_stdout(first_stdout):
            first_exit = open_production_package.main(
                [
                    str(self.folder_path),
                    "--root",
                    str(root),
                    "--no-launch",
                ]
            )

        project_path = root / "projects" / "command_project.json"
        saved_project = json.loads(project_path.read_text(encoding="utf-8"))
        saved_project["chart"]["title"] = "Saved after first import"
        project_path.write_text(
            json.dumps(saved_project, sort_keys=True),
            encoding="utf-8",
        )
        second_stdout = io.StringIO()

        with mock.patch.object(
            open_production_package,
            "import_project_bundle",
        ) as importer, contextlib.redirect_stdout(second_stdout):
            second_exit = open_production_package.main(
                [
                    str(self.folder_path),
                    "--root",
                    str(root),
                    "--no-launch",
                ]
            )

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 0)
        importer.assert_not_called()
        self.assertEqual(
            json.loads(project_path.read_text(encoding="utf-8"))["chart"][
                "title"
            ],
            "Saved after first import",
        )
        self.assertFalse(
            (root / "projects" / "command_project_2.json").exists()
        )
        summary = second_stdout.getvalue()
        self.assertIn("Production package already linked", summary)
        self.assertIn(
            "Editable path: projects/command_project.json",
            summary,
        )
        self.assertIn("No package import was performed", summary)

    def test_reimport_creates_new_project_and_updates_binding(self):
        root = self._new_root("reimport-root")
        with contextlib.redirect_stdout(io.StringIO()):
            first_exit = open_production_package.main(
                [
                    str(self.folder_path),
                    "--root",
                    str(root),
                    "--no-launch",
                ]
            )
        stdout = io.StringIO()
        with mock.patch.object(
            open_production_package.subprocess,
            "run",
        ) as launch, contextlib.redirect_stdout(stdout):
            second_exit = open_production_package.main(
                [
                    str(self.folder_path),
                    "--root",
                    str(root),
                    "--reimport",
                    "--no-launch",
                ]
            )

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 0)
        launch.assert_not_called()
        self.assertTrue(
            (root / "projects" / "command_project.json").is_file()
        )
        self.assertTrue(
            (root / "projects" / "command_project_2.json").is_file()
        )
        binding = self._binding_data(self.folder_path)
        self.assertEqual(
            binding["project_path"],
            "projects/command_project_2.json",
        )
        summary = stdout.getvalue()
        self.assertIn("Production package reimported", summary)
        self.assertIn(
            "Editable path: projects/command_project_2.json",
            summary,
        )
        self.assertIn("Binding updated:", summary)

    def test_adopt_project_links_existing_project_without_importing(self):
        root = self._new_root("adopt-root")
        adopted = self._write_existing_project(
            root,
            "existing_project_3",
            title="Existing edited project",
        )
        stdout = io.StringIO()

        with mock.patch.object(
            open_production_package,
            "import_project_bundle",
        ) as importer, mock.patch.object(
            open_production_package.subprocess,
            "run",
        ) as launch, contextlib.redirect_stdout(stdout):
            exit_code = open_production_package.main(
                [
                    str(self.folder_path),
                    "--root",
                    str(root),
                    "--adopt-project",
                    str(adopted.relative_to(root)),
                    "--no-launch",
                ]
            )

        self.assertEqual(exit_code, 0)
        importer.assert_not_called()
        launch.assert_not_called()
        binding = self._binding_data(self.folder_path)
        self.assertEqual(
            binding["project_path"],
            "projects/existing_project_3.json",
        )
        summary = stdout.getvalue()
        self.assertIn("Existing project adopted", summary)
        self.assertIn("Project: Existing edited project", summary)
        self.assertIn("Binding created:", summary)

    def test_adopt_project_rejects_paths_outside_projects(self):
        root = self._new_root("outside-adopt-root")
        outside = root / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        stderr = io.StringIO()

        with mock.patch.object(
            open_production_package,
            "import_project_bundle",
        ) as importer, contextlib.redirect_stderr(stderr):
            exit_code = open_production_package.main(
                [
                    str(self.folder_path),
                    "--root",
                    str(root),
                    "--adopt-project",
                    str(outside),
                    "--no-launch",
                ]
            )

        self.assertEqual(exit_code, 1)
        importer.assert_not_called()
        self.assertIn("inside root/projects", stderr.getvalue())
        self.assertFalse(
            binding_path_for_package(self.folder_path).exists()
        )

    def test_modified_manifest_invalidates_binding_without_reimport(self):
        root = self._new_root("changed-manifest-root")
        with contextlib.redirect_stdout(io.StringIO()):
            first_exit = open_production_package.main(
                [
                    str(self.folder_path),
                    "--root",
                    str(root),
                    "--no-launch",
                ]
            )
        manifest_path = self.folder_path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["project_name"] = "changed_package_name"
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True),
            encoding="utf-8",
        )
        stderr = io.StringIO()

        with mock.patch.object(
            open_production_package,
            "import_project_bundle",
        ) as importer, contextlib.redirect_stderr(stderr):
            second_exit = open_production_package.main(
                [
                    str(self.folder_path),
                    "--root",
                    str(root),
                    "--no-launch",
                ]
            )

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 1)
        importer.assert_not_called()
        error = stderr.getvalue()
        self.assertIn("manifest changed", error)
        self.assertIn("--reimport", error)
        self.assertFalse(
            (root / "projects" / "command_project_2.json").exists()
        )

    def test_deleted_linked_project_reports_recovery_options(self):
        root = self._new_root("deleted-project-root")
        with contextlib.redirect_stdout(io.StringIO()):
            first_exit = open_production_package.main(
                [
                    str(self.folder_path),
                    "--root",
                    str(root),
                    "--no-launch",
                ]
            )
        (root / "projects" / "command_project.json").unlink()
        stderr = io.StringIO()

        with mock.patch.object(
            open_production_package,
            "import_project_bundle",
        ) as importer, contextlib.redirect_stderr(stderr):
            second_exit = open_production_package.main(
                [
                    str(self.folder_path),
                    "--root",
                    str(root),
                    "--no-launch",
                ]
            )

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 1)
        importer.assert_not_called()
        error = stderr.getvalue()
        self.assertIn("linked editable project was deleted", error)
        self.assertIn("--reimport", error)
        self.assertIn("--adopt-project PROJECT_PATH", error)

    def test_corrupt_binding_stops_without_replacing_or_importing(self):
        root = self._new_root("corrupt-binding-root")
        state_path = binding_path_for_package(self.folder_path)
        state_path.write_text("{not valid json", encoding="utf-8")
        original_state = state_path.read_bytes()
        stderr = io.StringIO()

        with mock.patch.object(
            open_production_package,
            "import_project_bundle",
        ) as importer, contextlib.redirect_stderr(stderr):
            exit_code = open_production_package.main(
                [
                    str(self.folder_path),
                    "--root",
                    str(root),
                    "--no-launch",
                ]
            )

        self.assertEqual(exit_code, 1)
        importer.assert_not_called()
        self.assertEqual(state_path.read_bytes(), original_state)
        self.assertIn("Binding file is corrupt", stderr.getvalue())

    def test_folder_binding_is_outside_package_atomic_and_portable(self):
        root = self._new_root("portable-binding-root")
        manifest_path = self.folder_path / "manifest.json"
        manifest_before = manifest_path.read_bytes()
        package_files_before = sorted(
            path.relative_to(self.folder_path).as_posix()
            for path in self.folder_path.rglob("*")
            if path.is_file()
        )

        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = open_production_package.main(
                [
                    str(self.folder_path),
                    "--root",
                    str(root),
                    "--no-launch",
                ]
            )

        self.assertEqual(exit_code, 0)
        state_path = binding_path_for_package(self.folder_path)
        self.assertEqual(
            state_path,
            self.folder_path.parent / BINDING_FILENAME,
        )
        self.assertFalse(state_path.is_relative_to(self.folder_path))
        binding = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(binding["schema_version"], 1)
        self.assertEqual(
            binding["project_path"],
            "projects/command_project.json",
        )
        self.assertFalse(Path(binding["project_path"]).is_absolute())
        self.assertEqual(
            binding["package_reference"],
            self.folder_path.name,
        )
        self.assertEqual(
            binding["package_manifest_sha256"],
            hashlib.sha256(manifest_before).hexdigest(),
        )
        self.assertIn("+00:00", binding["bound_at"])
        self.assertEqual(manifest_path.read_bytes(), manifest_before)
        self.assertEqual(
            sorted(
                path.relative_to(self.folder_path).as_posix()
                for path in self.folder_path.rglob("*")
                if path.is_file()
            ),
            package_files_before,
        )
        self.assertEqual(list(state_path.parent.glob("*.tmp")), [])

    def test_zip_and_folder_use_deterministic_sidecar_paths(self):
        folder_binding = binding_path_for_package(self.folder_path)
        zip_binding = binding_path_for_package(self.zip_path)

        self.assertEqual(
            folder_binding,
            self.folder_path.parent / BINDING_FILENAME,
        )
        self.assertEqual(
            zip_binding,
            self.zip_path.with_name(
                f"{self.zip_path.name}.barchartstudio-launch.json"
            ),
        )
        self.assertNotEqual(folder_binding, zip_binding)
        self.assertFalse(folder_binding.is_relative_to(self.folder_path))
        self.assertEqual(zip_binding.parent, self.zip_path.parent)

    def test_keyboard_interrupt_returns_130_without_traceback(self):
        root = self._new_root("interrupt-root")
        stderr = io.StringIO()

        with mock.patch.object(
            open_production_package.subprocess,
            "run",
            side_effect=KeyboardInterrupt,
        ), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            stderr
        ):
            exit_code = open_production_package.main(
                [
                    str(self.zip_path),
                    "--root",
                    str(root),
                ]
            )

        self.assertEqual(exit_code, 130)
        error = stderr.getvalue()
        self.assertIn("Project Studio stopped by user.", error)
        self.assertNotIn("Traceback", error)

    @staticmethod
    def _build_bundle(source_root):
        dataset_path = source_root / "data" / "dataset.csv"
        dataset_path.parent.mkdir(parents=True)
        dataset_path.write_text(
            "year,name,value\n"
            "2000,Alpha,10\n"
            "2001,Alpha,12\n",
            encoding="utf-8",
        )
        return build_project_bundle(
            {
                "schema_version": 1,
                "name": "Command Project",
                "chart": {
                    "title": "Command Project",
                    "width": 320,
                    "height": 180,
                    "dpi": 80,
                    "logos_enabled": False,
                    "max_visible_bars": 1,
                    "output_file": "output/command.mp4",
                    "frames_dir": "output/command-frames",
                },
                "selection": {
                    "top_n": 1,
                    "aggregate_other": False,
                },
                "data_source": {
                    "source_type": "csv",
                    "csv_path": "data/dataset.csv",
                },
                "dataset": {
                    "year_column": "year",
                    "name_column": "name",
                    "value_column": "value",
                },
            },
            root_dir=source_root,
        )

    def _new_root(self, name):
        root = self.temp_path / name
        root.mkdir()
        return root

    @staticmethod
    def _write_existing_project(root, slug, *, title):
        dataset_path = root / "data" / f"{slug}.csv"
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        dataset_path.write_text(
            "year,name,value\n2000,Alpha,10\n2001,Alpha,12\n",
            encoding="utf-8",
        )
        project_path = root / "projects" / f"{slug}.json"
        project_path.parent.mkdir(parents=True, exist_ok=True)
        project_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": title,
                    "chart": {
                        "title": title,
                        "width": 320,
                        "height": 180,
                        "dpi": 80,
                        "logos_enabled": False,
                        "max_visible_bars": 1,
                        "output_file": f"output/{slug}.mp4",
                        "frames_dir": f"output/{slug}-frames",
                    },
                    "selection": {
                        "top_n": 1,
                        "aggregate_other": False,
                    },
                    "data_source": {
                        "source_type": "csv",
                        "csv_path": f"data/{slug}.csv",
                    },
                    "dataset": {
                        "year_column": "year",
                        "name_column": "name",
                        "value_column": "value",
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return project_path

    @staticmethod
    def _binding_data(package_path):
        state_path = binding_path_for_package(package_path)
        return json.loads(state_path.read_text(encoding="utf-8"))


class ProjectStudioAutoloadTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="barchart-autoload-"
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        repository_root = Path(__file__).resolve().parents[1]
        self.app_path = self.root / "src" / "ui" / "project_studio.py"
        self.app_path.parent.mkdir(parents=True)
        shutil.copy2(
            repository_root / "src" / "ui" / "project_studio.py",
            self.app_path,
        )
        self.first_project = self._write_project(
            "first",
            title="First Project",
        )
        self.second_project = self._write_project(
            "second",
            title="Second Project",
        )
        (self.root / "outside.json").write_text(
            self.first_project.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def test_valid_autoload_loads_once_and_does_not_revert_rerun_changes(self):
        token = "valid-token"
        with self._autoload_environment(
            project="projects/first.json",
            token=token,
        ), chdir(self.root):
            app = self._run_app()

            self._assert_loaded(app, "projects/first.json", "First Project")
            self.assertEqual(
                app.session_state["autoload_consumed_token"],
                token,
            )
            title = next(
                item
                for item in app.text_input
                if item.label == "Video title"
            )
            title.set_value("Changed after autoload")
            app.run()
            app.run()

            self.assertEqual(
                app.session_state["current_project_draft"]["project_data"][
                    "chart"
                ]["title"],
                "Changed after autoload",
            )
            self.assertEqual(
                app.session_state["loaded_project_path"],
                "projects/first.json",
            )

    def test_new_token_can_request_another_project(self):
        with self._autoload_environment(
            project="projects/first.json",
            token="first-token",
        ), chdir(self.root):
            app = self._run_app()
            self._assert_loaded(app, "projects/first.json", "First Project")

            os.environ[open_production_package.AUTOLOAD_PROJECT_ENV] = (
                "projects/second.json"
            )
            os.environ[open_production_package.AUTOLOAD_TOKEN_ENV] = (
                "second-token"
            )
            app.run()

            self._assert_loaded(
                app,
                "projects/second.json",
                "Second Project",
            )
            self.assertEqual(
                app.session_state["autoload_consumed_token"],
                "second-token",
            )

    def test_invalid_autoload_paths_are_rejected_without_loading(self):
        invalid_paths = (
            str(self.first_project.resolve()),
            "../outside.json",
            "outside.json",
        )
        for index, requested_project in enumerate(invalid_paths):
            with self.subTest(requested_project=requested_project):
                with self._autoload_environment(
                    project=requested_project,
                    token=f"invalid-token-{index}",
                ), chdir(self.root):
                    app = self._run_app()

                self.assertFalse(app.exception)
                error_text = "\n".join(error.value for error in app.error)
                self.assertIn("Auto-load request rejected", error_text)
                self.assertEqual(self._project_selector(app).value, "")
                self.assertFalse(
                    any(
                        caption.value in (
                            "projects/first.json",
                            "projects/second.json",
                        )
                        for caption in app.caption
                    )
                )

    def test_without_environment_keeps_manual_selection_behavior(self):
        with self._autoload_environment(), chdir(self.root):
            app = self._run_app()
            self.assertFalse(app.exception)
            self.assertEqual(self._project_selector(app).value, "")
            self.assertFalse(
                any(
                    "Auto-load request rejected" in error.value
                    for error in app.error
                )
            )

            self._project_selector(app).set_value("projects/first.json")
            self._button(app, "Load project").click()
            app.run()

            self._assert_loaded(app, "projects/first.json", "First Project")
            self.assertIsNone(
                app.session_state["autoload_consumed_token"]
            )

    def _write_project(self, slug, *, title):
        dataset_path = self.root / "data" / f"{slug}.csv"
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        dataset_path.write_text(
            "year,name,value\n"
            "2000,Alpha,10\n"
            "2001,Alpha,12\n",
            encoding="utf-8",
        )
        project_path = self.root / "projects" / f"{slug}.json"
        project_path.parent.mkdir(parents=True, exist_ok=True)
        project_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": title,
                    "chart": {
                        "title": title,
                        "width": 320,
                        "height": 180,
                        "dpi": 80,
                        "logos_enabled": False,
                        "max_visible_bars": 1,
                        "output_file": f"output/{slug}.mp4",
                        "frames_dir": f"output/{slug}-frames",
                    },
                    "selection": {
                        "top_n": 1,
                        "aggregate_other": False,
                    },
                    "data_source": {
                        "source_type": "csv",
                        "csv_path": f"data/{slug}.csv",
                    },
                    "dataset": {
                        "year_column": "year",
                        "name_column": "name",
                        "value_column": "value",
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return project_path

    @contextlib.contextmanager
    def _autoload_environment(self, *, project=None, token=None):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(
                open_production_package.AUTOLOAD_PROJECT_ENV,
                None,
            )
            os.environ.pop(
                open_production_package.AUTOLOAD_TOKEN_ENV,
                None,
            )
            if project is not None:
                os.environ[
                    open_production_package.AUTOLOAD_PROJECT_ENV
                ] = project
            if token is not None:
                os.environ[
                    open_production_package.AUTOLOAD_TOKEN_ENV
                ] = token
            yield

    def _run_app(self):
        return AppTest.from_file(
            str(self.app_path),
            default_timeout=30,
        ).run()

    def _assert_loaded(self, app, project_path, title):
        self.assertFalse(app.exception)
        self.assertEqual(
            app.session_state["loaded_project_path"],
            project_path,
        )
        self.assertEqual(
            app.session_state["loaded_project_data"]["name"],
            title,
        )
        selector = self._project_selector(app)
        self.assertEqual(selector.value, project_path)
        self.assertIn(project_path, selector.options)

    @staticmethod
    def _project_selector(app):
        return next(
            item for item in app.selectbox if item.label == "Open project"
        )

    @staticmethod
    def _button(app, label):
        return next(button for button in app.button if button.label == label)


if __name__ == "__main__":
    unittest.main()
