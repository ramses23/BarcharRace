import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from streamlit.testing.v1 import AppTest

import _test_path
from studio.project_bundle import ProjectBundleError, ProjectBundleImport


class ProjectStudioBundleImportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.app_path = cls.root / "src" / "ui" / "project_studio.py"

    def test_valid_zip_imports_once_selects_and_loads_project(self):
        project_path, project_relative = self._new_imported_project_path()
        importer = self._importer_that_creates(project_path)
        try:
            with patch(
                "studio.project_bundle.import_project_bundle",
                side_effect=importer,
            ) as import_mock:
                app = AppTest.from_file(
                    str(self.app_path),
                    default_timeout=30,
                ).run()
                self._mark_draft_saved(app)
                uploader = next(
                    item
                    for item in app.file_uploader
                    if item.label == "Project bundle"
                )
                uploader.set_value(
                    ("production.zip", b"zip bytes", "application/zip")
                )
                self._button(app, "Import and open").click()
                app.run()

                self.assertEqual(import_mock.call_count, 1)
                self.assertEqual(import_mock.call_args.args, (b"zip bytes",))
                self.assertEqual(import_mock.call_args.kwargs, {"root_dir": self.root})
                self._assert_project_selected_and_loaded(
                    app,
                    project_path,
                    project_relative,
                )
                self.assertTrue(
                    any(project_relative in caption.value for caption in app.caption)
                )
                self.assertTrue(
                    any("4 verified files" in caption.value for caption in app.caption)
                )

                app.run()
                self.assertEqual(import_mock.call_count, 1)
                refreshed_uploader = next(
                    item
                    for item in app.file_uploader
                    if item.label == "Project bundle"
                )
                self.assertIsNone(refreshed_uploader.value)
        finally:
            project_path.unlink(missing_ok=True)

    def test_valid_folder_uses_same_importer_and_selects_project(self):
        project_path, project_relative = self._new_imported_project_path()
        importer = self._importer_that_creates(project_path)
        try:
            with tempfile.TemporaryDirectory() as folder_dir, patch(
                "studio.project_bundle.import_project_bundle",
                side_effect=importer,
            ) as import_mock:
                app = AppTest.from_file(
                    str(self.app_path),
                    default_timeout=30,
                ).run()
                self._mark_draft_saved(app)
                source = next(
                    item
                    for item in app.get("button_group")
                    if item.label == "Package source"
                )
                source.set_value("Local folder")
                app.run()
                folder_input = next(
                    item
                    for item in app.text_input
                    if item.label == "Production folder path"
                )
                folder_input.set_value(folder_dir)
                self._button(app, "Import and open").click()
                app.run()

                self.assertEqual(import_mock.call_count, 1)
                self.assertEqual(
                    import_mock.call_args.args,
                    (Path(folder_dir),),
                )
                self.assertEqual(import_mock.call_args.kwargs, {"root_dir": self.root})
                self._assert_project_selected_and_loaded(
                    app,
                    project_path,
                    project_relative,
                )
        finally:
            project_path.unlink(missing_ok=True)

    def test_import_error_preserves_active_project_and_draft(self):
        with patch(
            "studio.project_bundle.import_project_bundle",
            side_effect=ProjectBundleError("bundle is invalid"),
        ) as import_mock:
            app = AppTest.from_file(
                str(self.app_path),
                default_timeout=30,
            ).run()
            self._mark_draft_saved(app)
            project_selector = next(
                item for item in app.selectbox if item.label == "Open project"
            )
            project_selector.set_value("projects/sample_project.json")
            self._button(app, "Load project").click()
            app.run()
            self._mark_draft_saved(app)
            active_path = app.session_state["loaded_project_path"]
            active_data = copy.deepcopy(app.session_state["loaded_project_data"])
            active_draft = copy.deepcopy(
                app.session_state["current_project_draft"]
            )

            uploader = next(
                item
                for item in app.file_uploader
                if item.label == "Project bundle"
            )
            uploader.set_value(("broken.zip", b"broken", "application/zip"))
            self._button(app, "Import and open").click()
            app.run()

            self.assertEqual(import_mock.call_count, 1)
            self.assertFalse(app.exception)
            self.assertTrue(
                any("bundle is invalid" in error.value for error in app.error)
            )
            self.assertEqual(app.session_state["loaded_project_path"], active_path)
            self.assertEqual(app.session_state["loaded_project_data"], active_data)
            self.assertEqual(
                app.session_state["current_project_draft"],
                active_draft,
            )
            self.assertIsNone(
                app.session_state["last_project_bundle_import"]
            )
            retained_uploader = next(
                item
                for item in app.file_uploader
                if item.label == "Project bundle"
            )
            self.assertIsNotNone(retained_uploader.value)

    def _new_imported_project_path(self):
        name = f"ui_bundle_import_{uuid4().hex}"
        relative = f"projects/{name}.json"
        return self.root / relative, relative

    def _importer_that_creates(self, project_path):
        def importer(bundle, *, root_dir):
            self.assertEqual(root_dir, self.root)
            project_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": project_path.stem,
                        "data_source": {
                            "source_type": "csv",
                            "csv_path": "data/datasets/sample_dynamic.csv",
                        },
                    }
                ),
                encoding="utf-8",
            )
            return ProjectBundleImport(
                project_path=str(project_path),
                asset_directory=str(
                    self.root / "projects" / "imported" / project_path.stem
                ),
                file_count=4,
                uncompressed_size=1024,
            )

        return importer

    @staticmethod
    def _mark_draft_saved(app):
        app.session_state["saved_project_draft_fingerprint"] = (
            app.session_state["current_project_draft_fingerprint"]
        )

    def _assert_project_selected_and_loaded(
        self,
        app,
        project_path,
        project_relative,
    ):
        self.assertFalse(app.exception)
        self.assertTrue(project_path.is_file())
        self.assertEqual(
            app.session_state["loaded_project_path"],
            project_relative,
        )
        self.assertEqual(
            app.session_state["loaded_project_data"]["name"],
            project_path.stem,
        )
        selector = next(
            item for item in app.selectbox if item.label == "Open project"
        )
        self.assertIn(project_relative, selector.options)
        self.assertEqual(selector.value, project_relative)

    @staticmethod
    def _button(app, label):
        return next(button for button in app.button if button.label == label)


if __name__ == "__main__":
    unittest.main()
