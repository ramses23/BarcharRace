import copy
import hashlib
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from contextlib import chdir
from pathlib import Path

from streamlit.testing.v1 import AppTest

import _test_path
from PIL import Image
from config.project_file_loader import load_project_file
from studio.package_paths import resolve_project_path
from studio.preview import _resolved_dataset_config, render_project_preview
from studio.project_builder import load_project_data
from studio.project_bundle import MANIFEST_PATH, build_project_bundle
from studio.render_preflight import run_render_preflight


class ProjectStudioBundleEndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository_root = Path(__file__).resolve().parents[1]
        cls.project_studio_path = (
            cls.repository_root / "src" / "ui" / "project_studio.py"
        )

    def test_real_zip_import_save_preview_and_preflight(self):
        sandbox_root = None
        with tempfile.TemporaryDirectory(
            prefix="barchart-studio-e2e-"
        ) as temp_dir:
            sandbox_root = Path(temp_dir)
            source_root = sandbox_root / "bundle-source"
            studio_root = sandbox_root / "studio-root"
            app_path = self._isolated_project_studio(studio_root)
            exported = self._build_bundle(
                source_root,
                project_name="E2E Production",
            )
            self._assert_real_bundle_contract(
                exported.data,
                project_name="e2e_production",
            )

            project_relative = "projects/e2e_production.json"
            imported_project = studio_root / project_relative
            imported_assets = (
                studio_root / "projects" / "imported" / "e2e_production"
            )
            resolved_imported_assets = imported_assets.resolve()

            with chdir(studio_root):
                app = AppTest.from_file(
                    str(app_path),
                    default_timeout=30,
                ).run()
                self._mark_draft_saved(app)
                self._upload_bundle(app, exported.data, exported.filename)
                self._button(app, "Import and open").click()
                app.run()

                self.assertFalse(app.exception)
                self.assertTrue(imported_project.is_file())
                self.assertTrue(imported_assets.is_dir())
                selector = self._project_selector(app)
                self.assertIn(project_relative, selector.options)
                self.assertEqual(selector.value, project_relative)
                self.assertEqual(
                    app.session_state["loaded_project_path"],
                    project_relative,
                )
                self.assertEqual(
                    app.session_state["loaded_project_data"],
                    load_project_data(imported_project),
                )

                video_title = next(
                    item
                    for item in app.text_input
                    if item.label == "Video title"
                )
                video_title.set_value("E2E Production Saved")
                app.run()
                self.assertNotEqual(
                    app.session_state["saved_project_draft_fingerprint"],
                    app.session_state["current_project_draft_fingerprint"],
                )
                self._button(app, "Save project").click()
                app.run()

                self.assertFalse(app.exception)
                self.assertEqual(
                    app.session_state["saved_project_draft_fingerprint"],
                    app.session_state["current_project_draft_fingerprint"],
                )
                saved_project = load_project_data(imported_project)
                self.assertEqual(
                    saved_project["chart"]["title"],
                    "E2E Production Saved",
                )
                self.assertEqual(
                    app.session_state["loaded_project_data"],
                    saved_project,
                )

            preview_path = Path(
                render_project_preview(
                    project_relative,
                    output_dir="output/e2e-preview",
                    year=2001,
                    root_dir=studio_root,
                )
            )
            self.assertTrue(preview_path.is_file())
            self.assertGreater(preview_path.stat().st_size, 0)
            with Image.open(preview_path) as preview_image:
                preview_image.load()
                self.assertEqual(preview_image.format, "PNG")
                self.assertEqual(preview_image.size, (320, 180))

            preflight = run_render_preflight(
                project_relative,
                root_dir=studio_root,
                ffmpeg_path="ffmpeg",
            )
            blocking_errors = [
                check for check in preflight.checks if check.level == "error"
            ]
            self.assertTrue(
                preflight.ready,
                msg="; ".join(check.message for check in blocking_errors),
            )
            self.assertEqual(blocking_errors, [])

            preset = load_project_file(imported_project)
            dataset_path = resolve_project_path(
                preset.data_source_config.csv_path,
                project_root=studio_root,
                required=True,
                field_name="data_source.csv_path",
            )
            self.assertTrue(dataset_path.is_file())
            self.assertTrue(
                dataset_path.is_relative_to(resolved_imported_assets)
            )

            preview_dataset = _resolved_dataset_config(
                preset.dataset_config,
                studio_root,
            )
            preflight_logo_paths = self._resolved_logo_paths(
                preset,
                studio_root,
            )
            self.assertEqual(
                preview_dataset.category_logos,
                preflight_logo_paths["primary"],
            )
            self.assertEqual(
                preview_dataset.category_secondary_logos,
                preflight_logo_paths["secondary"],
            )
            for resolved_path in (
                *preflight_logo_paths["primary"].values(),
                *preflight_logo_paths["secondary"].values(),
            ):
                path = Path(resolved_path)
                self.assertTrue(path.is_file())
                self.assertTrue(path.is_relative_to(resolved_imported_assets))

            checks = {check.key: check for check in preflight.checks}
            self.assertNotIn("logos", checks)
            expected_background = resolve_project_path(
                preset.chart_config.background_image_path,
                project_root=studio_root,
                required=True,
                field_name="chart.background_image_path",
            )
            self.assertEqual(
                checks["background"].message,
                str(expected_background),
            )
            self.assertTrue(
                expected_background.is_relative_to(resolved_imported_assets)
            )
            self.assertEqual(list(studio_root.rglob("*.tmp")), [])

        self.assertIsNotNone(sandbox_root)
        self.assertFalse(sandbox_root.exists())

    def test_real_zip_with_corrupt_image_preserves_selected_project(self):
        sandbox_root = None
        with tempfile.TemporaryDirectory(
            prefix="barchart-studio-corrupt-e2e-"
        ) as temp_dir:
            sandbox_root = Path(temp_dir)
            source_root = sandbox_root / "bundle-source"
            studio_root = sandbox_root / "studio-root"
            app_path = self._isolated_project_studio(studio_root)
            active_project = self._write_active_project(studio_root)
            active_project_bytes = active_project.read_bytes()
            exported = self._build_bundle(
                source_root,
                project_name="Broken Production",
                corrupt_primary_logo=True,
            )
            self._assert_real_bundle_contract(
                exported.data,
                project_name="broken_production",
            )

            broken_project = studio_root / "projects" / "broken_production.json"
            broken_assets = (
                studio_root / "projects" / "imported" / "broken_production"
            )

            with chdir(studio_root):
                app = AppTest.from_file(
                    str(app_path),
                    default_timeout=30,
                ).run()
                self._project_selector(app).set_value("projects/active.json")
                self._button(app, "Load project").click()
                app.run()
                self._mark_draft_saved(app)
                active_path = app.session_state["loaded_project_path"]
                active_data = copy.deepcopy(
                    app.session_state["loaded_project_data"]
                )
                active_draft = copy.deepcopy(
                    app.session_state["current_project_draft"]
                )

                self._upload_bundle(app, exported.data, exported.filename)
                self._button(app, "Import and open").click()
                app.run()

                self.assertFalse(app.exception)
                error_text = "\n".join(error.value for error in app.error)
                self.assertIn("corrupt or unsupported", error_text)
                self.assertIn("categories['Alpha'].logo", error_text)
                self.assertEqual(
                    app.session_state["loaded_project_path"],
                    active_path,
                )
                self.assertEqual(
                    app.session_state["loaded_project_data"],
                    active_data,
                )
                self.assertEqual(
                    app.session_state["current_project_draft"],
                    active_draft,
                )
                self.assertEqual(
                    self._project_selector(app).value,
                    "projects/active.json",
                )
                self.assertIsNone(
                    app.session_state["last_project_bundle_import"]
                )

            self.assertFalse(broken_project.exists())
            self.assertFalse(broken_assets.exists())
            self.assertEqual(active_project.read_bytes(), active_project_bytes)
            self.assertEqual(list(studio_root.rglob("*.tmp")), [])

        self.assertIsNotNone(sandbox_root)
        self.assertFalse(sandbox_root.exists())

    def _isolated_project_studio(self, studio_root):
        app_path = studio_root / "src" / "ui" / "project_studio.py"
        app_path.parent.mkdir(parents=True)
        shutil.copy2(self.project_studio_path, app_path)
        return app_path

    @staticmethod
    def _build_bundle(
        source_root,
        *,
        project_name,
        corrupt_primary_logo=False,
    ):
        dataset_path = source_root / "data" / "dataset.csv"
        dataset_path.parent.mkdir(parents=True)
        dataset_path.write_text(
            "year,name,value\n"
            "2000,Alpha,10\n"
            "2000,Beta,8\n"
            "2001,Alpha,12\n"
            "2001,Beta,11\n",
            encoding="utf-8",
        )
        images = {
            "backgrounds/background.png": (18, 28, 44, 255),
            "logos/alpha.png": (78, 121, 167, 255),
            "logos/beta.png": (89, 161, 79, 255),
            "logos_secondary/alpha.png": (242, 142, 43, 255),
            "logos_secondary/beta.png": (225, 87, 89, 255),
        }
        for relative_path, color in images.items():
            destination = source_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            if corrupt_primary_logo and relative_path == "logos/alpha.png":
                destination.write_bytes(b"not a real PNG")
            else:
                Image.new("RGBA", (8, 8), color).save(destination)

        project = {
            "schema_version": 1,
            "name": project_name,
            "chart": {
                "title": "E2E Production",
                "layout_preset": "compact_dashboard",
                "theme": "clean_report",
                "typography_preset": "compact",
                "width": 320,
                "height": 180,
                "dpi": 80,
                "left_margin": 90,
                "right_margin": 24,
                "top_margin": 52,
                "bottom_margin": 24,
                "bar_height": 24,
                "bar_gap": 8,
                "title_font_size": 12,
                "subtitle_font_size": 8,
                "time_label_font_size": 28,
                "source_font_size": 6,
                "label_font_size": 7,
                "value_font_size": 7,
                "title_y": 15,
                "subtitle_y": 30,
                "time_label_x": 290,
                "time_label_y": 148,
                "source_x": 90,
                "source_y": 170,
                "rank_labels_enabled": False,
                "logos_enabled": True,
                "logo_size": 18,
                "logo_gap": 6,
                "logo_label_gap": 6,
                "bar_secondary_logo_enabled": True,
                "bar_secondary_logo_size": 10,
                "bar_secondary_logo_padding": 1,
                "bar_secondary_logo_border_width": 1.0,
                "max_visible_bars": 2,
                "fps": 2,
                "steps_per_transition": 2,
                "output_file": "output/source.mp4",
                "frames_dir": "output/source-frames",
                "background_mode": "image",
                "background_image_path": "backgrounds/background.png",
                "background_image_fit": "cover",
                "png_compress_level": 1,
            },
            "selection": {
                "top_n": 2,
                "aggregate_other": False,
            },
            "data_source": {
                "source_type": "csv",
                "csv_path": "data/dataset.csv",
                "source_label_override": "Source: E2E fixture",
            },
            "dataset": {
                "year_column": "year",
                "name_column": "name",
                "value_column": "value",
            },
            "categories": {
                "Alpha": {
                    "logo": "logos/alpha.png",
                    "secondary_logo": "logos_secondary/alpha.png",
                },
                "Beta": {
                    "logo": "logos/beta.png",
                    "secondary_logo": "logos_secondary/beta.png",
                },
            },
        }
        return build_project_bundle(project, root_dir=source_root)

    def _assert_real_bundle_contract(self, bundle_data, *, project_name):
        with zipfile.ZipFile(io.BytesIO(bundle_data)) as archive:
            manifest = json.loads(archive.read(MANIFEST_PATH))
            records = {
                record["path"]: record for record in manifest["files"]
            }
            self.assertEqual(manifest["bundle_schema_version"], 1)
            self.assertEqual(manifest["project_name"], project_name)
            self.assertEqual(manifest["project_file"], "project.json")
            self.assertEqual(
                set(archive.namelist()),
                {MANIFEST_PATH, *records},
            )
            for path, record in records.items():
                payload = archive.read(path)
                self.assertEqual(set(record), {"path", "size", "sha256"})
                self.assertEqual(record["size"], len(payload))
                self.assertEqual(
                    record["sha256"],
                    hashlib.sha256(payload).hexdigest(),
                )

    @staticmethod
    def _write_active_project(studio_root):
        dataset_path = studio_root / "data" / "datasets" / "active.csv"
        dataset_path.parent.mkdir(parents=True)
        dataset_path.write_text(
            "year,name,value\n2000,Active,1\n2001,Active,2\n",
            encoding="utf-8",
        )
        project_path = studio_root / "projects" / "active.json"
        project_path.parent.mkdir(parents=True)
        project_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "Active Project",
                    "chart": {
                        "title": "Active Project",
                        "width": 320,
                        "height": 180,
                        "dpi": 80,
                        "logos_enabled": False,
                        "max_visible_bars": 1,
                        "output_file": "output/active.mp4",
                        "frames_dir": "output/active-frames",
                    },
                    "selection": {
                        "top_n": 1,
                        "aggregate_other": False,
                    },
                    "data_source": {
                        "source_type": "csv",
                        "csv_path": "data/datasets/active.csv",
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
    def _resolved_logo_paths(preset, project_root):
        return {
            "primary": {
                category: str(
                    resolve_project_path(
                        value,
                        project_root=project_root,
                        required=True,
                        field_name=(
                            f"dataset.category_logos[{category!r}]"
                        ),
                    )
                )
                for category, value in preset.dataset_config.category_logos.items()
            },
            "secondary": {
                category: str(
                    resolve_project_path(
                        value,
                        project_root=project_root,
                        required=True,
                        field_name=(
                            "dataset.category_secondary_logos"
                            f"[{category!r}]"
                        ),
                    )
                )
                for category, value in (
                    preset.dataset_config.category_secondary_logos.items()
                )
            },
        }

    @staticmethod
    def _upload_bundle(app, bundle_data, filename):
        uploader = next(
            item
            for item in app.file_uploader
            if item.label == "Project bundle"
        )
        uploader.set_value((filename, bundle_data, "application/zip"))

    @staticmethod
    def _mark_draft_saved(app):
        app.session_state["saved_project_draft_fingerprint"] = (
            app.session_state["current_project_draft_fingerprint"]
        )

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
