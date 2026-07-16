import hashlib
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

import pandas as pd


TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from automation.brief_loader import ProductionBriefError, load_production_brief
from automation.builders import NationalTeamGoalsDatasetBuilder
from automation.models import FrozenParameters
from automation.workspace import ProductionWorkspace, validate_job_id
from config.dataset_config import DatasetConfig
from validators.dataset_validator import DatasetValidator


VALID_BRIEF_PATH = (
    TESTS_DIR / "automation" / "fixtures" / "valid_production_brief.json"
)
SOURCE_FIXTURE_PATH = (
    TESTS_DIR / "automation" / "fixtures" / "national_team_goals_source.csv"
)


class ProductionBriefTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()
        self.root_dir = self.temp_path / "root"
        self.root_dir.mkdir()
        self.source_path = self.root_dir / "inputs" / "source.csv"
        self.source_path.parent.mkdir()
        self.source_path.write_text("not read by brief loader\n", encoding="utf-8")

    def valid_data(self):
        return {
            "production_brief_schema_version": 1,
            "job_id": "job7",
            "dataset": {
                "builder": "national_team_goals",
                "source_csv": "inputs/source.csv",
                "expected_source_sha256": None,
                "parameters": {
                    "start_year": 1900,
                    "end_year": 2025,
                    "mode": "cumulative",
                    "duplicate_policy": "warn",
                },
            },
        }

    def write_brief(self, data=None, *, name="brief.json", raw=None):
        path = self.temp_path / name
        if raw is None:
            raw = json.dumps(self.valid_data() if data is None else data, indent=2)
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        path.write_bytes(raw)
        return path

    def load(self, data=None, *, raw=None, root_dir=None):
        return load_production_brief(
            self.write_brief(data, raw=raw),
            root_dir=root_dir or self.root_dir,
        )

    def assert_field_error(self, data, message):
        with self.assertRaisesRegex(ProductionBriefError, message):
            self.load(data)

    def test_loads_valid_fixture(self):
        brief = load_production_brief(VALID_BRIEF_PATH, root_dir=ROOT_DIR)

        self.assertEqual(brief.schema_version, 1)
        self.assertEqual(brief.job_id, "national-team-goals-1900-2025")
        self.assertEqual(brief.dataset.builder_id, "national_team_goals")
        self.assertEqual(brief.dataset.source_csv, SOURCE_FIXTURE_PATH.resolve())
        self.assertIsNone(brief.dataset.expected_source_sha256)
        self.assertEqual(brief.dataset.parameters["start_year"], 1900)

    def test_production_brief_is_frozen(self):
        brief = self.load()
        with self.assertRaises(FrozenInstanceError):
            brief.job_id = "changed"

    def test_dataset_brief_is_frozen(self):
        brief = self.load()
        with self.assertRaises(FrozenInstanceError):
            brief.dataset.builder_id = "changed"

    def test_parameters_are_deeply_immutable(self):
        external = {"value": 1, "enabled": True}
        parameters = FrozenParameters.from_mapping(external)
        external["value"] = 9

        self.assertEqual(parameters["value"], 1)
        self.assertIsInstance(parameters._items, tuple)
        with self.assertRaises(TypeError):
            parameters["value"] = 2
        with self.assertRaises(FrozenInstanceError):
            parameters._items = ()

    def test_parameters_convert_to_independent_dict(self):
        parameters = self.load().dataset.parameters
        first = parameters.to_dict()
        second = parameters.to_dict()
        first["start_year"] = 1

        self.assertIsNot(first, second)
        self.assertEqual(second["start_year"], 1900)
        self.assertEqual(parameters["start_year"], 1900)

    def test_parameter_order_is_deterministic(self):
        data = self.valid_data()
        data["dataset"]["parameters"] = {"z": 1, "a": 2, "middle": 3}
        brief = self.load(data)

        self.assertEqual(tuple(brief.dataset.parameters), ("a", "middle", "z"))

    def test_source_csv_is_absolute_and_resolved(self):
        brief = self.load()
        self.assertTrue(brief.dataset.source_csv.is_absolute())
        self.assertEqual(brief.dataset.source_csv, self.source_path.resolve())

    def test_source_csv_content_is_not_read(self):
        brief_path = self.write_brief()
        original_read_bytes = Path.read_bytes

        def forbid_source_read(path):
            if path.resolve() == self.source_path.resolve():
                raise AssertionError("source content was read")
            return original_read_bytes(path)

        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=forbid_source_read):
            brief = load_production_brief(brief_path, root_dir=self.root_dir)

        self.assertEqual(brief.dataset.source_csv, self.source_path.resolve())

    def test_source_csv_is_not_modified(self):
        before = self.source_path.read_bytes()
        before_stat = self.source_path.stat()
        self.load()
        after_stat = self.source_path.stat()

        self.assertEqual(self.source_path.read_bytes(), before)
        self.assertEqual(after_stat.st_size, before_stat.st_size)
        self.assertEqual(after_stat.st_mtime_ns, before_stat.st_mtime_ns)

    def test_loader_does_not_create_workspace(self):
        with mock.patch.object(
            ProductionWorkspace,
            "create",
            side_effect=AssertionError("workspace creation attempted"),
        ):
            self.load()

    def test_loader_creates_no_files_or_directories(self):
        brief_path = self.write_brief()
        before = self._tree_snapshot(self.temp_path)
        load_production_brief(brief_path, root_dir=self.root_dir)
        self.assertEqual(self._tree_snapshot(self.temp_path), before)

    def test_missing_schema_version_is_rejected(self):
        data = self.valid_data()
        del data["production_brief_schema_version"]
        self.assert_field_error(data, "production_brief_schema_version")

    def test_boolean_schema_version_is_rejected(self):
        data = self.valid_data()
        data["production_brief_schema_version"] = True
        self.assert_field_error(data, "must be integer 1")

    def test_version_zero_is_rejected(self):
        data = self.valid_data()
        data["production_brief_schema_version"] = 0
        self.assert_field_error(data, "Unsupported.*0")

    def test_future_version_is_rejected(self):
        data = self.valid_data()
        data["production_brief_schema_version"] = 2
        self.assert_field_error(data, "Unsupported.*2")

    def test_unknown_top_level_field_is_rejected(self):
        data = self.valid_data()
        data["visual"] = {}
        self.assert_field_error(data, "Unknown field.*visual")

    def test_missing_job_id_is_rejected(self):
        data = self.valid_data()
        del data["job_id"]
        self.assert_field_error(data, "Missing required field 'job_id'")

    def test_invalid_job_id_is_rejected(self):
        data = self.valid_data()
        data["job_id"] = "mi trabajo"
        self.assert_field_error(data, "Invalid field 'job_id'")

    def test_brief_and_workspace_share_exact_job_id_rules(self):
        candidates = (
            "job7",
            "national-team_goals",
            "",
            "mi trabajo",
            "../otro",
            "con",
            "A",
            "a" * 65,
        )
        for candidate in candidates:
            data = self.valid_data()
            data["job_id"] = candidate
            workspace_accepts = self._accepts(lambda: validate_job_id(candidate))
            brief_accepts = self._accepts(lambda: self.load(data))
            with self.subTest(job_id=candidate):
                self.assertEqual(brief_accepts, workspace_accepts)

    def test_missing_dataset_is_rejected(self):
        data = self.valid_data()
        del data["dataset"]
        self.assert_field_error(data, "Missing required field 'dataset'")

    def test_unknown_dataset_field_is_rejected(self):
        data = self.valid_data()
        data["dataset"]["logos"] = {}
        self.assert_field_error(data, "Unknown field.*logos")

    def test_missing_builder_is_rejected(self):
        data = self.valid_data()
        del data["dataset"]["builder"]
        self.assert_field_error(data, "Missing required field 'builder'")

    def test_empty_builder_is_rejected(self):
        data = self.valid_data()
        data["dataset"]["builder"] = ""
        self.assert_field_error(data, "dataset.builder")

    def test_uppercase_builder_is_rejected(self):
        data = self.valid_data()
        data["dataset"]["builder"] = "NationalTeamGoals"
        self.assert_field_error(data, "dataset.builder")

    def test_hyphenated_builder_is_rejected(self):
        data = self.valid_data()
        data["dataset"]["builder"] = "national-team-goals"
        self.assert_field_error(data, "dataset.builder")

    def test_builder_with_spaces_is_rejected(self):
        data = self.valid_data()
        data["dataset"]["builder"] = "mi builder"
        self.assert_field_error(data, "dataset.builder")

    def test_overlong_builder_is_rejected(self):
        data = self.valid_data()
        data["dataset"]["builder"] = "a" * 65
        self.assert_field_error(data, "1-64 characters")

    def test_missing_source_csv_is_rejected(self):
        data = self.valid_data()
        del data["dataset"]["source_csv"]
        self.assert_field_error(data, "Missing required field 'source_csv'")

    def test_empty_source_csv_is_rejected(self):
        self._assert_source_rejected("", "non-empty string")

    def test_absolute_posix_source_is_rejected(self):
        self._assert_source_rejected("/tmp/source.csv", "must be relative")

    def test_windows_drive_source_is_rejected(self):
        self._assert_source_rejected("C:/source.csv", "Windows drive")

    def test_unc_source_is_rejected(self):
        self._assert_source_rejected("//server/share/source.csv", "must be relative")

    def test_parent_source_segment_is_rejected(self):
        self._assert_source_rejected("inputs/../source.csv", "must not contain")

    def test_current_source_segment_is_rejected(self):
        self._assert_source_rejected("inputs/./source.csv", "must not contain")

    def test_backslash_source_is_rejected(self):
        self._assert_source_rejected(r"inputs\source.csv", "must use '/' separators")

    def test_empty_source_segment_is_rejected(self):
        self._assert_source_rejected("inputs//source.csv", "empty segment")

    def test_source_resolving_outside_root_is_rejected(self):
        data = self.valid_data()
        brief_path = self.write_brief(data)
        unresolved_source = self.root_dir / "inputs" / "source.csv"
        outside = self.temp_path / "outside.csv"
        outside.write_text("outside", encoding="utf-8")
        original_resolve = Path.resolve

        def escape_source(path, strict=False):
            if path == unresolved_source:
                return outside.resolve()
            return original_resolve(path, strict=strict)

        with mock.patch.object(Path, "resolve", autospec=True, side_effect=escape_source):
            with self.assertRaisesRegex(ProductionBriefError, "escapes root_dir"):
                load_production_brief(brief_path, root_dir=self.root_dir)

    def test_missing_source_file_is_rejected(self):
        self._assert_source_rejected("inputs/missing.csv", "does not exist")

    def test_source_directory_is_rejected(self):
        (self.root_dir / "inputs" / "folder").mkdir()
        self._assert_source_rejected("inputs/folder", "is not a file")

    def test_null_sha256_is_accepted(self):
        self.assertIsNone(self.load().dataset.expected_source_sha256)

    def test_valid_sha256_is_preserved(self):
        digest = "a" * 64
        data = self.valid_data()
        data["dataset"]["expected_source_sha256"] = digest
        self.assertEqual(self.load(data).dataset.expected_source_sha256, digest)

    def test_short_sha256_is_rejected(self):
        self._assert_sha_rejected("a" * 63)

    def test_uppercase_sha256_is_rejected(self):
        self._assert_sha_rejected("A" * 64)

    def test_non_hex_sha256_is_rejected(self):
        self._assert_sha_rejected("g" * 64)

    def test_numeric_and_boolean_sha256_are_rejected(self):
        for value in (1, False):
            with self.subTest(value=value):
                self._assert_sha_rejected(value)

    def test_missing_parameters_is_rejected(self):
        data = self.valid_data()
        del data["dataset"]["parameters"]
        self.assert_field_error(data, "Missing required field 'parameters'")

    def test_non_object_parameters_are_rejected(self):
        for value in ([], "mode", 1, None):
            data = self.valid_data()
            data["dataset"]["parameters"] = value
            with self.subTest(value=value):
                self.assert_field_error(data, "parameters.*JSON object")

    def test_empty_parameters_object_is_accepted(self):
        data = self.valid_data()
        data["dataset"]["parameters"] = {}
        self.assertEqual(self.load(data).dataset.parameters.to_dict(), {})

    def test_non_finite_parameter_is_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            raw = self._raw_brief(
                '"builder":"national_team_goals",'
                '"source_csv":"inputs/source.csv",'
                f'"parameters":{{"value":{value}}}'
            )
            with self.subTest(value=value), self.assertRaisesRegex(
                ProductionBriefError,
                "Non-JSON numeric value",
            ):
                self.load(raw=raw)

    def test_string_parameter_is_preserved(self):
        self._assert_parameter_type("text", "value", str)

    def test_integer_parameter_is_preserved(self):
        self._assert_parameter_type("integer", 7, int)

    def test_float_parameter_is_preserved(self):
        self._assert_parameter_type("float", 1.5, float)

    def test_boolean_parameter_is_preserved_without_integer_conversion(self):
        self._assert_parameter_type("enabled", True, bool)

    def test_null_parameter_is_preserved(self):
        data = self.valid_data()
        data["dataset"]["parameters"] = {"optional": None}
        self.assertIsNone(self.load(data).dataset.parameters["optional"])

    def test_list_parameter_is_rejected(self):
        self._assert_parameter_rejected("items", [1], "JSON scalar")

    def test_nested_object_parameter_is_rejected(self):
        self._assert_parameter_rejected("nested", {"value": 1}, "JSON scalar")

    def test_empty_parameter_key_is_rejected(self):
        self._assert_parameter_rejected("", 1, "non-empty")

    def test_parameter_key_with_outer_spaces_is_rejected(self):
        self._assert_parameter_rejected(" mode ", "annual", "outer whitespace")

    def test_duplicate_top_level_key_is_rejected(self):
        raw = self._raw_brief('"job_id":"job7","job_id":"job8"')
        with self.assertRaisesRegex(ProductionBriefError, "Duplicate JSON key: 'job_id'"):
            self.load(raw=raw)

    def test_duplicate_dataset_key_is_rejected(self):
        raw = self._raw_brief(
            '"builder":"one","builder":"two",'
            '"source_csv":"inputs/source.csv","parameters":{}'
        )
        with self.assertRaisesRegex(ProductionBriefError, "Duplicate JSON key: 'builder'"):
            self.load(raw=raw)

    def test_duplicate_parameter_key_is_rejected(self):
        raw = self._raw_brief(
            '"builder":"national_team_goals",'
            '"source_csv":"inputs/source.csv",'
            '"parameters":{"mode":"annual","mode":"cumulative"}'
        )
        with self.assertRaisesRegex(ProductionBriefError, "Duplicate JSON key: 'mode'"):
            self.load(raw=raw)

    def test_invalid_json_is_rejected_with_location(self):
        brief_path = self.write_brief(raw="{")
        with self.assertRaisesRegex(ProductionBriefError, "Invalid.*line.*column") as context:
            load_production_brief(brief_path, root_dir=self.root_dir)
        self.assertIn(str(brief_path.resolve()), str(context.exception))

    def test_empty_json_file_is_rejected(self):
        with self.assertRaisesRegex(ProductionBriefError, "JSON is empty"):
            self.load(raw=b"")

    def test_missing_brief_file_is_rejected(self):
        missing = self.temp_path / "missing.json"
        with self.assertRaisesRegex(ProductionBriefError, "file not found"):
            load_production_brief(missing, root_dir=self.root_dir)

    def test_brief_directory_is_rejected(self):
        directory = self.temp_path / "brief_dir"
        directory.mkdir()
        with self.assertRaisesRegex(ProductionBriefError, "not a file"):
            load_production_brief(directory, root_dir=self.root_dir)

    def test_invalid_utf8_is_rejected(self):
        with self.assertRaisesRegex(ProductionBriefError, "valid UTF-8"):
            self.load(raw=b"\xff\xfe")

    def test_loader_has_zero_network_access(self):
        with (
            mock.patch.object(
                urllib.request,
                "urlopen",
                side_effect=AssertionError("network access attempted"),
            ),
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network access attempted"),
            ),
        ):
            self.load()

    def test_loader_executes_zero_subprocesses(self):
        with (
            mock.patch.object(
                subprocess,
                "run",
                side_effect=AssertionError("subprocess attempted"),
            ),
            mock.patch.object(
                subprocess,
                "Popen",
                side_effect=AssertionError("subprocess attempted"),
            ),
        ):
            self.load()

    def test_loader_has_no_streamlit_or_render_dependencies(self):
        import automation.brief_loader as loader_module

        source = inspect.getsource(loader_module)
        for forbidden in ("streamlit", "renderer", "ffmpeg", "RenderJob", "subprocess"):
            self.assertNotIn(forbidden, source)

    def test_repeated_loads_produce_equivalent_objects(self):
        brief_path = self.write_brief()
        first = load_production_brief(brief_path, root_dir=self.root_dir)
        second = load_production_brief(brief_path, root_dir=self.root_dir)
        self.assertEqual(first, second)

    def test_persisted_fixture_and_normal_validation_messages_have_no_personal_paths(self):
        fixture_text = VALID_BRIEF_PATH.read_text(encoding="utf-8")
        parameters = load_production_brief(
            VALID_BRIEF_PATH,
            root_dir=ROOT_DIR,
        ).dataset.parameters.to_dict()

        self.assertNotIn(str(Path.home()), fixture_text)
        self.assertNotIn(str(ROOT_DIR), fixture_text)
        self.assertNotIn(str(Path.home()), repr(parameters))

    def test_manual_integration_connects_brief_workspace_and_builder_by_values(self):
        brief = load_production_brief(VALID_BRIEF_PATH, root_dir=ROOT_DIR)
        workspace = ProductionWorkspace.create(
            job_id=brief.job_id,
            root_dir=self.temp_path / "jobs",
        )
        parameters = brief.dataset.parameters.to_dict()
        builder = NationalTeamGoalsDatasetBuilder()

        result = builder.build(
            source_csv=brief.dataset.source_csv,
            output_csv=workspace.dataset_csv_path,
            start_year=parameters["start_year"],
            end_year=parameters["end_year"],
            mode=parameters["mode"],
            expected_source_sha256=brief.dataset.expected_source_sha256,
            duplicate_policy=parameters["duplicate_policy"],
        )

        self.assertEqual(result.csv_path, workspace.dataset_csv_path)
        self.assertTrue(result.csv_path.is_relative_to(workspace.root_path))
        validated = DatasetValidator(
            DatasetConfig(
                year_column="year",
                name_column="country",
                value_column="value",
            )
        ).validate(pd.read_csv(result.csv_path))
        self.assertFalse(validated.empty)

    def _assert_source_rejected(self, value, message):
        data = self.valid_data()
        data["dataset"]["source_csv"] = value
        self.assert_field_error(data, message)

    def _assert_sha_rejected(self, value):
        data = self.valid_data()
        data["dataset"]["expected_source_sha256"] = value
        self.assert_field_error(data, "expected_source_sha256")

    def _assert_parameter_type(self, key, value, expected_type):
        data = self.valid_data()
        data["dataset"]["parameters"] = {key: value}
        actual = self.load(data).dataset.parameters[key]
        self.assertIs(type(actual), expected_type)
        self.assertEqual(actual, value)

    def _assert_parameter_rejected(self, key, value, message):
        data = self.valid_data()
        data["dataset"]["parameters"] = {key: value}
        self.assert_field_error(data, message)

    @staticmethod
    def _raw_brief(dataset_fields):
        if dataset_fields.startswith('"job_id"'):
            return (
                '{"production_brief_schema_version":1,'
                f"{dataset_fields},"
                '"dataset":{"builder":"national_team_goals",'
                '"source_csv":"inputs/source.csv","parameters":{}}}'
            )
        return (
            '{"production_brief_schema_version":1,"job_id":"job7",'
            f'"dataset":{{{dataset_fields}}}}}'
        )

    @staticmethod
    def _accepts(operation):
        try:
            operation()
        except (ValueError, ProductionBriefError):
            return False
        return True

    @staticmethod
    def _tree_snapshot(root):
        return tuple(
            sorted(
                (str(path.relative_to(root)), path.is_dir(), path.stat().st_size)
                for path in root.rglob("*")
            )
        )


if __name__ == "__main__":
    unittest.main()
