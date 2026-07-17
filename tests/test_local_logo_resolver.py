import hashlib
import inspect
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

import pandas as pd


TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import automation.logo_resolver as logo_resolver_module
from automation.brief_loader import load_production_brief
from automation.logo_resolver import (
    LOGO_RESOLUTION_MANIFEST_SCHEMA_VERSION,
    LocalLogoResolver,
    LogoAsset,
    LogoResolutionError,
    LogoResolutionResult,
)
from automation.orchestrator import ProductionOrchestrator
from automation.registry import create_default_dataset_builder_registry
from automation.workspace import ProductionWorkspace
from studio import project_builder


VALID_BRIEF_PATH = (
    TESTS_DIR / "automation" / "fixtures" / "valid_production_brief.json"
)


class LocalLogoResolverTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()
        self.workspace = ProductionWorkspace.create(
            job_id="logo-job",
            root_dir=self.temp_path / "jobs",
        )
        self.dataset_path = self.workspace.dataset_csv_path
        self.primary_dir = self.temp_path / "primary-source"
        self.secondary_dir = self.temp_path / "secondary-source"
        self.resolver = LocalLogoResolver()

    def test_resolves_exact_primary_logo(self):
        self.write_dataset(("Alpha Team",))
        logo = self.write_logo(self.primary_dir, "Alpha Team.PNG", b"exact")

        result = self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(len(result.primary_assets), 1)
        self.assertEqual(result.primary_assets[0].category, "Alpha Team")
        self.assertEqual(result.primary_assets[0].source_path, logo.resolve())

    def test_resolves_normalized_primary_logo(self):
        self.write_dataset(("United States",))
        self.write_logo(self.primary_dir, "united_states.webp")

        result = self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(tuple(result.primary_logo_map()), ("United States",))

    def test_resolves_logo_across_accents(self):
        self.write_dataset(("México",))
        self.write_logo(self.primary_dir, "Mexico.jpg")

        result = self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(result.primary_assets[0].category, "México")

    def test_resolves_logo_across_separators(self):
        self.write_dataset(("National-Team / Goals",))
        self.write_logo(self.primary_dir, "national_team_goals.jpeg")

        result = self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(len(result.primary_assets), 1)

    def test_resolves_secondary_logo(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.secondary_dir, "alpha.png", b"secondary")

        result = self.resolve(secondary_logo_dir=self.secondary_dir)

        self.assertEqual(len(result.secondary_assets), 1)
        self.assertEqual(result.secondary_assets[0].slot, "secondary")

    def test_primary_directory_none_skips_resolution(self):
        self.write_dataset(("Beta", "Alpha"))

        result = self.resolve(primary_logo_dir=None, missing_policy="allow")

        self.assertEqual(result.primary_assets, ())
        self.assertEqual(result.missing_primary, ("Alpha", "Beta"))
        self.assertFalse(self.workspace.primary_logos_dir.exists())

    def test_secondary_directory_none_skips_resolution(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")

        result = self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(result.secondary_assets, ())
        self.assertEqual(result.missing_secondary, ("Alpha",))

    def test_categories_are_sorted_deterministically(self):
        self.write_dataset(("zulu", "Alpha", "beta"))

        result = self.resolve(missing_policy="allow")

        self.assertEqual(result.missing_primary, ("Alpha", "beta", "zulu"))

    def test_duplicate_categories_are_removed(self):
        self.write_dataset(("Alpha", "Alpha", "Beta", "Alpha"))

        result = self.resolve(missing_policy="allow")

        self.assertEqual(result.total_categories, 2)
        self.assertEqual(result.missing_primary, ("Alpha", "Beta"))

    def test_null_category_is_rejected(self):
        self.write_dataset(("placeholder",))
        dataframe = pd.DataFrame({"country": [None]})

        with mock.patch.object(pd, "read_csv", return_value=dataframe):
            with self.assertRaisesRegex(LogoResolutionError, "validation"):
                self.resolve(missing_policy="allow")

        self.assertFalse(self.workspace.logo_resolution_manifest_path.exists())

    def test_empty_category_is_rejected(self):
        self.dataset_path.write_text("country\n\"\"\n", encoding="utf-8")

        with self.assertRaisesRegex(LogoResolutionError, "validation"):
            self.resolve(missing_policy="allow")

    def test_whitespace_category_is_rejected(self):
        self.dataset_path.write_text("country\n\"   \"\n", encoding="utf-8")

        with self.assertRaisesRegex(LogoResolutionError, "validation"):
            self.resolve(missing_policy="allow")

    def test_missing_csv_is_rejected(self):
        with self.assertRaisesRegex(LogoResolutionError, "validation"):
            self.resolver.resolve(
                dataset_csv=self.temp_path / "missing.csv",
                category_column="country",
                workspace=self.workspace,
                missing_policy="allow",
            )

    def test_csv_directory_is_rejected(self):
        csv_directory = self.temp_path / "dataset.csv"
        csv_directory.mkdir()

        with self.assertRaisesRegex(LogoResolutionError, "validation"):
            self.resolver.resolve(
                dataset_csv=csv_directory,
                category_column="country",
                workspace=self.workspace,
                missing_policy="allow",
            )

    def test_missing_category_column_is_rejected(self):
        self.dataset_path.write_text("name\nAlpha\n", encoding="utf-8")

        with self.assertRaisesRegex(LogoResolutionError, "validation"):
            self.resolve(missing_policy="allow")

    def test_missing_primary_directory_is_rejected(self):
        self.write_dataset(("Alpha",))

        with self.assertRaisesRegex(LogoResolutionError, "validation"):
            self.resolve(primary_logo_dir=self.temp_path / "missing")
        with self.assertRaisesRegex(LogoResolutionError, "validation"):
            self.resolve(primary_logo_dir=Path("relative-logos"))

    def test_primary_directory_file_is_rejected(self):
        self.write_dataset(("Alpha",))
        file_path = self.temp_path / "primary-file"
        file_path.write_bytes(b"file")

        with self.assertRaisesRegex(LogoResolutionError, "validation"):
            self.resolve(primary_logo_dir=file_path)

    def test_missing_secondary_directory_is_rejected(self):
        self.write_dataset(("Alpha",))

        with self.assertRaisesRegex(LogoResolutionError, "validation"):
            self.resolve(secondary_logo_dir=self.temp_path / "missing-secondary")

    def test_allow_policy_suppresses_missing_warnings(self):
        self.write_dataset(("Alpha",))

        result = self.resolve(missing_policy="allow")

        self.assertEqual(result.missing_primary, ("Alpha",))
        self.assertEqual(result.warnings, ())

    def test_warn_policy_continues(self):
        self.write_dataset(("Alpha",))

        result = self.resolve(missing_policy="warn")

        self.assertEqual(len(result.warnings), 1)
        self.assertIn("Missing primary logo", result.warnings[0])

    def test_error_policy_accepts_complete_primary_matches(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")

        result = self.resolve(
            primary_logo_dir=self.primary_dir,
            missing_policy="error",
        )

        self.assertEqual(result.missing_primary, ())

    def test_invalid_missing_policy_is_rejected(self):
        self.write_dataset(("Alpha",))

        for value in ("ignore", "", 1, None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(LogoResolutionError, "validation"):
                    self.resolve(missing_policy=value)

    def test_uppercase_missing_policy_is_rejected(self):
        self.write_dataset(("Alpha",))

        with self.assertRaisesRegex(LogoResolutionError, "validation"):
            self.resolve(missing_policy="WARN")

    def test_missing_primary_warn_is_recorded(self):
        self.write_dataset(("Beta", "Alpha"))

        result = self.resolve(missing_policy="warn")

        self.assertEqual(result.missing_primary, ("Alpha", "Beta"))
        self.assertEqual(len(result.warnings), 2)

    def test_missing_primary_error_copies_nothing(self):
        self.write_dataset(("Alpha", "Beta"))
        self.write_logo(self.primary_dir, "alpha.png")

        with self.assertRaisesRegex(LogoResolutionError, "matching"):
            self.resolve(
                primary_logo_dir=self.primary_dir,
                missing_policy="error",
            )

        self.assertFalse(self.workspace.primary_logos_dir.exists())
        self.assertFalse(self.workspace.logo_resolution_manifest_path.exists())

    def test_missing_secondary_never_blocks(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")
        self.secondary_dir.mkdir()

        result = self.resolve(
            primary_logo_dir=self.primary_dir,
            secondary_logo_dir=self.secondary_dir,
            missing_policy="error",
        )

        self.assertEqual(result.missing_secondary, ("Alpha",))

    def test_unsupported_temporary_and_nested_files_are_ignored(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.gif")
        self.write_logo(self.primary_dir, ".alpha.png")
        self.write_logo(self.primary_dir, "alpha.tmp.png")
        nested = self.primary_dir / "nested"
        self.write_logo(nested, "alpha.png")
        (self.primary_dir / "directory.png").mkdir()

        result = self.resolve(
            primary_logo_dir=self.primary_dir,
            missing_policy="allow",
        )

        self.assertEqual(result.primary_assets, ())

    def test_empty_image_file_is_ignored(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png", b"")

        result = self.resolve(
            primary_logo_dir=self.primary_dir,
            missing_policy="allow",
        )

        self.assertEqual(result.primary_assets, ())
        self.assertEqual(result.missing_primary, ("Alpha",))

    def test_result_is_frozen(self):
        self.write_dataset(("Alpha",))
        result = self.resolve(missing_policy="allow")

        with self.assertRaises(FrozenInstanceError):
            result.total_categories = 0

    def test_result_collections_are_tuples(self):
        self.write_dataset(("Alpha",))
        result = self.resolve(missing_policy="allow")

        for value in (
            result.primary_assets,
            result.secondary_assets,
            result.missing_primary,
            result.missing_secondary,
            result.ambiguous_primary,
            result.ambiguous_secondary,
            result.warnings,
        ):
            self.assertIsInstance(value, tuple)

    def test_logo_maps_are_independent_copies(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")
        result = self.resolve(primary_logo_dir=self.primary_dir)

        first = result.primary_logo_map()
        second = result.primary_logo_map()
        first["Alpha"] = "changed.png"

        self.assertIsNot(first, second)
        self.assertNotEqual(first, second)
        self.assertEqual(second, result.primary_logo_map())

    def test_destination_names_are_deterministic(self):
        first = LocalLogoResolver._destination_filename("Example Team", ".png")
        second = LocalLogoResolver._destination_filename("Example Team", ".png")

        self.assertEqual(first, second)

    def test_destination_names_are_portable(self):
        filename = LocalLogoResolver._destination_filename(
            "Team: A/B*? <Final>",
            ".PNG",
        )

        self.assertRegex(
            filename,
            r"^[a-z0-9-]+--[0-9a-f]{12}\.(png|jpg|jpeg|webp)$",
        )
        self.assertNotRegex(filename, r'[<>:"/\\|?*]')

    def test_destination_collision_is_detected(self):
        self.write_dataset(("Alpha", "Beta"))
        self.write_logo(self.primary_dir, "alpha.png")
        self.write_logo(self.primary_dir, "beta.png")

        with mock.patch.object(
            LocalLogoResolver,
            "_destination_filename",
            return_value="same.png",
        ):
            with self.assertRaisesRegex(LogoResolutionError, "matching"):
                self.resolve(primary_logo_dir=self.primary_dir)

        self.assertFalse(self.workspace.primary_logos_dir.exists())

    def test_copy_preserves_exact_bytes(self):
        content = b"synthetic-image\x00\xffbytes"
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png", content)

        asset = self.resolve(primary_logo_dir=self.primary_dir).primary_assets[0]

        self.assertEqual(asset.workspace_path.read_bytes(), content)

    def test_asset_hash_matches_copied_file(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png", b"hash-content")

        asset = self.resolve(primary_logo_dir=self.primary_dir).primary_assets[0]

        self.assertEqual(
            asset.sha256,
            hashlib.sha256(asset.workspace_path.read_bytes()).hexdigest(),
        )

    def test_asset_size_matches_copied_file(self):
        content = b"123456789"
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png", content)

        asset = self.resolve(primary_logo_dir=self.primary_dir).primary_assets[0]

        self.assertEqual(asset.size_bytes, len(content))
        self.assertEqual(asset.size_bytes, asset.workspace_path.stat().st_size)

    def test_asset_paths_are_absolute_and_resolved(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")

        asset = self.resolve(primary_logo_dir=self.primary_dir).primary_assets[0]

        for path in (asset.source_path, asset.workspace_path):
            self.assertTrue(path.is_absolute())
            self.assertEqual(path, path.resolve())

    def test_relative_paths_are_posix_workspace_paths(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")

        asset = self.resolve(primary_logo_dir=self.primary_dir).primary_assets[0]

        self.assertTrue(asset.relative_path.startswith("logos/primary/"))
        self.assertNotIn("\\", asset.relative_path)
        self.assertEqual(
            asset.workspace_path,
            self.workspace.root_path.joinpath(*asset.relative_path.split("/")),
        )

    def test_manifest_contains_no_external_paths(self):
        self.write_dataset(("Alpha",))
        source = self.write_logo(self.primary_dir, "alpha.png")

        result = self.resolve(primary_logo_dir=self.primary_dir)
        text = result.manifest_path.read_text(encoding="utf-8")

        self.assertNotIn(str(source), text)
        self.assertNotIn(str(self.primary_dir), text)
        self.assertNotIn(str(self.temp_path), text)
        self.assertNotIn(str(Path.home()), text)

    def test_manifest_uses_version_one(self):
        self.write_dataset(("Alpha",))
        result = self.resolve(missing_policy="allow")

        self.assertEqual(
            self.read_manifest(result)["logo_resolution_manifest_schema_version"],
            LOGO_RESOLUTION_MANIFEST_SCHEMA_VERSION,
        )
        self.assertEqual(LOGO_RESOLUTION_MANIFEST_SCHEMA_VERSION, 1)

    def test_manifest_is_deterministic(self):
        first_result = self.resolve_in_new_workspace(
            "first-job",
            ("Beta", "Alpha"),
            primary_names=("alpha.png", "beta.png"),
        )
        second_result = self.resolve_in_new_workspace(
            "second-job",
            ("Beta", "Alpha"),
            primary_names=("alpha.png", "beta.png"),
        )

        self.assertEqual(
            first_result.manifest_path.read_bytes(),
            second_result.manifest_path.read_bytes(),
        )

    def test_manifest_is_utf8_without_bom(self):
        self.write_dataset(("México",))
        result = self.resolve(missing_policy="allow")
        content = result.manifest_path.read_bytes()

        self.assertFalse(content.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(content.decode("utf-8"), result.manifest_path.read_text("utf-8"))

    def test_manifest_ends_with_one_lf(self):
        self.write_dataset(("Alpha",))
        content = self.resolve(missing_policy="allow").manifest_path.read_bytes()

        self.assertTrue(content.endswith(b"\n"))
        self.assertFalse(content.endswith(b"\n\n"))
        self.assertNotIn(b"\r", content)

    def test_manifest_assets_are_sorted_by_category(self):
        self.write_dataset(("zulu", "Alpha", "beta"))
        for name in ("zulu.png", "alpha.png", "beta.png"):
            self.write_logo(self.primary_dir, name)

        assets = self.read_manifest(
            self.resolve(primary_logo_dir=self.primary_dir)
        )["primary"]["assets"]

        self.assertEqual([asset["category"] for asset in assets], ["Alpha", "beta", "zulu"])

    def test_manifest_missing_categories_are_sorted(self):
        self.write_dataset(("zulu", "Alpha", "beta"))

        manifest = self.read_manifest(self.resolve(missing_policy="allow"))

        self.assertEqual(manifest["primary"]["missing"], ["Alpha", "beta", "zulu"])
        self.assertEqual(manifest["secondary"]["missing"], ["Alpha", "beta", "zulu"])

    def test_warnings_and_ambiguities_are_deterministic(self):
        self.write_dataset(("Beta", "Alpha"))
        self.write_logo(self.primary_dir, "Alpha.jpg", b"first")
        self.write_logo(self.primary_dir, "alpha.png", b"second")

        result = self.resolve(
            primary_logo_dir=self.primary_dir,
            missing_policy="warn",
        )

        self.assertEqual(result.ambiguous_primary, ("Alpha",))
        self.assertEqual(result.warnings, tuple(sorted(result.warnings, key=lambda x: (x.casefold(), x))))
        self.assertEqual(
            self.read_manifest(result)["primary"]["ambiguous"],
            ["Alpha"],
        )

    def test_preexisting_manifest_blocks_resolution(self):
        self.write_dataset(("Alpha",))
        manifest = self.workspace.logo_resolution_manifest_path
        manifest.write_bytes(b"existing manifest\n")
        self.write_logo(self.primary_dir, "alpha.png")

        with self.assertRaisesRegex(LogoResolutionError, "validation"):
            self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(manifest.read_bytes(), b"existing manifest\n")
        self.assertFalse(self.workspace.primary_logos_dir.exists())

    def test_preexisting_logo_files_block_without_overwrite(self):
        self.write_dataset(("Alpha",))
        self.workspace.primary_logos_dir.mkdir()
        existing = self.workspace.primary_logos_dir / "keep.png"
        existing.write_bytes(b"keep")
        self.write_logo(self.primary_dir, "alpha.png", b"new")

        with self.assertRaisesRegex(LogoResolutionError, "validation"):
            self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(existing.read_bytes(), b"keep")

    def test_failure_during_first_copy_rolls_back(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")

        with mock.patch.object(
            LocalLogoResolver,
            "_copy_file_exclusive",
            side_effect=OSError("first copy failed"),
        ):
            with self.assertRaisesRegex(LogoResolutionError, "copy"):
                self.resolve(primary_logo_dir=self.primary_dir)

        self.assertFalse(self.workspace.primary_logos_dir.exists())

    def test_failure_during_later_copy_rolls_back_earlier_copy(self):
        self.write_dataset(("Alpha", "Beta"))
        self.write_logo(self.primary_dir, "alpha.png")
        self.write_logo(self.primary_dir, "beta.png")
        original = LocalLogoResolver._copy_file_exclusive
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("second copy failed")
            return original(source, destination)

        with mock.patch.object(
            LocalLogoResolver,
            "_copy_file_exclusive",
            side_effect=fail_second,
        ):
            with self.assertRaises(LogoResolutionError):
                self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(calls, 2)
        self.assertFalse(self.workspace.primary_logos_dir.exists())

    def test_manifest_publication_failure_rolls_back_assets(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")

        with mock.patch.object(
            ProductionWorkspace,
            "publish_logo_resolution_manifest",
            side_effect=OSError("manifest failed"),
        ):
            with self.assertRaisesRegex(LogoResolutionError, "manifest"):
                self.resolve(primary_logo_dir=self.primary_dir)

        self.assertFalse(self.workspace.primary_logos_dir.exists())
        self.assertFalse(self.workspace.logo_resolution_manifest_path.exists())

    def test_rollback_removes_only_attempt_files(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")
        preserved = self.workspace.logos_dir / "keep.txt"
        preserved.write_bytes(b"keep")

        with mock.patch.object(
            ProductionWorkspace,
            "publish_logo_resolution_manifest",
            side_effect=OSError("manifest failed"),
        ):
            with self.assertRaises(LogoResolutionError):
                self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(preserved.read_bytes(), b"keep")
        self.assertFalse(self.workspace.primary_logos_dir.exists())

    def test_rollback_preserves_preexisting_empty_slot_directory(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")
        self.workspace.primary_logos_dir.mkdir()

        with mock.patch.object(
            ProductionWorkspace,
            "publish_logo_resolution_manifest",
            side_effect=OSError("manifest failed"),
        ):
            with self.assertRaises(LogoResolutionError):
                self.resolve(primary_logo_dir=self.primary_dir)

        self.assertTrue(self.workspace.primary_logos_dir.is_dir())
        self.assertEqual(list(self.workspace.primary_logos_dir.iterdir()), [])

    def test_rollback_failure_does_not_hide_original_error(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")
        original_error = OSError("original manifest failure")
        original_unlink = Path.unlink

        def fail_logo_unlink(path, *args, **kwargs):
            if path.parent.name == "primary" and path.suffix == ".png":
                raise PermissionError("rollback lock")
            return original_unlink(path, *args, **kwargs)

        with (
            mock.patch.object(
                ProductionWorkspace,
                "publish_logo_resolution_manifest",
                side_effect=original_error,
            ),
            mock.patch.object(Path, "unlink", new=fail_logo_unlink),
        ):
            with self.assertRaises(LogoResolutionError) as captured:
                self.resolve(primary_logo_dir=self.primary_dir)

        self.assertIs(captured.exception.__cause__, original_error)
        self.assertIn("rollback", " ".join(original_error.__notes__).casefold())
        for path in self.workspace.primary_logos_dir.iterdir():
            path.unlink()
        self.workspace.primary_logos_dir.rmdir()

    def test_success_leaves_no_temporary_files(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")

        self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(list(self.workspace.root_path.rglob("*.tmp")), [])

    def test_controlled_copy_failure_leaves_no_temporaries(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")
        original_link = os.link

        def fail_logo_link(source, destination, *args, **kwargs):
            if Path(destination).parent.name == "primary":
                raise OSError("logo hardlink failed")
            return original_link(source, destination, *args, **kwargs)

        with mock.patch.object(os, "link", side_effect=fail_logo_link):
            with self.assertRaises(LogoResolutionError):
                self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(list(self.workspace.root_path.rglob("*.tmp")), [])

    def test_dataset_is_not_modified(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")
        before = self.file_snapshot(self.dataset_path)

        self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(self.file_snapshot(self.dataset_path), before)

    def test_source_directories_are_not_modified(self):
        self.write_dataset(("Alpha",))
        primary = self.write_logo(self.primary_dir, "alpha.png", b"primary")
        secondary = self.write_logo(self.secondary_dir, "alpha.png", b"secondary")
        before = (self.file_snapshot(primary), self.file_snapshot(secondary))

        self.resolve(
            primary_logo_dir=self.primary_dir,
            secondary_logo_dir=self.secondary_dir,
        )

        self.assertEqual(
            (self.file_snapshot(primary), self.file_snapshot(secondary)),
            before,
        )

    def test_status_json_is_not_modified(self):
        self.write_dataset(("Alpha",))
        before = self.workspace.status_path.read_bytes()

        self.resolve(missing_policy="allow")

        self.assertEqual(self.workspace.status_path.read_bytes(), before)

    def test_project_json_is_not_created(self):
        self.write_dataset(("Alpha",))

        self.resolve(missing_policy="allow")

        self.assertFalse(self.workspace.project_json_path.exists())

    def test_video_is_not_created(self):
        self.write_dataset(("Alpha",))

        self.resolve(missing_policy="allow")

        self.assertFalse(self.workspace.video_path.exists())

    def test_resolution_uses_no_network(self):
        self.write_dataset(("Alpha",))
        failure = AssertionError("network attempted")

        with (
            mock.patch.object(socket, "socket", side_effect=failure),
            mock.patch.object(socket, "create_connection", side_effect=failure),
        ):
            self.resolve(missing_policy="allow")

    def test_resolution_uses_no_subprocesses(self):
        self.write_dataset(("Alpha",))
        failure = AssertionError("subprocess attempted")

        with (
            mock.patch.object(subprocess, "Popen", side_effect=failure),
            mock.patch.object(subprocess, "run", side_effect=failure),
        ):
            self.resolve(missing_policy="allow")

    def test_logo_resolver_has_no_streamlit_dependency(self):
        source = inspect.getsource(logo_resolver_module).casefold()

        self.assertNotIn("streamlit", source)

    def test_logo_resolver_has_no_renderer_or_ffmpeg_dependency(self):
        source = inspect.getsource(logo_resolver_module).casefold()

        self.assertNotIn("renderer", source)
        self.assertNotIn("ffmpeg", source)

    def test_existing_match_category_logos_is_reused(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")
        self.write_logo(self.secondary_dir, "alpha.png")

        with mock.patch.object(
            project_builder,
            "match_category_logos",
            wraps=project_builder.match_category_logos,
        ) as matcher:
            self.resolve(
                primary_logo_dir=self.primary_dir,
                secondary_logo_dir=self.secondary_dir,
            )

        self.assertEqual(matcher.call_count, 2)

    def test_apply_category_logo_matches_is_not_called(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png")

        with mock.patch.object(
            project_builder,
            "apply_category_logo_matches",
            side_effect=AssertionError("apply must not be called"),
        ) as apply_matches:
            self.resolve(primary_logo_dir=self.primary_dir)

        apply_matches.assert_not_called()

    def test_distinct_workspaces_produce_equivalent_manifests(self):
        first = self.resolve_in_new_workspace(
            "manifest-one",
            ("Alpha",),
            primary_names=("alpha.png",),
            secondary_names=("alpha.png",),
        )
        second = self.resolve_in_new_workspace(
            "manifest-two",
            ("Alpha",),
            primary_names=("alpha.png",),
            secondary_names=("alpha.png",),
        )

        self.assertEqual(first.manifest_path.read_bytes(), second.manifest_path.read_bytes())

    def test_unicode_categories_produce_safe_names(self):
        filename = LocalLogoResolver._destination_filename("日本代表 🏆", ".png")

        self.assertRegex(filename, r"^category--[0-9a-f]{12}\.png$")
        self.assertTrue(filename.isascii())

    def test_windows_reserved_names_are_avoided(self):
        for category in ("CON", "prn", "LPT1"):
            with self.subTest(category=category):
                filename = LocalLogoResolver._destination_filename(category, ".png")
                stem_prefix = filename.split("--", 1)[0].casefold()
                self.assertNotIn(stem_prefix, {"con", "prn", "lpt1"})

    def test_same_source_file_can_fill_both_slots(self):
        self.write_dataset(("Alpha",))
        source = self.write_logo(self.primary_dir, "alpha.png", b"shared")

        result = self.resolve(
            primary_logo_dir=self.primary_dir,
            secondary_logo_dir=self.primary_dir,
        )

        self.assertEqual(result.primary_assets[0].source_path, source.resolve())
        self.assertEqual(result.secondary_assets[0].source_path, source.resolve())
        self.assertEqual(
            result.primary_assets[0].workspace_path.read_bytes(),
            result.secondary_assets[0].workspace_path.read_bytes(),
        )

    def test_primary_and_secondary_use_separate_directories(self):
        self.write_dataset(("Alpha",))
        self.write_logo(self.primary_dir, "alpha.png", b"primary")
        self.write_logo(self.secondary_dir, "alpha.png", b"secondary")

        result = self.resolve(
            primary_logo_dir=self.primary_dir,
            secondary_logo_dir=self.secondary_dir,
        )

        self.assertEqual(result.primary_assets[0].workspace_path.parent.name, "primary")
        self.assertEqual(result.secondary_assets[0].workspace_path.parent.name, "secondary")

    def test_logo_asset_source_path_is_not_serialized(self):
        self.write_dataset(("Alpha",))
        source = self.write_logo(self.primary_dir, "alpha.png")

        result = self.resolve(primary_logo_dir=self.primary_dir)

        self.assertEqual(result.primary_assets[0].source_path, source.resolve())
        self.assertNotIn(
            str(source.resolve()),
            result.manifest_path.read_text(encoding="utf-8"),
        )

    def test_result_represents_zero_matches(self):
        self.write_dataset(("Alpha", "Beta"))
        self.primary_dir.mkdir()
        self.secondary_dir.mkdir()

        result = self.resolve(
            primary_logo_dir=self.primary_dir,
            secondary_logo_dir=self.secondary_dir,
            missing_policy="allow",
        )

        self.assertEqual(result.primary_assets, ())
        self.assertEqual(result.secondary_assets, ())
        self.assertEqual(result.total_categories, 2)
        self.assertEqual(result.missing_primary, ("Alpha", "Beta"))
        self.assertTrue(result.manifest_path.is_file())

    def test_manual_integration_after_real_dataset_production(self):
        brief = load_production_brief(VALID_BRIEF_PATH, root_dir=ROOT_DIR)
        dataset_result = ProductionOrchestrator(
            create_default_dataset_builder_registry()
        ).prepare_dataset(
            brief,
            workspace_root_dir=self.temp_path / "integration-jobs",
            source_root_dir=ROOT_DIR,
        )
        categories = tuple(
            sorted(
                pd.read_csv(dataset_result.build_result.csv_path)[
                    dataset_result.build_result.category_column
                ].unique()
            )
        )
        logo_dir = self.temp_path / "integration-logos"
        for category in categories[:2]:
            self.write_logo(logo_dir, f"{category}.png", category.encode("utf-8"))
        status_before = dataset_result.status_path.read_bytes()

        logo_result = self.resolver.resolve(
            dataset_csv=dataset_result.build_result.csv_path,
            category_column=dataset_result.build_result.category_column,
            workspace=dataset_result.workspace,
            primary_logo_dir=logo_dir,
            missing_policy="warn",
        )

        self.assertEqual(len(logo_result.primary_assets), 2)
        self.assertEqual(
            len(logo_result.missing_primary),
            len(categories) - 2,
        )
        self.assertTrue(all(asset.workspace_path.is_file() for asset in logo_result.primary_assets))
        self.assertTrue(logo_result.manifest_path.is_file())
        self.assertEqual(dataset_result.status_path.read_bytes(), status_before)
        self.assertEqual(
            json.loads(status_before.decode("utf-8"))["state"],
            "dataset_ready",
        )
        self.assertFalse(dataset_result.workspace.project_json_path.exists())
        self.assertFalse(dataset_result.workspace.video_path.exists())

    def resolve(
        self,
        *,
        primary_logo_dir=None,
        secondary_logo_dir=None,
        missing_policy="warn",
    ):
        return self.resolver.resolve(
            dataset_csv=self.dataset_path,
            category_column="country",
            workspace=self.workspace,
            primary_logo_dir=primary_logo_dir,
            secondary_logo_dir=secondary_logo_dir,
            missing_policy=missing_policy,
        )

    def write_dataset(self, categories, *, path=None):
        destination = path or self.dataset_path
        pd.DataFrame({"country": tuple(categories)}).to_csv(
            destination,
            index=False,
            encoding="utf-8",
            lineterminator="\n",
        )
        return destination

    @staticmethod
    def write_logo(directory, name, content=b"synthetic-image"):
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_bytes(content)
        return path

    @staticmethod
    def read_manifest(result):
        return json.loads(result.manifest_path.read_text(encoding="utf-8"))

    @staticmethod
    def file_snapshot(path):
        stat = path.stat()
        return path.read_bytes(), stat.st_size, stat.st_mtime_ns

    def resolve_in_new_workspace(
        self,
        job_id,
        categories,
        *,
        primary_names=(),
        secondary_names=(),
    ):
        workspace = ProductionWorkspace.create(
            job_id=job_id,
            root_dir=self.temp_path / "separate-jobs",
        )
        self.write_dataset(categories, path=workspace.dataset_csv_path)
        primary_dir = self.temp_path / f"{job_id}-primary"
        secondary_dir = self.temp_path / f"{job_id}-secondary"
        for name in primary_names:
            self.write_logo(primary_dir, name, b"same-primary")
        for name in secondary_names:
            self.write_logo(secondary_dir, name, b"same-secondary")
        return self.resolver.resolve(
            dataset_csv=workspace.dataset_csv_path,
            category_column="country",
            workspace=workspace,
            primary_logo_dir=primary_dir if primary_names else None,
            secondary_logo_dir=secondary_dir if secondary_names else None,
            missing_policy="allow",
        )


if __name__ == "__main__":
    unittest.main()
