import copy
import hashlib
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import _test_path
from PIL import Image
from config.project_file_loader import load_project_file
from pipeline.render_job import RenderJob
from studio.project_bundle import (
    MANIFEST_PATH,
    ProjectBundleError,
    build_project_bundle,
    import_project_bundle,
)


class ProjectBundleTest(unittest.TestCase):
    def test_exports_and_imports_complete_portable_project(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            project = self._project_fixture(source_root)
            original = copy.deepcopy(project)

            exported = build_project_bundle(project, root_dir=source_root)
            imported = import_project_bundle(exported.data, root_dir=target_root)

            imported_path = Path(imported.project_path)
            imported_asset_directory = Path(imported.asset_directory)
            imported_data = json.loads(imported_path.read_text(encoding="utf-8"))
            referenced_paths = (
                imported_data["data_source"]["csv_path"],
                imported_data["chart"]["background_image_path"],
                imported_data["chart"]["bar_texture_custom_image"],
                imported_data["categories"]["Alpha"]["logo"],
                imported_data["categories"]["Alpha"]["secondary_logo"],
            )

            self.assertEqual(project, original)
            self.assertEqual(exported.filename, "portable_project.barchart.zip")
            self.assertEqual(imported_path.name, "portable_project.json")
            self.assertTrue(imported_path.is_file())
            self.assertTrue(imported_asset_directory.is_dir())
            self.assertEqual(imported_data["name"], "portable_project")
            self.assertEqual(
                imported_data["chart"]["output_file"],
                "output/portable_project.mp4",
            )
            self.assertTrue(all(path.startswith("projects/imported/portable_project/") for path in referenced_paths))
            self.assertTrue(all((target_root / path).is_file() for path in referenced_paths))
            self.assertEqual(
                (target_root / referenced_paths[0]).read_text(encoding="utf-8"),
                "year,name,value\n2020,Alpha,10\n2021,Alpha,12\n",
            )
            self.assertEqual(load_project_file(imported_path).name, "portable_project")

    def test_rejects_non_numeric_dataset_before_publishing(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            project = self._project_fixture(source_root)
            (source_root / "data" / "source.csv").write_text(
                "year,name,value\n2020,Alpha,not-a-number\n2021,Alpha,12\n",
                encoding="utf-8",
            )
            exported = build_project_bundle(project, root_dir=source_root)

            with self.assertRaisesRegex(ProjectBundleError, "non-numeric values"):
                import_project_bundle(exported.data, root_dir=target_root)

            self._assert_failed_import_is_clean(target_root)

    def test_rejects_duplicate_dataset_rows_before_publishing(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            project = self._project_fixture(source_root)
            (source_root / "data" / "source.csv").write_text(
                "year,name,value\n2020,Alpha,10\n2020,Alpha,12\n",
                encoding="utf-8",
            )
            exported = build_project_bundle(project, root_dir=source_root)

            with self.assertRaisesRegex(
                ProjectBundleError,
                "Duplicate year/name combinations",
            ):
                import_project_bundle(exported.data, root_dir=target_root)

            self._assert_failed_import_is_clean(target_root)

    def test_failure_after_staging_preparation_leaves_no_temporaries(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            project = self._project_fixture(source_root)
            project["data_source"]["source_type"] = "unsupported"
            exported = build_project_bundle(project, root_dir=source_root)

            with self.assertRaisesRegex(
                ProjectBundleError,
                "unsupported data source type",
            ):
                import_project_bundle(exported.data, root_dir=target_root)

            self._assert_failed_import_is_clean(target_root)

    def test_export_is_deterministic_and_manifest_checksums_every_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = self._project_fixture(root)

            first = build_project_bundle(project, root_dir=root)
            second = build_project_bundle(project, root_dir=root)

            self.assertEqual(first.data, second.data)
            with zipfile.ZipFile(io.BytesIO(first.data)) as archive:
                manifest = json.loads(archive.read(MANIFEST_PATH))
                records = {record["path"]: record for record in manifest["files"]}

                self.assertEqual(
                    set(archive.namelist()),
                    {MANIFEST_PATH, *records},
                )
                for path, record in records.items():
                    payload = archive.read(path)
                    self.assertEqual(record["size"], len(payload))
                    self.assertEqual(
                        record["sha256"],
                        hashlib.sha256(payload).hexdigest(),
                    )

    def test_duplicate_import_uses_a_non_destructive_suffix(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            exported = build_project_bundle(
                self._project_fixture(source_root),
                root_dir=source_root,
            )

            first = import_project_bundle(exported.data, root_dir=target_root)
            second = import_project_bundle(exported.data, root_dir=target_root)

            self.assertEqual(Path(first.project_path).name, "portable_project.json")
            self.assertEqual(Path(second.project_path).name, "portable_project_2.json")
            self.assertTrue(Path(first.project_path).is_file())
            self.assertTrue(Path(second.project_path).is_file())

    def test_rejects_tampered_payload(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            exported = build_project_bundle(
                self._project_fixture(source_root),
                root_dir=source_root,
            )
            tampered = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(exported.data)) as source_archive:
                with zipfile.ZipFile(tampered, "w") as target_archive:
                    for name in source_archive.namelist():
                        payload = source_archive.read(name)
                        if name.startswith("data/"):
                            payload = bytes([payload[0] ^ 0xFF]) + payload[1:]
                        target_archive.writestr(name, payload)

            with self.assertRaisesRegex(ProjectBundleError, "Checksum failed"):
                import_project_bundle(tampered.getvalue(), root_dir=target_dir)

    def test_rejects_unsafe_archive_path(self):
        payload = b"unsafe"
        digest = hashlib.sha256(payload).hexdigest()
        manifest = {
            "bundle_schema_version": 1,
            "project_name": "unsafe",
            "project_file": "project.json",
            "files": [
                {"path": "../evil.txt", "size": len(payload), "sha256": digest}
            ],
        }
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w") as archive:
            archive.writestr(MANIFEST_PATH, json.dumps(manifest))
            archive.writestr("../evil.txt", payload)

        with tempfile.TemporaryDirectory() as target_dir:
            with self.assertRaisesRegex(ProjectBundleError, "unsafe file path"):
                import_project_bundle(bundle.getvalue(), root_dir=target_dir)

            self.assertFalse((Path(target_dir).parent / "evil.txt").exists())

    def test_rejects_case_insensitive_archive_collisions(self):
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w") as archive:
            archive.writestr(MANIFEST_PATH, "{}")
            archive.writestr("assets/Logo.png", b"first")
            archive.writestr("assets/logo.png", b"second")

        with tempfile.TemporaryDirectory() as target_dir:
            with self.assertRaisesRegex(ProjectBundleError, "duplicate file names"):
                import_project_bundle(bundle.getvalue(), root_dir=target_dir)

    def test_export_reports_missing_referenced_asset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = self._project_fixture(root)
            project["chart"]["background_image_path"] = "missing.png"

            with self.assertRaisesRegex(ProjectBundleError, "was not found"):
                build_project_bundle(project, root_dir=root)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required for video export")
    def test_imported_bundle_can_render_a_real_video(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            exported = build_project_bundle(
                self._project_fixture(source_root),
                root_dir=source_root,
            )
            imported = import_project_bundle(exported.data, root_dir=target_root)
            project_path = Path(imported.project_path)
            project_data = json.loads(project_path.read_text(encoding="utf-8"))
            preset = load_project_file(project_path)
            chart = project_data["chart"]
            categories = project_data["categories"]
            output_file = target_root / "output" / "portable.mp4"
            frames_dir = target_root / "output" / "frames"
            chart_config = replace(
                preset.chart_config,
                width=320,
                height=180,
                dpi=72,
                left_margin=100,
                right_margin=24,
                top_margin=52,
                bottom_margin=24,
                bar_height=22,
                bar_gap=8,
                title_font_size=12,
                subtitle_font_size=8,
                label_font_size=8,
                value_font_size=8,
                rank_label_font_size=7,
                time_label_font_size=28,
                source_font_size=6,
                title_y=14,
                subtitle_y=30,
                time_label_x=300,
                time_label_y=150,
                source_x=100,
                source_y=170,
                fps=2,
                steps_per_transition=2,
                output_file=str(output_file),
                frames_dir=str(frames_dir),
                background_image_path=str(
                    target_root / chart["background_image_path"]
                ),
                bar_texture_custom_image=str(
                    target_root / chart["bar_texture_custom_image"]
                ),
            )
            dataset_config = replace(
                preset.dataset_config,
                category_logos={
                    "Alpha": str(target_root / categories["Alpha"]["logo"])
                },
                category_secondary_logos={
                    "Alpha": str(
                        target_root / categories["Alpha"]["secondary_logo"]
                    )
                },
            )
            data_source_config = replace(
                preset.data_source_config,
                csv_path=str(
                    target_root / project_data["data_source"]["csv_path"]
                ),
            )

            with patch("builtins.print"):
                result = RenderJob(
                    config=chart_config,
                    data_source_config=data_source_config,
                    dataset_config=dataset_config,
                ).run()

            self.assertEqual(result.frames_rendered, 2)
            self.assertTrue(output_file.is_file())
            self.assertGreater(output_file.stat().st_size, 0)

    @staticmethod
    def _project_fixture(root):
        csv_path = root / "data" / "source.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_bytes(
            b"year,name,value\n2020,Alpha,10\n2021,Alpha,12\n"
        )
        images = {
            "backgrounds/background.png": (18, 28, 44, 255),
            "textures/texture.png": (110, 125, 145, 255),
            "logos/alpha.png": (78, 121, 167, 255),
            "logos_secondary/alpha.png": (242, 142, 43, 255),
        }
        for relative_path, color in images.items():
            destination = root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (8, 8), color).save(destination)

        return {
            "schema_version": 1,
            "name": "Portable Project",
            "chart": {
                "title": "Portable",
                "output_file": "output/original.mp4",
                "frames_dir": "output/original_frames",
                "background_mode": "image",
                "background_image_path": "backgrounds/background.png",
                "bar_texture_enabled": True,
                "bar_texture_preset": "custom_image",
                "bar_texture_custom_image": "textures/texture.png",
                "bar_appearance_mode": "advanced",
            },
            "data_source": {
                "source_type": "csv",
                "csv_path": "data/source.csv",
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
                }
            },
        }

    def _assert_failed_import_is_clean(self, root):
        self.assertFalse((root / "projects" / "portable_project.json").exists())
        self.assertFalse(
            (root / "projects" / "imported" / "portable_project").exists()
        )
        self.assertEqual(list(root.rglob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
