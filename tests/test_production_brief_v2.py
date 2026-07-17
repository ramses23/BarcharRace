import inspect
import json
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import automation.brief_loader as brief_loader_module
from automation.brief_loader import ProductionBriefError, load_production_brief
from automation.models import (
    ProductionAssetsBrief,
    ProductionBrief,
    ProductionBriefV2,
    ProductionProjectBrief,
    ProductionRenderBrief,
)


class ProductionBriefV2Test(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()
        self.root_dir = self.temp_path / "root"
        self.root_dir.mkdir()
        self.source_path = self.root_dir / "inputs" / "source.csv"
        self.source_path.parent.mkdir()
        self.source_path.write_text("date,home_team\n", encoding="utf-8")
        self.template_path = self.root_dir / "templates" / "template.json"
        self.template_path.parent.mkdir()
        self.template_path.write_text("{}\n", encoding="utf-8")
        self.primary_logo_dir = self.root_dir / "logos" / "primary"
        self.secondary_logo_dir = self.root_dir / "logos" / "secondary"
        self.primary_logo_dir.mkdir(parents=True)
        self.secondary_logo_dir.mkdir()

    def valid_data(self):
        return {
            "production_brief_schema_version": 2,
            "job_id": "full-pipeline-job",
            "dataset": {
                "builder": "national_team_goals",
                "source_csv": "inputs/source.csv",
                "expected_source_sha256": None,
                "parameters": {
                    "start_year": 2000,
                    "end_year": 2002,
                    "mode": "cumulative",
                    "duplicate_policy": "warn",
                },
            },
            "assets": {
                "primary_logo_dir": "logos/primary",
                "secondary_logo_dir": "logos/secondary",
                "missing_policy": "warn",
            },
            "project": {
                "template": "templates/template.json",
                "name": "full-pipeline-project",
                "title": "Full Pipeline",
                "source_label": "Synthetic source",
            },
            "render": {"enabled": True},
        }

    def write_brief(self, data=None, *, raw=None):
        path = self.temp_path / "brief.json"
        if raw is None:
            raw = json.dumps(self.valid_data() if data is None else data, indent=2)
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        path.write_bytes(raw)
        return path

    def load(self, data=None, *, raw=None):
        return load_production_brief(
            self.write_brief(data, raw=raw),
            root_dir=self.root_dir,
        )

    def assert_field_error(self, data, message):
        with self.assertRaisesRegex(ProductionBriefError, message):
            self.load(data)

    def test_loads_full_version_two_contract(self):
        brief = self.load()

        self.assertIsInstance(brief, ProductionBriefV2)
        self.assertIsInstance(brief, ProductionBrief)
        self.assertEqual(brief.schema_version, 2)
        self.assertEqual(brief.assets.primary_logo_dir, self.primary_logo_dir.resolve())
        self.assertEqual(
            brief.assets.secondary_logo_dir,
            self.secondary_logo_dir.resolve(),
        )
        self.assertEqual(brief.assets.missing_policy, "warn")
        self.assertEqual(brief.project.template_path, self.template_path.resolve())
        self.assertEqual(brief.project.name, "full-pipeline-project")
        self.assertEqual(brief.project.title, "Full Pipeline")
        self.assertEqual(brief.project.source_label, "Synthetic source")
        self.assertTrue(brief.render.enabled)

    def test_version_one_returns_the_original_model_without_v2_fields(self):
        data = self.valid_data()
        data["production_brief_schema_version"] = 1
        del data["assets"]
        del data["project"]
        del data["render"]

        brief = self.load(data)

        self.assertIs(type(brief), ProductionBrief)
        self.assertEqual(tuple(brief.__dict__), ("schema_version", "job_id", "dataset"))
        self.assertFalse(hasattr(brief, "assets"))
        self.assertFalse(hasattr(brief, "project"))
        self.assertFalse(hasattr(brief, "render"))

    def test_version_one_is_not_silently_migrated(self):
        data = self.valid_data()
        data["production_brief_schema_version"] = 1

        self.assert_field_error(data, "Unknown field.*assets.*project.*render")

    def test_null_logo_directories_are_accepted(self):
        data = self.valid_data()
        data["assets"]["primary_logo_dir"] = None
        data["assets"]["secondary_logo_dir"] = None

        brief = self.load(data)

        self.assertIsNone(brief.assets.primary_logo_dir)
        self.assertIsNone(brief.assets.secondary_logo_dir)

    def test_models_are_frozen_and_nested_values_are_immutable(self):
        brief = self.load()

        self.assertIsInstance(brief.assets, ProductionAssetsBrief)
        self.assertIsInstance(brief.project, ProductionProjectBrief)
        self.assertIsInstance(brief.render, ProductionRenderBrief)
        with self.assertRaises(FrozenInstanceError):
            brief.job_id = "changed"
        with self.assertRaises(FrozenInstanceError):
            brief.assets.missing_policy = "allow"
        with self.assertRaises(FrozenInstanceError):
            brief.project.title = "Changed"
        with self.assertRaises(FrozenInstanceError):
            brief.render.enabled = False
        with self.assertRaises(TypeError):
            brief.dataset.parameters["start_year"] = 1

    def test_all_v2_sections_are_required(self):
        for section in ("assets", "project", "render"):
            data = self.valid_data()
            del data[section]
            with self.subTest(section=section):
                self.assert_field_error(data, f"Missing required field '{section}'")

    def test_v2_sections_must_be_objects(self):
        for section in ("assets", "project", "render"):
            for value in (None, [], "value", 1):
                data = self.valid_data()
                data[section] = value
                with self.subTest(section=section, value=value):
                    self.assert_field_error(data, f"'{section}'.*JSON object")

    def test_unknown_fields_are_rejected_at_every_v2_level(self):
        cases = (
            (None, "future", "Unknown field.*future"),
            ("assets", "download", "Unknown field.*download"),
            ("project", "theme", "Unknown field.*theme"),
            ("render", "quality", "Unknown field.*quality"),
        )
        for section, field, message in cases:
            data = self.valid_data()
            target = data if section is None else data[section]
            target[field] = True
            with self.subTest(section=section, field=field):
                self.assert_field_error(data, message)

    def test_all_v2_nested_fields_are_required(self):
        fields = {
            "assets": (
                "primary_logo_dir",
                "secondary_logo_dir",
                "missing_policy",
            ),
            "project": ("template", "name", "title", "source_label"),
            "render": ("enabled",),
        }
        for section, section_fields in fields.items():
            for field in section_fields:
                data = self.valid_data()
                del data[section][field]
                with self.subTest(section=section, field=field):
                    self.assert_field_error(data, f"Missing required field '{field}'")

    def test_missing_policy_accepts_only_documented_values(self):
        for policy in ("allow", "warn", "error"):
            data = self.valid_data()
            data["assets"]["missing_policy"] = policy
            with self.subTest(policy=policy):
                self.assertEqual(self.load(data).assets.missing_policy, policy)

        for policy in (None, "ignore", "WARN", 1, False):
            data = self.valid_data()
            data["assets"]["missing_policy"] = policy
            with self.subTest(policy=policy):
                self.assert_field_error(data, "assets.missing_policy")

    def test_render_enabled_requires_a_real_boolean(self):
        for value in (True, False):
            data = self.valid_data()
            data["render"]["enabled"] = value
            with self.subTest(value=value):
                self.assertIs(self.load(data).render.enabled, value)

        for value in (0, 1, None, "true", []):
            data = self.valid_data()
            data["render"]["enabled"] = value
            with self.subTest(value=value):
                self.assert_field_error(data, "render.enabled.*boolean")

    def test_project_text_fields_must_be_nonempty_strings(self):
        for field in ("name", "title", "source_label"):
            for value in (None, "", "   ", 1, False):
                data = self.valid_data()
                data["project"][field] = value
                with self.subTest(field=field, value=value):
                    self.assert_field_error(data, f"project.{field}.*non-empty")

    def test_template_must_exist_and_be_a_file(self):
        data = self.valid_data()
        data["project"]["template"] = "templates/missing.json"
        self.assert_field_error(data, "project.template.*does not exist")

        data = self.valid_data()
        data["project"]["template"] = "templates"
        self.assert_field_error(data, "project.template.*not a file")

    def test_logo_path_must_exist_and_be_a_directory(self):
        data = self.valid_data()
        data["assets"]["primary_logo_dir"] = "logos/missing"
        self.assert_field_error(data, "primary_logo_dir.*does not exist")

        logo_file = self.root_dir / "logos" / "logo.png"
        logo_file.write_bytes(b"logo")
        data = self.valid_data()
        data["assets"]["primary_logo_dir"] = "logos/logo.png"
        self.assert_field_error(data, "primary_logo_dir.*not a directory")

    def test_source_logo_and_template_paths_are_absolute_and_resolved(self):
        brief = self.load()

        for path in (
            brief.dataset.source_csv,
            brief.assets.primary_logo_dir,
            brief.assets.secondary_logo_dir,
            brief.project.template_path,
        ):
            with self.subTest(path=path):
                self.assertTrue(path.is_absolute())
                self.assertEqual(path, path.resolve(strict=True))
                self.assertTrue(path.is_relative_to(self.root_dir))

    def test_every_new_path_rejects_nonportable_forms(self):
        fields = (
            ("assets", "primary_logo_dir"),
            ("assets", "secondary_logo_dir"),
            ("project", "template"),
        )
        values = (
            ("C:/private/item", "Windows drive"),
            ("/private/item", "must be relative"),
            ("//server/share/item", "must be relative"),
            ("folder/../item", "must not contain"),
            ("folder/./item", "must not contain"),
            (r"folder\item", "must use '/' separators"),
            ("folder//item", "empty segment"),
        )
        for (section, field), (value, message) in (
            (field, value) for field in fields for value in values
        ):
            data = self.valid_data()
            data[section][field] = value
            with self.subTest(section=section, field=field, value=value):
                self.assert_field_error(data, message)

    def test_resolved_new_path_cannot_escape_root(self):
        data = self.valid_data()
        brief_path = self.write_brief(data)
        unresolved = self.root_dir / "templates" / "template.json"
        outside = self.temp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        original_resolve = Path.resolve

        def escape_template(path, strict=False):
            if path == unresolved:
                return outside.resolve()
            return original_resolve(path, strict=strict)

        with mock.patch.object(
            Path,
            "resolve",
            autospec=True,
            side_effect=escape_template,
        ):
            with self.assertRaisesRegex(ProductionBriefError, "escapes root_dir"):
                load_production_brief(brief_path, root_dir=self.root_dir)

    def test_loading_reads_no_source_logo_or_template_content(self):
        brief_path = self.write_brief()
        protected = {
            self.source_path.resolve(),
            self.template_path.resolve(),
        }
        original_read_bytes = Path.read_bytes

        def forbid_asset_read(path):
            if path.resolve() in protected:
                raise AssertionError("pipeline input content was read")
            return original_read_bytes(path)

        with mock.patch.object(
            Path,
            "read_bytes",
            autospec=True,
            side_effect=forbid_asset_read,
        ):
            brief = load_production_brief(brief_path, root_dir=self.root_dir)

        self.assertEqual(brief.project.template_path, self.template_path.resolve())

    def test_loading_executes_no_pipeline_network_or_subprocess(self):
        with mock.patch.object(
            urllib.request,
            "urlopen",
            side_effect=AssertionError("network attempted"),
        ), mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network attempted"),
        ), mock.patch.object(
            subprocess,
            "run",
            side_effect=AssertionError("subprocess attempted"),
        ), mock.patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("subprocess attempted"),
        ):
            self.load()

        source = inspect.getsource(brief_loader_module)
        for forbidden in (
            "ProductionOrchestrator",
            "LocalLogoResolver",
            "ProductionProjectAssembler",
            "ProductionPreflightRunner",
            "ProductionRenderExecutor",
            "streamlit",
        ):
            self.assertNotIn(forbidden, source)

    def test_repeated_loads_are_equivalent(self):
        brief_path = self.write_brief()

        first = load_production_brief(brief_path, root_dir=self.root_dir)
        second = load_production_brief(brief_path, root_dir=self.root_dir)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
