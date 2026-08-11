import json
import os
import shutil
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path
from unittest import mock

import _test_path
from streamlit.testing.v1 import AppTest

import main as cli_main
from config.project_file_loader import load_project_file
from studio.package_paths import ProjectPathError, resolve_project_path
from studio.preview import render_project_preview
from studio.production_package_binding import (
    BINDING_SCHEMA_VERSION,
    ProductionPackageBindingError,
    load_production_package_binding,
    resolve_linked_project,
    write_production_package_binding,
)
from studio.project_builder import default_project_paths, save_project_data
from studio.project_bundle import build_project_bundle, import_project_bundle
from studio.project_runtime import (
    resolve_project_output_path,
    resolve_project_preset_paths,
)
from studio.render_preflight import run_render_preflight
from studio.workspace_paths import (
    AppRootWriteError,
    SETTINGS_FILE_ENV,
    WORKSPACE_DIRECTORIES,
    WORKSPACE_ROOT_ENV,
    WorkspaceLayout,
    WorkspacePathError,
    assert_user_write_path,
    default_settings_path,
    default_workspace_root,
    discover_project_locations,
    find_project_location,
    initialize_workspace,
    load_workspace_settings,
    project_location_from_path,
    save_workspace_settings,
    validate_workspace_root,
)


class WorkspaceSeparationTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="barchart-workspace-separation-"
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.base = Path(self.temporary_directory.name).resolve()
        self.app_root = self.base / "BarChartStudio"
        self.app_root.mkdir()
        self.workspace_root = self.base / "UserWorkspace"
        self.settings_path = self.base / "settings" / "settings.json"

    def test_default_workspace_is_outside_app_root(self):
        workspace = default_workspace_root(self.app_root)
        self.assertEqual(workspace, self.base / "BarChartStudioWorkspace")
        self.assertFalse(workspace.is_relative_to(self.app_root))

    def test_environment_selects_custom_workspace(self):
        custom = self.base / "custom-workspace"
        settings = load_workspace_settings(
            app_root=self.app_root,
            environ={
                WORKSPACE_ROOT_ENV: str(custom),
                SETTINGS_FILE_ENV: str(self.settings_path),
            },
        )
        self.assertEqual(settings.workspace_root, custom)
        self.assertFalse(settings.configured)

    def test_workspace_settings_persist_outside_app_root(self):
        saved = save_workspace_settings(
            self.workspace_root,
            app_root=self.app_root,
            settings_path=self.settings_path,
        )
        loaded = load_workspace_settings(
            app_root=self.app_root,
            settings_path=self.settings_path,
            environ={},
        )
        self.assertEqual(loaded.workspace_root, self.workspace_root)
        self.assertTrue(loaded.configured)
        self.assertEqual(saved.settings_path, self.settings_path)
        self.assertFalse(self.settings_path.is_relative_to(self.app_root))
        self.assertEqual(list(self.settings_path.parent.glob("*.tmp")), [])

    def test_render_cpu_preference_is_global_and_backwards_compatible(self):
        save_workspace_settings(
            self.workspace_root, app_root=self.app_root, settings_path=self.settings_path,
            render_cpu_limit_enabled=True, render_cpu_limit_percent=82,
        )
        loaded = load_workspace_settings(app_root=self.app_root, settings_path=self.settings_path, environ={})
        self.assertTrue(loaded.render_cpu_limit_enabled)
        self.assertEqual(loaded.render_cpu_limit_percent, 82)
        self.settings_path.write_text(json.dumps({"schema_version": 1, "workspace_root": str(self.workspace_root)}), encoding="utf-8")
        legacy = load_workspace_settings(app_root=self.app_root, settings_path=self.settings_path, environ={})
        self.assertTrue(legacy.render_cpu_limit_enabled)
        self.assertEqual(legacy.render_cpu_limit_percent, 95)

    def test_relative_workspace_path_is_invalid(self):
        with self.assertRaises(WorkspacePathError):
            validate_workspace_root("relative/workspace", app_root=self.app_root)

    def test_workspace_cannot_overlap_app_root(self):
        with self.assertRaises(WorkspacePathError):
            validate_workspace_root(
                self.app_root / "user-content",
                app_root=self.app_root,
            )

    def test_invalid_settings_json_is_rejected(self):
        self.settings_path.parent.mkdir()
        self.settings_path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(WorkspacePathError):
            load_workspace_settings(
                app_root=self.app_root,
                settings_path=self.settings_path,
                environ={},
            )

    def test_default_settings_path_uses_user_configuration_root(self):
        local_app_data = self.base / "local-app-data"
        path = default_settings_path(
            environ={"LOCALAPPDATA": str(local_app_data)}
        )
        self.assertEqual(
            path,
            local_app_data / "BarChartStudio" / "settings.json",
        )

    def test_workspace_initialization_creates_only_v1_directories(self):
        layout = initialize_workspace(
            self.workspace_root,
            app_root=self.app_root,
        )
        self.assertEqual(
            {path.name for path in layout.workspace_root.iterdir()},
            set(WORKSPACE_DIRECTORIES),
        )

    def test_production_root_creation_stays_in_workspace(self):
        layout = initialize_workspace(
            self.workspace_root,
            app_root=self.app_root,
        )
        production = layout.production_root("mobile_usage", create=True)
        self.assertEqual(
            production,
            self.workspace_root / "productions" / "mobile_usage",
        )
        self.assertTrue(production.is_dir())

    def test_scratch_root_creation_stays_in_workspace(self):
        layout = initialize_workspace(
            self.workspace_root,
            app_root=self.app_root,
        )
        scratch = layout.scratch_project_root("experiment", create=True)
        self.assertEqual(
            scratch,
            self.workspace_root / "scratch" / "experiment",
        )
        self.assertTrue(scratch.is_dir())

    def test_relative_dataset_resolves_inside_production(self):
        production = self._production_root()
        self._assert_resolves_in_production(production, "data/race.csv")

    def test_relative_logo_resolves_inside_production(self):
        production = self._production_root()
        self._assert_resolves_in_production(
            production,
            "assets/logos/alpha.png",
        )

    def test_relative_fun_fact_resolves_inside_production(self):
        production = self._production_root()
        self._assert_resolves_in_production(
            production,
            "fun_facts/race.json",
        )

    def test_relative_background_resolves_inside_production(self):
        production = self._production_root()
        self._assert_resolves_in_production(
            production,
            "assets/backgrounds/main.png",
        )

    def test_preview_output_is_outside_app_root(self):
        production, project_path = self._write_project()
        preview = Path(
            render_project_preview(
                "projects/race.json",
                root_dir=production,
                output_dir="output/previews",
                year=2000,
                app_root=self.app_root,
            )
        )
        self.assertTrue(preview.is_file())
        self.assertTrue(preview.is_relative_to(production / "output" / "previews"))
        self.assertFalse(preview.is_relative_to(self.app_root))
        self.assertTrue(project_path.is_file())

    def test_preview_write_into_app_root_is_rejected(self):
        production, _project_path = self._write_project()
        with self.assertRaises(AppRootWriteError):
            render_project_preview(
                "projects/race.json",
                root_dir=production,
                output_dir=self.app_root / "output" / "previews",
                year=2000,
                app_root=self.app_root,
            )

    def test_render_outputs_resolve_inside_production(self):
        production, project_path = self._write_project()
        preset = resolve_project_preset_paths(
            load_project_file(project_path),
            project_root=production,
            output_root=production,
            app_root=self.app_root,
        )
        self.assertTrue(
            Path(preset.chart_config.output_file).is_relative_to(production)
        )
        self.assertTrue(
            Path(preset.chart_config.frames_dir).is_relative_to(production)
        )

    def test_render_output_cannot_escape_output_root(self):
        production = self._production_root()
        with self.assertRaises(ProjectPathError):
            resolve_project_output_path(
                "../escape.mp4",
                output_root=production,
                field_name="chart.output_file",
            )

    def test_preflight_reports_app_root_output_as_blocking_error(self):
        production, project_path = self._write_project()
        data = json.loads(project_path.read_text(encoding="utf-8"))
        data["chart"]["output_file"] = str(self.app_root / "output" / "race.mp4")
        project_path.write_text(json.dumps(data), encoding="utf-8")
        preflight = run_render_preflight(
            "projects/race.json",
            project_root=production,
            output_root=production,
            app_root=self.app_root,
            ffmpeg_path="ffmpeg",
        )
        output_check = next(
            check for check in preflight.checks if check.key == "output"
        )
        self.assertFalse(preflight.ready)
        self.assertEqual(output_check.level, "error")
        self.assertIn("output_root", output_check.message)

    def test_new_project_is_never_written_to_repo_projects(self):
        project_data = self._project_data()
        with self.assertRaises(AppRootWriteError):
            save_project_data(
                project_data,
                self.app_root / "projects" / "new.json",
                app_root=self.app_root,
                workspace_root=self.workspace_root,
            )

        scratch = initialize_workspace(
            self.workspace_root,
            app_root=self.app_root,
        ).scratch_project_root("new", create=True)
        saved = save_project_data(
            project_data,
            scratch / "project.json",
            app_root=self.app_root,
            workspace_root=self.workspace_root,
        )
        self.assertTrue(saved.is_file())

    def test_bundle_import_installs_self_contained_production(self):
        exported = self._bundle_export()
        imported = import_project_bundle(
            exported.data,
            workspace_root=self.workspace_root,
            app_root=self.app_root,
        )
        project = Path(imported.project_path)
        production = project.parents[1]
        self.assertTrue(project.is_relative_to(self.workspace_root / "productions"))
        self.assertEqual(project.parent, production / "projects")
        self.assertEqual(Path(imported.asset_directory), production)
        self.assertFalse(project.is_relative_to(self.app_root))

    def test_bundle_keeps_project_paths_portable(self):
        imported = import_project_bundle(
            self._bundle_export().data,
            workspace_root=self.workspace_root,
            app_root=self.app_root,
        )
        project_path = Path(imported.project_path)
        production = project_path.parents[1]
        data = json.loads(project_path.read_text(encoding="utf-8"))
        csv_path = data["data_source"]["csv_path"]
        self.assertFalse(Path(csv_path).is_absolute())
        self.assertNotIn("..", Path(csv_path).parts)
        resolved = resolve_project_path(
            csv_path,
            project_root=production,
            required=True,
        )
        self.assertTrue(resolved.is_file())
        self.assertTrue(resolved.is_relative_to(production))

    def test_production_binding_uses_production_relative_project(self):
        imported = import_project_bundle(
            self._bundle_export().data,
            workspace_root=self.workspace_root,
            app_root=self.app_root,
        )
        package = self.workspace_root / "packages" / "race.zip"
        package.parent.mkdir(parents=True, exist_ok=True)
        package.write_bytes(b"package")
        binding = write_production_package_binding(
            package,
            workspace_root=self.workspace_root,
            app_root=self.app_root,
            project_path=imported.project_path,
            package_manifest_sha256="a" * 64,
        )
        state = json.loads(binding.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["schema_version"], BINDING_SCHEMA_VERSION)
        self.assertEqual(state["production_reference"], "productions/race")
        self.assertEqual(state["project_relative_path"], "projects/race.json")
        self.assertNotIn("project_path", state)

        loaded = load_production_package_binding(
            package,
            workspace_root=self.workspace_root,
            app_root=self.app_root,
            package_manifest_sha256="a" * 64,
        )
        self.assertEqual(loaded.project.absolute_path, Path(imported.project_path))

    def test_binding_traversal_is_rejected(self):
        initialize_workspace(self.workspace_root, app_root=self.app_root)
        with self.assertRaises(ProductionPackageBindingError):
            resolve_linked_project(
                "../outside.json",
                workspace_root=self.workspace_root,
                production_reference="productions/race",
                require_portable_relative=True,
            )

    def test_package_state_write_into_app_root_is_rejected(self):
        production, project_path = self._write_project()
        package = self.app_root / "package.zip"
        package.write_bytes(b"package")
        with self.assertRaises(AppRootWriteError):
            write_production_package_binding(
                package,
                workspace_root=self.workspace_root,
                app_root=self.app_root,
                project_path=project_path,
                package_manifest_sha256="b" * 64,
            )
        self.assertFalse(
            package.with_name(
                "package.zip.barchartstudio-launch.json"
            ).exists()
        )
        self.assertTrue(production.is_dir())

    def test_project_path_traversal_is_rejected(self):
        production = self._production_root()
        with self.assertRaises(ProjectPathError):
            resolve_project_path(
                "../outside.csv",
                project_root=production,
                required=True,
            )

    def test_project_path_symlink_escape_is_rejected(self):
        production = self._production_root()
        outside = self.base / "outside"
        outside.mkdir()
        link = production / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symbolic links are unavailable: {exc}")
        with self.assertRaises(ProjectPathError):
            resolve_project_path(
                "linked/file.csv",
                project_root=production,
                required=True,
            )

    def test_legacy_repository_project_remains_readable(self):
        legacy = self.app_root / "projects" / "legacy.json"
        legacy.parent.mkdir()
        legacy.write_text(json.dumps(self._project_data()), encoding="utf-8")
        layout = WorkspaceLayout(self.app_root, self.workspace_root)
        location = find_project_location("projects/legacy.json", layout)
        self.assertEqual(location.kind, "legacy")
        self.assertFalse(location.writable)
        self.assertEqual(location.absolute_path, legacy.resolve())

    def test_legacy_project_is_not_default_save_target(self):
        paths = default_project_paths("new_race")
        self.assertEqual(paths["project_file"], "project.json")
        scratch = (
            initialize_workspace(self.workspace_root, app_root=self.app_root)
            .scratch_project_root("new_race", create=True)
        )
        self.assertFalse((scratch / paths["project_file"]).is_relative_to(self.app_root))

    def test_examples_remain_readable_and_are_explicit(self):
        example = self.app_root / "examples" / "energy" / "project.json"
        example.parent.mkdir(parents=True)
        example.write_text(json.dumps(self._project_data()), encoding="utf-8")
        layout = WorkspaceLayout(self.app_root, self.workspace_root)
        locations = discover_project_locations(layout)
        location = next(item for item in locations if item.absolute_path == example.resolve())
        self.assertEqual(location.kind, "example")
        self.assertFalse(location.writable)
        self.assertTrue(location.label.startswith("Example /"))

    def test_presets_root_belongs_to_app_not_workspace(self):
        layout = WorkspaceLayout(self.app_root, self.workspace_root)
        self.assertEqual(layout.presets_root, self.app_root / "presets")
        self.assertFalse(layout.presets_root.is_relative_to(self.workspace_root))

    def test_project_location_detects_production_and_scratch_context(self):
        layout = initialize_workspace(self.workspace_root, app_root=self.app_root)
        production = layout.production_root("prod", create=True)
        production_project = production / "projects" / "race.json"
        production_project.parent.mkdir()
        production_project.write_text("{}", encoding="utf-8")
        scratch = layout.scratch_project_root("draft", create=True)
        scratch_project = scratch / "project.json"
        scratch_project.write_text("{}", encoding="utf-8")
        self.assertEqual(
            project_location_from_path(production_project, layout).kind,
            "production",
        )
        self.assertEqual(
            project_location_from_path(scratch_project, layout).kind,
            "scratch",
        )

    def test_legacy_identifier_is_not_shadowed_by_production_relative_path(self):
        layout = initialize_workspace(self.workspace_root, app_root=self.app_root)
        production = layout.production_root("prod", create=True)
        production_project = production / "projects" / "same.json"
        production_project.parent.mkdir()
        production_project.write_text("{}", encoding="utf-8")
        legacy_project = self.app_root / "projects" / "same.json"
        legacy_project.parent.mkdir()
        legacy_project.write_text("{}", encoding="utf-8")

        legacy = find_project_location("projects/same.json", layout)
        production_location = find_project_location(
            "productions/prod/projects/same.json",
            layout,
        )
        self.assertEqual(legacy.kind, "legacy")
        self.assertEqual(production_location.kind, "production")

    def test_workspace_change_is_persisted_from_project_studio(self):
        repository_root = Path(__file__).resolve().parents[1]
        studio_path = self.app_root / "src" / "ui" / "project_studio.py"
        studio_path.parent.mkdir(parents=True)
        shutil.copy2(
            repository_root / "src" / "ui" / "project_studio.py",
            studio_path,
        )
        custom_workspace = self.base / "changed-workspace"
        environment = dict(os.environ)
        environment.pop(WORKSPACE_ROOT_ENV, None)
        environment[SETTINGS_FILE_ENV] = str(self.settings_path)
        environment["BARCHARTSTUDIO_APPEARANCE_PRESETS_DIR"] = str(
            self.base / "appearance-presets"
        )
        with mock.patch.dict(os.environ, environment, clear=True), chdir(self.app_root):
            app = AppTest.from_file(str(studio_path), default_timeout=30).run()
            workspace_input = next(
                item for item in app.text_input if item.label == "Workspace path"
            )
            workspace_input.set_value(str(custom_workspace))
            next(
                button
                for button in app.button
                if button.label == "Change workspace"
            ).click()
            app.run()

        self.assertFalse(app.exception)
        saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(Path(saved["workspace_root"]), custom_workspace)
        self.assertTrue(
            any(str(custom_workspace) in item.value for item in app.code)
        )

    def test_clean_startup_without_settings_creates_nothing(self):
        settings = load_workspace_settings(
            app_root=self.app_root,
            settings_path=self.settings_path,
            environ={},
        )
        self.assertEqual(settings.workspace_root, default_workspace_root(self.app_root))
        self.assertFalse(settings.configured)
        self.assertFalse(self.settings_path.exists())
        self.assertFalse(settings.workspace_root.exists())

    def test_legacy_cli_reads_app_inputs_and_routes_output_to_scratch(self):
        data_path = self.app_root / "data" / "race.csv"
        data_path.parent.mkdir()
        data_path.write_text(
            "year,name,value\n2000,Alpha,10\n2001,Alpha,12\n",
            encoding="utf-8",
        )
        project_path = self.app_root / "projects" / "legacy.json"
        project_path.parent.mkdir()
        project_path.write_text(
            json.dumps(self._project_data()),
            encoding="utf-8",
        )
        with mock.patch.object(
            cli_main,
            "APP_ROOT",
            self.app_root,
        ), mock.patch.object(
            cli_main,
            "run_project_preset",
        ) as run_project:
            cli_main.main(
                [
                    "--project",
                    str(project_path),
                    "--workspace",
                    str(self.workspace_root),
                ]
            )

        preset = run_project.call_args.args[0]
        self.assertEqual(run_project.call_args.kwargs["project_root"], self.app_root)
        output = Path(preset.chart_config.output_file)
        self.assertTrue(
            output.is_relative_to(
                self.workspace_root / "scratch" / "legacy_legacy"
            )
        )
        self.assertFalse(output.is_relative_to(self.app_root))

    def test_cli_rejects_project_outside_explicit_production_root(self):
        production = self._production_root()
        outside_project = self.base / "outside.json"
        outside_project.write_text(
            json.dumps(self._project_data()),
            encoding="utf-8",
        )
        with mock.patch.object(cli_main, "APP_ROOT", self.app_root):
            with self.assertRaisesRegex(ValueError, "inside production_root"):
                cli_main.main(
                    [
                        "--project",
                        str(outside_project),
                        "--production-root",
                        str(production),
                    ]
                )

    def test_no_user_write_path_may_enter_app_root(self):
        for relative in (
            "data/dataset.csv",
            "projects/project.json",
            "output/previews/preview.png",
            "output/races/video.mp4",
            "assets/photos/photo.png",
            "assets/logos/logo.png",
            "packages/state.json",
        ):
            with self.subTest(relative=relative), self.assertRaises(AppRootWriteError):
                assert_user_write_path(
                    self.app_root / relative,
                    app_root=self.app_root,
                    operation="Test user content",
                )

    def test_workspace_guard_rejects_other_external_directory(self):
        initialize_workspace(self.workspace_root, app_root=self.app_root)
        with self.assertRaises(WorkspacePathError):
            assert_user_write_path(
                self.base / "different-workspace" / "file.json",
                app_root=self.app_root,
                workspace_root=self.workspace_root,
            )

    def _production_root(self):
        return initialize_workspace(
            self.workspace_root,
            app_root=self.app_root,
        ).production_root("race", create=True)

    def _assert_resolves_in_production(self, production, relative_path):
        resolved = resolve_project_path(
            relative_path,
            project_root=production,
            required=True,
        )
        self.assertEqual(resolved, production / relative_path)
        self.assertTrue(resolved.is_relative_to(production))

    def _write_project(self):
        production = self._production_root()
        data_path = production / "data" / "race.csv"
        data_path.parent.mkdir()
        data_path.write_text(
            "year,name,value\n2000,Alpha,10\n2001,Alpha,12\n",
            encoding="utf-8",
        )
        project_path = production / "projects" / "race.json"
        project_path.parent.mkdir()
        project_path.write_text(
            json.dumps(self._project_data()),
            encoding="utf-8",
        )
        return production, project_path

    def _bundle_export(self):
        source = self.base / "bundle-source"
        source.mkdir(exist_ok=True)
        data_path = source / "data" / "race.csv"
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text(
            "year,name,value\n2000,Alpha,10\n2001,Alpha,12\n",
            encoding="utf-8",
        )
        return build_project_bundle(self._project_data(), root_dir=source)

    @staticmethod
    def _project_data():
        return {
            "schema_version": 1,
            "name": "race",
            "chart": {
                "title": "Workspace race",
                "width": 320,
                "height": 180,
                "dpi": 80,
                "logos_enabled": False,
                "max_visible_bars": 1,
                "output_file": "output/races/race.mp4",
                "frames_dir": "output/frames/race",
            },
            "selection": {"top_n": 1, "aggregate_other": False},
            "data_source": {
                "source_type": "csv",
                "csv_path": "data/race.csv",
            },
            "dataset": {
                "year_column": "year",
                "name_column": "name",
                "value_column": "value",
            },
        }


if __name__ == "__main__":
    unittest.main()
