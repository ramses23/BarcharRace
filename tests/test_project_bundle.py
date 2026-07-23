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

    def test_imports_valid_extracted_bundle_folder_without_modifying_source(self):
        with (
            tempfile.TemporaryDirectory() as source_dir,
            tempfile.TemporaryDirectory() as package_dir,
            tempfile.TemporaryDirectory() as target_dir,
        ):
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            exported = build_project_bundle(
                self._project_fixture(source_root),
                root_dir=source_root,
            )
            package_root = self._extract_bundle_folder(
                exported.data,
                Path(package_dir),
            )
            original_package = self._file_snapshot(package_root)

            imported = import_project_bundle(package_root, root_dir=target_root)

            self.assertTrue(Path(imported.project_path).is_file())
            self.assertTrue(Path(imported.asset_directory).is_dir())
            self.assertEqual(self._file_snapshot(package_root), original_package)

    def test_zip_path_and_folder_imports_are_equivalent(self):
        with (
            tempfile.TemporaryDirectory() as source_dir,
            tempfile.TemporaryDirectory() as package_dir,
            tempfile.TemporaryDirectory() as zip_target_dir,
            tempfile.TemporaryDirectory() as folder_target_dir,
        ):
            source_root = Path(source_dir)
            exported = build_project_bundle(
                self._project_fixture(source_root),
                root_dir=source_root,
            )
            package_parent = Path(package_dir)
            zip_path = package_parent / exported.filename
            zip_path.write_bytes(exported.data)
            package_root = self._extract_bundle_folder(
                exported.data,
                package_parent,
            )

            zip_import = import_project_bundle(
                zip_path,
                root_dir=Path(zip_target_dir),
            )
            folder_import = import_project_bundle(
                package_root,
                root_dir=Path(folder_target_dir),
            )

            zip_project = json.loads(
                Path(zip_import.project_path).read_text(encoding="utf-8")
            )
            folder_project = json.loads(
                Path(folder_import.project_path).read_text(encoding="utf-8")
            )
            self.assertEqual(zip_project, folder_project)
            self.assertEqual(
                self._file_snapshot(Path(zip_import.asset_directory)),
                self._file_snapshot(Path(folder_import.asset_directory)),
            )

    def test_rejects_folder_with_incorrect_hash_without_publishing(self):
        with (
            tempfile.TemporaryDirectory() as source_dir,
            tempfile.TemporaryDirectory() as package_dir,
            tempfile.TemporaryDirectory() as target_dir,
        ):
            source_root = Path(source_dir)
            exported = build_project_bundle(
                self._project_fixture(source_root),
                root_dir=source_root,
            )
            package_root = self._extract_bundle_folder(
                exported.data,
                Path(package_dir),
            )
            manifest = json.loads(
                (package_root / MANIFEST_PATH).read_text(encoding="utf-8")
            )
            dataset_path = next(
                record["path"]
                for record in manifest["files"]
                if record["path"].startswith("data/")
            )
            dataset_file = package_root.joinpath(*Path(dataset_path).parts)
            tampered = bytearray(dataset_file.read_bytes())
            tampered[-2] ^= 0x01
            dataset_file.write_bytes(tampered)

            with self.assertRaisesRegex(ProjectBundleError, "Checksum failed"):
                import_project_bundle(package_root, root_dir=Path(target_dir))

            self._assert_failed_import_is_clean(Path(target_dir))

    def test_rejects_semantically_invalid_folder_dataset_before_publishing(self):
        with (
            tempfile.TemporaryDirectory() as source_dir,
            tempfile.TemporaryDirectory() as package_dir,
            tempfile.TemporaryDirectory() as target_dir,
        ):
            source_root = Path(source_dir)
            project = self._project_fixture(source_root)
            (source_root / "data" / "source.csv").write_text(
                "year,name,value\n2020,Alpha,invalid\n2021,Alpha,12\n",
                encoding="utf-8",
            )
            exported = build_project_bundle(project, root_dir=source_root)
            package_root = self._extract_bundle_folder(
                exported.data,
                Path(package_dir),
            )

            with self.assertRaisesRegex(ProjectBundleError, "non-numeric values"):
                import_project_bundle(package_root, root_dir=Path(target_dir))

            self._assert_failed_import_is_clean(Path(target_dir))

    def test_rejects_symbolic_link_in_bundle_folder(self):
        with (
            tempfile.TemporaryDirectory() as source_dir,
            tempfile.TemporaryDirectory() as package_dir,
            tempfile.TemporaryDirectory() as target_dir,
        ):
            source_root = Path(source_dir)
            exported = build_project_bundle(
                self._project_fixture(source_root),
                root_dir=source_root,
            )
            package_parent = Path(package_dir)
            package_root = self._extract_bundle_folder(
                exported.data,
                package_parent,
            )
            outside_file = package_parent / "outside.txt"
            outside_file.write_text("outside", encoding="utf-8")
            link_path = package_root / "external-link.txt"
            try:
                link_path.symlink_to(outside_file)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"Symbolic links are unavailable: {exc}")

            with self.assertRaisesRegex(ProjectBundleError, "Symbolic links"):
                import_project_bundle(package_root, root_dir=Path(target_dir))

            self._assert_failed_import_is_clean(Path(target_dir))

    def test_rejects_missing_path_and_non_zip_file(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)

            with self.assertRaisesRegex(ProjectBundleError, "does not exist"):
                import_project_bundle(
                    source_root / "missing.barchart.zip",
                    root_dir=target_root,
                )

            text_file = source_root / "not-a-bundle.txt"
            text_file.write_text("not a bundle", encoding="utf-8")
            with self.assertRaisesRegex(
                ProjectBundleError,
                r"\.zip file or a directory",
            ):
                import_project_bundle(text_file, root_dir=target_root)

            self._assert_failed_import_is_clean(target_root)

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

    def test_rejects_corrupt_logo_before_publishing(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            exported = build_project_bundle(
                self._project_fixture(source_root),
                root_dir=source_root,
            )
            with zipfile.ZipFile(io.BytesIO(exported.data)) as archive:
                project = json.loads(archive.read("project.json"))
            logo_path = project["categories"]["Alpha"]["logo"]
            corrupt_bundle = self._rewrite_bundle(
                exported.data,
                payload_updates={logo_path: b"not an image"},
            )

            with self.assertRaisesRegex(
                ProjectBundleError,
                r"corrupt or unsupported.*categories\['Alpha'\]\.logo",
            ):
                import_project_bundle(corrupt_bundle, root_dir=target_root)

            self._assert_failed_import_is_clean(target_root)

    def test_rejects_missing_secondary_logo_before_publishing(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            exported = build_project_bundle(
                self._project_fixture(source_root),
                root_dir=source_root,
            )

            def use_missing_secondary_logo(project):
                project["categories"]["Alpha"]["secondary_logo"] = (
                    "assets/logos/secondary/missing.png"
                )

            missing_bundle = self._rewrite_bundle(
                exported.data,
                project_mutator=use_missing_secondary_logo,
            )

            with self.assertRaisesRegex(
                ProjectBundleError,
                r"not found.*categories\['Alpha'\]\.secondary_logo",
            ):
                import_project_bundle(missing_bundle, root_dir=target_root)

            self._assert_failed_import_is_clean(target_root)

    def test_imports_bundle_with_valid_background(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            project = self._project_fixture(source_root)
            project["categories"] = {}
            project["chart"]["bar_texture_enabled"] = False
            project["chart"].pop("bar_texture_custom_image")
            exported = build_project_bundle(project, root_dir=source_root)

            imported = import_project_bundle(exported.data, root_dir=target_root)

            imported_project = json.loads(
                Path(imported.project_path).read_text(encoding="utf-8")
            )
            background = target_root / imported_project["chart"][
                "background_image_path"
            ]
            self.assertTrue(background.is_file())

    def test_imports_dataset_logo_maps_as_portable_images(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            project = self._project_fixture(source_root)
            project["categories"] = {}
            project["dataset"]["category_logos"] = {
                "Alpha": "logos/alpha.png"
            }
            project["dataset"]["category_secondary_logos"] = {
                "Alpha": "logos_secondary/alpha.png"
            }
            exported = build_project_bundle(project, root_dir=source_root)

            imported = import_project_bundle(exported.data, root_dir=target_root)

            imported_project = json.loads(
                Path(imported.project_path).read_text(encoding="utf-8")
            )
            dataset = imported_project["dataset"]
            logo_paths = (
                dataset["category_logos"]["Alpha"],
                dataset["category_secondary_logos"]["Alpha"],
            )
            self.assertTrue(
                all(path.startswith("projects/imported/") for path in logo_paths)
            )
            self.assertTrue(all((target_root / path).is_file() for path in logo_paths))

    def test_rejects_absolute_external_image_path_in_portable_bundle(self):
        with (
            tempfile.TemporaryDirectory() as source_dir,
            tempfile.TemporaryDirectory() as external_dir,
            tempfile.TemporaryDirectory() as target_dir,
        ):
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            external_image = Path(external_dir) / "external.png"
            Image.new("RGB", (2, 2), (10, 20, 30)).save(external_image)
            exported = build_project_bundle(
                self._project_fixture(source_root),
                root_dir=source_root,
            )

            def use_absolute_background(project):
                project["chart"]["background_image_path"] = str(external_image)

            non_portable_bundle = self._rewrite_bundle(
                exported.data,
                project_mutator=use_absolute_background,
            )

            with self.assertRaisesRegex(
                ProjectBundleError,
                "portable relative path",
            ):
                import_project_bundle(non_portable_bundle, root_dir=target_root)

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

    @staticmethod
    def _extract_bundle_folder(bundle_data, parent):
        package_root = parent / "extracted-package"
        package_root.mkdir()
        with zipfile.ZipFile(io.BytesIO(bundle_data)) as archive:
            archive.extractall(package_root)
        return package_root

    @staticmethod
    def _file_snapshot(root):
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    @staticmethod
    def _rewrite_bundle(
        bundle_data,
        *,
        project_mutator=None,
        payload_updates=None,
    ):
        with zipfile.ZipFile(io.BytesIO(bundle_data)) as archive:
            payloads = {name: archive.read(name) for name in archive.namelist()}

        if project_mutator is not None:
            project = json.loads(payloads["project.json"])
            project_mutator(project)
            payloads["project.json"] = json.dumps(
                project,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        for path, payload in (payload_updates or {}).items():
            payloads[path] = payload

        manifest = json.loads(payloads[MANIFEST_PATH])
        for record in manifest["files"]:
            payload = payloads[record["path"]]
            record["size"] = len(payload)
            record["sha256"] = hashlib.sha256(payload).hexdigest()
        payloads[MANIFEST_PATH] = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in payloads.items():
                archive.writestr(name, payload)
        return output.getvalue()


if __name__ == "__main__":
    unittest.main()
