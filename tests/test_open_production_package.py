import contextlib
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
