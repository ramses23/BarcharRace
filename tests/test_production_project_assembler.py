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

import automation.project_assembler as project_assembler_module
from automation.brief_loader import load_production_brief
from automation.logo_resolver import LocalLogoResolver
from automation.orchestrator import ProductionOrchestrator
from automation.project_assembler import (
    PROJECT_ASSEMBLY_MANIFEST_SCHEMA_VERSION,
    ProductionProjectAssembler,
    ProjectAssemblyError,
    ProjectAssemblyOptions,
    ProjectAssemblyResult,
)
from automation.registry import create_default_dataset_builder_registry
from automation.workspace import ProductionWorkspace
from config.project_file_loader import load_project_file
from studio import project_builder
from validators.dataset_validator import DatasetValidator


FIXTURES_DIR = TESTS_DIR / "automation" / "fixtures"
VALID_BRIEF_PATH = FIXTURES_DIR / "valid_production_brief.json"
TEMPLATE_FIXTURE_PATH = FIXTURES_DIR / "automation_project_template.json"


class ProductionProjectAssemblerTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()
        self.project_root = self.temp_path / "production-root"
        self.project_root.mkdir()
        self.template_path, self.dataset_result = self.prepare_environment(
            self.project_root
        )
        self.assembler = ProductionProjectAssembler()
        self.options = ProjectAssemblyOptions(
            project_name="assembled_project",
            title="Assembled Production",
            source_label="Source: synthetic integration data",
        )

    def test_assembles_project_without_logos(self):
        result = self.assemble()

        self.assertIsInstance(result, ProjectAssemblyResult)
        self.assertTrue(result.project_path.is_file())
        self.assertTrue(result.manifest_path.is_file())
        self.assertEqual(result.primary_logo_count, 0)
        self.assertEqual(result.secondary_logo_count, 0)

    def test_assembles_project_with_primary_logos(self):
        logo_result = self.resolve_logos(primary_categories=self.categories[:2])

        result = self.assemble(logo_result=logo_result)
        preset = load_project_file(result.project_path)

        self.assertEqual(result.primary_logo_count, 2)
        self.assertEqual(
            set(preset.dataset_config.category_logos),
            set(self.categories[:2]),
        )

    def test_assembles_project_with_secondary_logos(self):
        logo_result = self.resolve_logos(secondary_categories=self.categories[:2])

        result = self.assemble(logo_result=logo_result)
        preset = load_project_file(result.project_path)

        self.assertEqual(result.secondary_logo_count, 2)
        self.assertEqual(
            set(preset.dataset_config.category_secondary_logos),
            set(self.categories[:2]),
        )

    def test_assembles_both_logo_slots(self):
        logo_result = self.resolve_logos(
            primary_categories=self.categories[:2],
            secondary_categories=self.categories[1:3],
        )

        result = self.assemble(logo_result=logo_result)

        self.assertEqual(result.primary_logo_count, 2)
        self.assertEqual(result.secondary_logo_count, 2)

    def test_generated_project_is_accepted_by_loader(self):
        preset = load_project_file(self.assemble().project_path)

        self.assertEqual(preset.name, self.options.project_name)

    def test_replaces_dataset_path_with_portable_reference(self):
        result = self.assemble()
        project = self.read_json(result.project_path)

        expected = self.dataset_result.workspace.dataset_csv_path.relative_to(
            self.project_root
        ).as_posix()
        self.assertEqual(project["data_source"]["csv_path"], expected)
        self.assertNotIn("\\", expected)
        self.assertFalse(Path(expected).is_absolute())

    def test_replaces_dataset_columns(self):
        project = self.read_json(self.assemble().project_path)
        build = self.dataset_result.build_result

        self.assertEqual(
            project["dataset"],
            {
                "year_column": build.period_column,
                "name_column": build.category_column,
                "value_column": build.value_column,
            },
        )

    def test_configures_workspace_video_output(self):
        result = self.assemble()
        project = self.read_json(result.project_path)

        expected = result.output_path.relative_to(self.project_root).as_posix()
        self.assertEqual(project["chart"]["output_file"], expected)
        self.assertEqual(expected, self.manifest(result)["output"]["path"])

    def test_configures_workspace_frames_directory(self):
        project = self.read_json(self.assemble().project_path)

        self.assertEqual(
            project["chart"]["frames_dir"],
            (
                self.dataset_result.workspace.render_dir / "frames"
            ).relative_to(self.project_root).as_posix(),
        )

    def test_keeps_only_styles_for_current_categories(self):
        project = self.read_json(self.assemble().project_path)

        self.assertTrue(set(project.get("categories", {})) <= set(self.categories))
        self.assertNotIn("Obsolete Empire", project.get("categories", {}))

    def test_preserves_matching_category_label_and_color(self):
        project = self.read_json(self.assemble().project_path)

        self.assertEqual(
            project["categories"]["Alpha Republic"],
            {"label": "Alpha", "color": "#38BDF8"},
        )

    def test_replaces_template_logo_fields(self):
        template = self.read_json(self.template_path)
        template["categories"]["Alpha Republic"]["logo"] = "logos/old.png"
        template["categories"]["Alpha Republic"]["secondary_logo"] = (
            "logos/old-secondary.png"
        )
        self.write_json(template, self.template_path)

        project = self.read_json(self.assemble().project_path)

        self.assertNotIn("logo", project["categories"]["Alpha Republic"])
        self.assertNotIn("secondary_logo", project["categories"]["Alpha Republic"])

    def test_preserves_template_fps(self):
        preset = load_project_file(self.assemble().project_path)

        self.assertEqual(preset.chart_config.fps, 27)

    def test_preserves_template_steps_per_transition(self):
        preset = load_project_file(self.assemble().project_path)

        self.assertEqual(preset.chart_config.steps_per_transition, 19)

    def test_preserves_template_top_n(self):
        preset = load_project_file(self.assemble().project_path)

        self.assertEqual(preset.chart_config.selection.top_n, 3)

    def test_preserves_template_general_appearance(self):
        preset = load_project_file(self.assemble().project_path)
        chart = preset.chart_config

        self.assertEqual(chart.layout_preset, "square_social")
        self.assertEqual(chart.theme.name, "midnight_contrast")
        self.assertEqual(chart.typography_preset, "compact")
        self.assertEqual(chart.bar_appearance_mode, "advanced")
        self.assertTrue(chart.bar_border_enabled)
        self.assertEqual(chart.bar_border_width, 2.0)

    def test_preserves_template_animation(self):
        animation = load_project_file(self.assemble().project_path).chart_config.animation

        self.assertEqual(animation.easing, "linear")
        self.assertFalse(animation.enter_exit)
        self.assertTrue(animation.value_smoothing)
        self.assertEqual(animation.motion_mode, "continuous")

    def test_preserves_template_selection_details(self):
        selection = load_project_file(self.assemble().project_path).chart_config.selection

        self.assertFalse(selection.aggregate_other)
        self.assertEqual(selection.other_label, "Remaining")
        self.assertEqual(selection.other_color, "#64748B")

    def test_replaces_project_name_title_and_source(self):
        preset = load_project_file(self.assemble().project_path)

        self.assertEqual(preset.name, self.options.project_name)
        self.assertEqual(preset.chart_config.title, self.options.title)
        self.assertEqual(
            preset.data_source_config.source_label_override,
            self.options.source_label,
        )

    def test_does_not_create_video(self):
        result = self.assemble()

        self.assertFalse(result.output_path.exists())

    def test_status_json_is_unchanged(self):
        before = self.dataset_result.status_path.read_bytes()

        self.assemble()

        self.assertEqual(self.dataset_result.status_path.read_bytes(), before)
        self.assertEqual(json.loads(before)["state"], "dataset_ready")

    def test_template_is_unchanged(self):
        before = self.template_path.read_bytes()

        self.assemble()

        self.assertEqual(self.template_path.read_bytes(), before)

    def test_dataset_is_unchanged(self):
        before = self.dataset_result.build_result.csv_path.read_bytes()

        self.assemble()

        self.assertEqual(self.dataset_result.build_result.csv_path.read_bytes(), before)

    def test_logo_files_and_manifest_are_unchanged(self):
        logo_result = self.resolve_logos(
            primary_categories=self.categories[:1],
            secondary_categories=self.categories[:1],
        )
        before = {
            path: path.read_bytes()
            for path in (
                logo_result.manifest_path,
                logo_result.primary_assets[0].workspace_path,
                logo_result.secondary_assets[0].workspace_path,
            )
        }

        self.assemble(logo_result=logo_result)

        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_result_paths_are_absolute_and_canonical(self):
        result = self.assemble()
        workspace = self.dataset_result.workspace

        self.assertEqual(result.project_path, workspace.project_json_path)
        self.assertEqual(result.manifest_path, workspace.project_assembly_manifest_path)
        self.assertEqual(result.dataset_path, workspace.dataset_csv_path)
        self.assertEqual(result.output_path, workspace.video_path)
        self.assertTrue(all(path.is_absolute() for path in (
            result.project_path,
            result.manifest_path,
            result.template_path,
            result.dataset_path,
            result.output_path,
        )))

    def test_project_hash_is_correct(self):
        result = self.assemble()

        self.assertEqual(result.project_sha256, self.sha256(result.project_path))

    def test_project_size_is_correct(self):
        result = self.assemble()

        self.assertEqual(result.project_size_bytes, result.project_path.stat().st_size)

    def test_category_count_is_correct(self):
        result = self.assemble()

        self.assertEqual(result.category_count, len(self.categories))

    def test_warnings_are_immutable_and_propagated(self):
        logo_result = self.resolve_logos(
            primary_categories=self.categories[:1],
            missing_policy="warn",
        )

        result = self.assemble(logo_result=logo_result)

        self.assertIsInstance(result.warnings, tuple)
        self.assertEqual(result.warnings, logo_result.warnings)

    def test_options_are_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.options.title = "changed"

    def test_result_is_frozen(self):
        result = self.assemble()

        with self.assertRaises(FrozenInstanceError):
            result.category_count = 0

    def test_result_contains_no_mutable_collections(self):
        result = self.assemble()

        self.assertIsInstance(result.warnings, tuple)
        self.assertFalse(any(isinstance(value, (dict, list, set, pd.DataFrame)) for value in result.__dict__.values()))

    def test_unicode_text_is_preserved_exactly(self):
        options = ProjectAssemblyOptions(
            project_name="proyecto_méxico_日本",
            title="Energía — México 日本",
            source_label="Fuente: análisis público ñ",
        )

        preset = load_project_file(self.assemble(options=options).project_path)

        self.assertEqual(preset.name, options.project_name)
        self.assertEqual(preset.chart_config.title, options.title)
        self.assertEqual(
            preset.data_source_config.source_label_override,
            options.source_label,
        )

    def test_text_options_require_strings(self):
        for field_name in ("project_name", "title", "source_label"):
            values = {
                "project_name": "project",
                "title": "Title",
                "source_label": "Source",
            }
            values[field_name] = 123
            with self.subTest(field_name=field_name):
                with self.assertRaises(TypeError):
                    ProjectAssemblyOptions(**values)

    def test_text_options_reject_empty_and_whitespace(self):
        for field_name, invalid in (
            ("project_name", ""),
            ("title", "   "),
            ("source_label", "\t"),
        ):
            values = {
                "project_name": "project",
                "title": "Title",
                "source_label": "Source",
            }
            values[field_name] = invalid
            with self.subTest(field_name=field_name):
                with self.assertRaises(ValueError):
                    ProjectAssemblyOptions(**values)

    def test_text_options_reject_control_characters(self):
        for field_name in ("project_name", "title", "source_label"):
            for invalid in ("invalid\ntext", "invalid\u202etext"):
                values = {
                    "project_name": "project",
                    "title": "Title",
                    "source_label": "Source",
                }
                values[field_name] = invalid
                with self.subTest(field_name=field_name, invalid=invalid):
                    with self.assertRaisesRegex(ValueError, "control"):
                        ProjectAssemblyOptions(**values)

    def test_text_options_enforce_reasonable_maximums(self):
        with self.assertRaisesRegex(ValueError, "128"):
            ProjectAssemblyOptions("x" * 129, "Title", "Source")
        with self.assertRaisesRegex(ValueError, "500"):
            ProjectAssemblyOptions("project", "x" * 501, "Source")
        with self.assertRaisesRegex(ValueError, "1000"):
            ProjectAssemblyOptions("project", "Title", "x" * 1001)

    def test_text_options_do_not_strip_values(self):
        options = ProjectAssemblyOptions(" project ", " Title ", " Source ")

        preset = load_project_file(self.assemble(options=options).project_path)

        self.assertEqual(preset.name, " project ")
        self.assertEqual(preset.chart_config.title, " Title ")
        self.assertEqual(preset.data_source_config.source_label_override, " Source ")

    def test_requires_project_assembly_options(self):
        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(options={"title": "invalid"})

    def test_requires_dataset_production_result(self):
        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assembler.assemble(
                dataset_result=object(),
                template_project_path=self.template_path,
                project_root_dir=self.project_root,
                options=self.options,
            )

    def test_rejects_relative_project_root(self):
        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(project_root_dir=Path("relative-root"))

    def test_rejects_missing_project_root(self):
        missing = (self.temp_path / "missing-root").resolve()

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(project_root_dir=missing)

    def test_rejects_project_root_that_is_a_file(self):
        file_path = self.temp_path / "root-file"
        file_path.write_text("file", encoding="utf-8")

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(project_root_dir=file_path.resolve())

    def test_rejects_workspace_outside_project_root(self):
        other_root = self.temp_path / "other-root"
        other_root.mkdir()
        other_template = other_root / "template.json"
        shutil.copyfile(self.template_path, other_template)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(
                project_root_dir=other_root.resolve(),
                template_project_path=other_template.resolve(),
            )

    def test_rejects_template_outside_project_root(self):
        allowed_root = self.temp_path / "allowed-root"
        allowed_root.mkdir()
        _inside_template, inside_result = self.prepare_environment(allowed_root)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assembler.assemble(
                dataset_result=inside_result,
                template_project_path=self.template_path,
                project_root_dir=allowed_root.resolve(),
                options=self.options,
            )

    def test_rejects_relative_template_path(self):
        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(template_project_path=Path("template.json"))

    def test_rejects_missing_template(self):
        missing = (self.project_root / "missing.json").resolve()

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(template_project_path=missing)

    def test_rejects_template_directory(self):
        directory = self.project_root / "template-directory"
        directory.mkdir()

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(template_project_path=directory.resolve())

    def test_rejects_invalid_template_json(self):
        self.template_path.write_text("{invalid", encoding="utf-8")

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble()

    def test_rejects_template_with_future_schema(self):
        template = self.read_json(self.template_path)
        template["schema_version"] = 999
        self.write_json(template, self.template_path)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble()

    def test_rejects_absolute_template_asset_reference(self):
        template = self.read_json(self.template_path)
        template["chart"]["background_image_path"] = "C:/Users/example/image.png"
        self.write_json(template, self.template_path)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble()

    def test_converts_internal_absolute_template_asset_to_relative_posix(self):
        background = self.project_root / "assets" / "background.png"
        background.parent.mkdir()
        background.write_bytes(b"synthetic-background")
        template = self.read_json(self.template_path)
        template["chart"]["background_mode"] = "image"
        template["chart"]["background_image_path"] = str(background.resolve())
        self.write_json(template, self.template_path)

        project = self.read_json(self.assemble().project_path)

        self.assertEqual(
            project["chart"]["background_image_path"],
            background.relative_to(self.project_root).as_posix(),
        )

    def test_rejects_parent_template_asset_reference(self):
        template = self.read_json(self.template_path)
        template["chart"]["bar_texture_custom_image"] = "../texture.png"
        self.write_json(template, self.template_path)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble()

    def test_rejects_non_ready_status(self):
        status = self.read_json(self.dataset_result.status_path)
        status["state"] = "running"
        self.write_json(status, self.dataset_result.status_path)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble()

    def test_rejects_status_for_other_job(self):
        status = self.read_json(self.dataset_result.status_path)
        status["job_id"] = "other-job"
        self.write_json(status, self.dataset_result.status_path)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble()

    def test_rejects_missing_dataset(self):
        self.dataset_result.build_result.csv_path.unlink()

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble()

    def test_rejects_dataset_hash_mismatch(self):
        build = replace(self.dataset_result.build_result, output_sha256="0" * 64)
        result = replace(self.dataset_result, build_result=build)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(dataset_result=result)

    def test_rejects_dataset_size_mismatch(self):
        build = replace(
            self.dataset_result.build_result,
            output_size_bytes=self.dataset_result.build_result.output_size_bytes + 1,
        )
        result = replace(self.dataset_result, build_result=build)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(dataset_result=result)

    def test_rejects_missing_dataset_manifest(self):
        self.dataset_result.dataset_manifest_path.unlink()

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble()

    def test_rejects_tampered_dataset_manifest(self):
        manifest = self.read_json(self.dataset_result.dataset_manifest_path)
        manifest["dataset"]["sha256"] = "0" * 64
        self.write_json(manifest, self.dataset_result.dataset_manifest_path)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble()

    def test_rejects_mismatched_dataset_columns(self):
        build = replace(self.dataset_result.build_result, category_column="unknown")
        result = replace(self.dataset_result, build_result=build)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(dataset_result=result)

    def test_reuses_dataset_validator(self):
        with mock.patch.object(
            DatasetValidator,
            "validate",
            autospec=True,
            side_effect=ValueError("validator failed"),
        ) as validate:
            with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
                self.assemble()

        validate.assert_called_once()

    def test_rejects_logo_result_from_other_workspace(self):
        logo_result = self.resolve_logos(primary_categories=self.categories[:1])
        other_workspace = ProductionWorkspace.create(
            job_id="other-logo-job",
            root_dir=self.project_root / "other-jobs",
        )
        changed = replace(
            logo_result,
            workspace=other_workspace,
            manifest_path=other_workspace.logo_resolution_manifest_path,
        )

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(logo_result=changed)

    def test_rejects_missing_logo_manifest(self):
        logo_result = self.resolve_logos(primary_categories=self.categories[:1])
        logo_result.manifest_path.unlink()

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(logo_result=logo_result)

    def test_rejects_tampered_logo_manifest(self):
        logo_result = self.resolve_logos(primary_categories=self.categories[:1])
        manifest = self.read_json(logo_result.manifest_path)
        manifest["category_count"] += 1
        self.write_json(manifest, logo_result.manifest_path)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(logo_result=logo_result)

    def test_rejects_missing_logo_asset(self):
        logo_result = self.resolve_logos(primary_categories=self.categories[:1])
        logo_result.primary_assets[0].workspace_path.unlink()

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(logo_result=logo_result)

    def test_rejects_logo_hash_mismatch(self):
        logo_result = self.resolve_logos(primary_categories=self.categories[:1])
        asset = replace(logo_result.primary_assets[0], sha256="0" * 64)
        changed = replace(logo_result, primary_assets=(asset,))

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(logo_result=changed)

    def test_rejects_logo_size_mismatch(self):
        logo_result = self.resolve_logos(primary_categories=self.categories[:1])
        original = logo_result.primary_assets[0]
        asset = replace(original, size_bytes=original.size_bytes + 1)
        changed = replace(logo_result, primary_assets=(asset,))

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(logo_result=changed)

    def test_rejects_logo_category_outside_dataset(self):
        logo_result = self.resolve_logos(primary_categories=self.categories[:1])
        asset = replace(logo_result.primary_assets[0], category="Unknown Category")
        changed = replace(logo_result, primary_assets=(asset,))

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(logo_result=changed)

    def test_rejects_duplicate_primary_logo_category(self):
        logo_result = self.resolve_logos(primary_categories=self.categories[:1])
        asset = logo_result.primary_assets[0]
        changed = replace(logo_result, primary_assets=(asset, asset))

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(logo_result=changed)

    def test_rejects_duplicate_secondary_logo_category(self):
        logo_result = self.resolve_logos(secondary_categories=self.categories[:1])
        asset = logo_result.secondary_assets[0]
        changed = replace(logo_result, secondary_assets=(asset, asset))

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(logo_result=changed)

    def test_rejects_logo_category_column_mismatch(self):
        logo_result = self.resolve_logos(primary_categories=self.categories[:1])
        changed = replace(logo_result, category_column="other_category")

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(logo_result=changed)

    def test_rejects_logo_category_count_mismatch(self):
        logo_result = self.resolve_logos(primary_categories=self.categories[:1])
        changed = replace(logo_result, total_categories=logo_result.total_categories + 1)

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble(logo_result=changed)

    def test_rejects_preexisting_project_without_overwrite(self):
        path = self.dataset_result.workspace.project_json_path
        path.write_text("original project", encoding="utf-8")

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble()

        self.assertEqual(path.read_text(encoding="utf-8"), "original project")

    def test_rejects_preexisting_manifest_without_overwrite(self):
        path = self.dataset_result.workspace.project_assembly_manifest_path
        path.write_text("original manifest", encoding="utf-8")

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble()

        self.assertEqual(path.read_text(encoding="utf-8"), "original manifest")

    def test_rejects_preexisting_video(self):
        path = self.dataset_result.workspace.video_path
        path.write_bytes(b"existing-video")

        with self.assertRaisesRegex(ProjectAssemblyError, "validation"):
            self.assemble()

        self.assertEqual(path.read_bytes(), b"existing-video")

    def test_build_failure_creates_no_project_or_manifest(self):
        with mock.patch.object(
            project_builder,
            "build_project_data",
            side_effect=ValueError("build failed"),
        ):
            with self.assertRaisesRegex(ProjectAssemblyError, "build"):
                self.assemble()

        self.assert_no_assembly_artifacts()

    def test_save_failure_rolls_back_reserved_project(self):
        with mock.patch.object(
            project_builder,
            "save_project_data",
            side_effect=OSError("save failed"),
        ):
            with self.assertRaisesRegex(ProjectAssemblyError, "save"):
                self.assemble()

        self.assert_no_assembly_artifacts()

    def test_reload_failure_rolls_back_saved_project(self):
        real_loader = project_assembler_module.load_project_file
        calls = 0

        def fail_second_load(path):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("reload failed")
            return real_loader(path)

        with mock.patch.object(
            project_assembler_module,
            "load_project_file",
            side_effect=fail_second_load,
        ):
            with self.assertRaisesRegex(ProjectAssemblyError, "reload"):
                self.assemble()

        self.assert_no_assembly_artifacts()

    def test_manifest_failure_rolls_back_saved_project(self):
        with mock.patch.object(
            ProductionWorkspace,
            "publish_project_assembly_manifest",
            side_effect=OSError("manifest failed"),
        ):
            with self.assertRaisesRegex(ProjectAssemblyError, "manifest"):
                self.assemble()

        self.assert_no_assembly_artifacts()

    def test_failure_rollback_preserves_existing_workspace_artifacts(self):
        workspace = self.dataset_result.workspace
        preserved = {
            workspace.dataset_csv_path: workspace.dataset_csv_path.read_bytes(),
            workspace.dataset_build_manifest_path: (
                workspace.dataset_build_manifest_path.read_bytes()
            ),
            workspace.status_path: workspace.status_path.read_bytes(),
            workspace.workspace_manifest_path: workspace.workspace_manifest_path.read_bytes(),
        }

        with mock.patch.object(
            ProductionWorkspace,
            "publish_project_assembly_manifest",
            side_effect=OSError("manifest failed"),
        ):
            with self.assertRaises(ProjectAssemblyError):
                self.assemble()

        self.assertEqual({path: path.read_bytes() for path in preserved}, preserved)

    def test_rollback_failure_does_not_hide_original_cause(self):
        project_path = self.dataset_result.workspace.project_json_path
        original_unlink = Path.unlink

        def fail_project_unlink(path, *args, **kwargs):
            if path == project_path:
                raise PermissionError("rollback blocked")
            return original_unlink(path, *args, **kwargs)

        with mock.patch.object(
            project_builder,
            "save_project_data",
            side_effect=OSError("save failed"),
        ), mock.patch.object(Path, "unlink", new=fail_project_unlink):
            with self.assertRaises(ProjectAssemblyError) as caught:
                self.assemble()

        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertTrue(
            any("rollback" in note.casefold() for note in caught.exception.__cause__.__notes__)
        )
        project_path.unlink(missing_ok=True)

    def test_reuses_build_project_data(self):
        with mock.patch.object(
            project_builder,
            "build_project_data",
            wraps=project_builder.build_project_data,
        ) as build:
            self.assemble()

        build.assert_called_once()
        self.assertIn("base_project_data", build.call_args.kwargs)

    def test_reuses_save_project_data(self):
        with mock.patch.object(
            project_builder,
            "save_project_data",
            wraps=project_builder.save_project_data,
        ) as save:
            self.assemble()

        save.assert_called_once()
        self.assertEqual(
            save.call_args.args[1],
            self.dataset_result.workspace.project_json_path,
        )

    def test_reuses_load_project_file_for_template_and_output(self):
        with mock.patch.object(
            project_assembler_module,
            "load_project_file",
            wraps=project_assembler_module.load_project_file,
        ) as loader:
            self.assemble()

        self.assertEqual(loader.call_count, 2)
        self.assertEqual(loader.call_args_list[0].args[0], self.template_path)
        self.assertEqual(
            loader.call_args_list[1].args[0],
            self.dataset_result.workspace.project_json_path,
        )

    def test_reuses_apply_category_logo_matches_for_both_slots(self):
        logo_result = self.resolve_logos(
            primary_categories=self.categories[:1],
            secondary_categories=self.categories[:1],
        )
        with mock.patch.object(
            project_builder,
            "apply_category_logo_matches",
            wraps=project_builder.apply_category_logo_matches,
        ) as apply_matches:
            self.assemble(logo_result=logo_result)

        self.assertEqual(apply_matches.call_count, 2)
        self.assertEqual(apply_matches.call_args_list[0].kwargs["logo_field"], "logo")
        self.assertEqual(
            apply_matches.call_args_list[1].kwargs["logo_field"],
            "secondary_logo",
        )

    def test_never_calls_match_category_logos(self):
        with mock.patch.object(
            project_builder,
            "match_category_logos",
            side_effect=AssertionError("matching must not run"),
        ) as match:
            self.assemble()

        match.assert_not_called()

    def test_assembly_uses_no_network(self):
        with mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network access attempted"),
        ), mock.patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("network access attempted"),
        ):
            self.assemble()

    def test_assembly_uses_no_subprocesses(self):
        with mock.patch.object(
            subprocess,
            "run",
            side_effect=AssertionError("subprocess attempted"),
        ), mock.patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("subprocess attempted"),
        ):
            self.assemble()

    def test_module_has_no_forbidden_runtime_dependencies(self):
        source = inspect.getsource(project_assembler_module)

        for forbidden in (
            "streamlit",
            "renderer",
            "ffmpeg",
            "render_preflight",
            "renderjob",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source.casefold())

    def test_project_and_manifest_are_deterministic(self):
        first_root = self.temp_path / "deterministic-first"
        second_root = self.temp_path / "deterministic-second"
        first_root.mkdir()
        second_root.mkdir()
        first_template, first_dataset = self.prepare_environment(first_root)
        second_template, second_dataset = self.prepare_environment(second_root)

        first = self.assembler.assemble(
            dataset_result=first_dataset,
            template_project_path=first_template,
            project_root_dir=first_root.resolve(),
            options=self.options,
        )
        second = self.assembler.assemble(
            dataset_result=second_dataset,
            template_project_path=second_template,
            project_root_dir=second_root.resolve(),
            options=self.options,
        )

        self.assertEqual(first.project_path.read_bytes(), second.project_path.read_bytes())
        self.assertEqual(first.manifest_path.read_bytes(), second.manifest_path.read_bytes())

    def test_json_outputs_are_utf8_without_bom_and_end_in_lf(self):
        result = self.assemble()

        for path in (result.project_path, result.manifest_path):
            with self.subTest(path=path.name):
                payload = path.read_bytes()
                self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))
                self.assertTrue(payload.endswith(b"\n"))
                payload.decode("utf-8")

    def test_manifest_uses_independent_version_one(self):
        manifest = self.manifest(self.assemble())

        self.assertEqual(PROJECT_ASSEMBLY_MANIFEST_SCHEMA_VERSION, 1)
        self.assertEqual(manifest["project_assembly_manifest_schema_version"], 1)

    def test_manifest_records_project_template_and_dataset_audit_data(self):
        result = self.assemble()
        manifest = self.manifest(result)

        self.assertEqual(manifest["project"]["sha256"], result.project_sha256)
        self.assertEqual(manifest["project"]["size_bytes"], result.project_size_bytes)
        self.assertEqual(manifest["template"]["sha256"], self.sha256(self.template_path))
        self.assertEqual(
            manifest["template"]["size_bytes"],
            self.template_path.stat().st_size,
        )
        self.assertEqual(
            manifest["dataset"]["sha256"],
            self.dataset_result.build_result.output_sha256,
        )

    def test_manifest_records_logo_manifest_and_counts(self):
        logo_result = self.resolve_logos(
            primary_categories=self.categories[:2],
            secondary_categories=self.categories[:1],
        )
        manifest = self.manifest(self.assemble(logo_result=logo_result))

        self.assertEqual(manifest["logos"]["primary_count"], 2)
        self.assertEqual(manifest["logos"]["secondary_count"], 1)
        self.assertEqual(
            manifest["logos"]["manifest"],
            logo_result.manifest_path.relative_to(self.project_root).as_posix(),
        )

    def test_manifest_contains_only_portable_paths(self):
        logo_result = self.resolve_logos(primary_categories=self.categories[:1])
        manifest = self.manifest(self.assemble(logo_result=logo_result))
        paths = (
            manifest["project"]["path"],
            manifest["template"]["path"],
            manifest["dataset"]["path"],
            manifest["logos"]["manifest"],
            manifest["output"]["path"],
        )

        for path in paths:
            with self.subTest(path=path):
                self.assertIsInstance(path, str)
                self.assertNotIn("\\", path)
                self.assertNotIn(":", path)
                self.assertNotIn("..", Path(path).parts)

    def test_manifest_has_no_personal_paths_timestamps_or_machine_data(self):
        text = self.assemble().manifest_path.read_text(encoding="utf-8")

        self.assertNotIn(str(self.project_root), text)
        self.assertNotIn(str(Path.home()), text)
        self.assertNotIn("timestamp", text.casefold())
        self.assertNotIn("created_at", text.casefold())

    def test_success_leaves_no_temporary_files(self):
        self.assemble()

        self.assertEqual(tuple(self.project_root.rglob("*.tmp")), ())

    def test_manual_real_pipeline_integration(self):
        integration_root = self.temp_path / "manual-integration"
        integration_root.mkdir()
        template_path, dataset_result = self.prepare_environment(integration_root)
        dataframe = pd.read_csv(dataset_result.build_result.csv_path)
        categories = tuple(
            sorted(dataframe[dataset_result.build_result.category_column].unique())
        )
        logo_source = integration_root / "local-logos"
        self.write_logo(logo_source, f"{categories[0]}.png", b"primary")
        logo_result = LocalLogoResolver().resolve(
            dataset_csv=dataset_result.build_result.csv_path,
            category_column=dataset_result.build_result.category_column,
            workspace=dataset_result.workspace,
            primary_logo_dir=logo_source.resolve(),
            missing_policy="warn",
        )
        status_before = dataset_result.status_path.read_bytes()

        with mock.patch(
            "studio.render_preflight.run_render_preflight",
            side_effect=AssertionError("preflight must not run"),
        ) as preflight:
            result = self.assembler.assemble(
                dataset_result=dataset_result,
                template_project_path=template_path,
                project_root_dir=integration_root.resolve(),
                options=self.options,
                logo_result=logo_result,
            )

        preset = load_project_file(result.project_path)
        self.assertEqual(preset.name, self.options.project_name)
        self.assertEqual(result.primary_logo_count, 1)
        self.assertEqual(dataset_result.status_path.read_bytes(), status_before)
        self.assertEqual(json.loads(status_before)["state"], "dataset_ready")
        self.assertFalse(result.output_path.exists())
        preflight.assert_not_called()

    @property
    def categories(self):
        build = self.dataset_result.build_result
        dataframe = pd.read_csv(build.csv_path)
        return tuple(sorted(dataframe[build.category_column].unique()))

    def assemble(
        self,
        *,
        dataset_result=None,
        template_project_path=None,
        project_root_dir=None,
        options=None,
        logo_result=None,
    ):
        return self.assembler.assemble(
            dataset_result=dataset_result or self.dataset_result,
            template_project_path=template_project_path or self.template_path,
            project_root_dir=project_root_dir or self.project_root.resolve(),
            options=options if options is not None else self.options,
            logo_result=logo_result,
        )

    def prepare_environment(self, project_root):
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
        return template_path.resolve(), dataset_result

    def resolve_logos(
        self,
        *,
        primary_categories=(),
        secondary_categories=(),
        missing_policy="allow",
    ):
        primary_dir = None
        secondary_dir = None
        if primary_categories:
            primary_dir = self.project_root / "primary-source"
            for category in primary_categories:
                self.write_logo(
                    primary_dir,
                    f"{category}.png",
                    f"primary:{category}".encode("utf-8"),
                )
        if secondary_categories:
            secondary_dir = self.project_root / "secondary-source"
            for category in secondary_categories:
                self.write_logo(
                    secondary_dir,
                    f"{category}.png",
                    f"secondary:{category}".encode("utf-8"),
                )
        return LocalLogoResolver().resolve(
            dataset_csv=self.dataset_result.build_result.csv_path,
            category_column=self.dataset_result.build_result.category_column,
            workspace=self.dataset_result.workspace,
            primary_logo_dir=primary_dir.resolve() if primary_dir else None,
            secondary_logo_dir=secondary_dir.resolve() if secondary_dir else None,
            missing_policy=missing_policy,
        )

    def assert_no_assembly_artifacts(self):
        workspace = self.dataset_result.workspace
        self.assertFalse(workspace.project_json_path.exists())
        self.assertFalse(workspace.project_assembly_manifest_path.exists())
        self.assertFalse(workspace.video_path.exists())

    @staticmethod
    def manifest(result):
        return ProductionProjectAssemblerTest.read_json(result.manifest_path)

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
    def write_logo(directory, name, content):
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_bytes(content)
        return path

    @staticmethod
    def sha256(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
