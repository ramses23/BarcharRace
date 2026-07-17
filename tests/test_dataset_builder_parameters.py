import inspect
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

import automation.builder_parameters as parameter_module
import automation.registry as registry_module
from automation.brief_loader import load_production_brief
from automation.builder_parameters import (
    DatasetBuilderParametersError,
    NationalTeamGoalsBuildParameters,
    parse_national_team_goals_parameters,
)
from automation.builders import NationalTeamGoalsDatasetBuilder
from automation.models import FrozenParameters
from automation.registry import (
    DatasetBuilderDefinition,
    DatasetBuilderRegistry,
    DatasetBuilderRegistryError,
    UnknownDatasetBuilderError,
    create_default_dataset_builder_registry,
)
from automation.workspace import ProductionWorkspace
from config.dataset_config import DatasetConfig
from validators.dataset_validator import DatasetValidator


VALID_BRIEF_PATH = (
    TESTS_DIR / "automation" / "fixtures" / "valid_production_brief.json"
)


class FakeBuilder:
    builder_id = "alpha"
    builder_version = "1.0.0"

    def build(self, **_kwargs):
        raise AssertionError("Parameter parsing must never invoke build().")


def valid_mapping(**changes):
    values = {
        "start_year": 1900,
        "end_year": 2025,
        "mode": "cumulative",
        "duplicate_policy": "warn",
    }
    values.update(changes)
    return values


def frozen_parameters(values=None, **changes):
    data = valid_mapping() if values is None else dict(values)
    data.update(changes)
    return FrozenParameters.from_mapping(data)


def definition(*, parser=None, factory=FakeBuilder, builder_id="alpha"):
    return DatasetBuilderDefinition(
        builder_id=builder_id,
        factory=factory,
        parameter_parser=parser,
    )


class DatasetBuilderParametersTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()

    def test_parses_valid_annual_mode(self):
        parsed = parse_national_team_goals_parameters(
            frozen_parameters(mode="annual", duplicate_policy="allow")
        )

        self.assertEqual(parsed.mode, "annual")
        self.assertEqual(parsed.duplicate_policy, "allow")

    def test_parses_valid_cumulative_mode(self):
        parsed = parse_national_team_goals_parameters(frozen_parameters())

        self.assertEqual(parsed.mode, "cumulative")
        self.assertEqual(parsed.duplicate_policy, "warn")

    def test_result_model_is_frozen(self):
        parsed = parse_national_team_goals_parameters(frozen_parameters())

        with self.assertRaises(FrozenInstanceError):
            parsed.start_year = 2000

    def test_to_build_kwargs_returns_a_new_copy(self):
        parsed = parse_national_team_goals_parameters(frozen_parameters())

        self.assertIsNot(parsed.to_build_kwargs(), parsed.to_build_kwargs())

    def test_mutating_build_kwargs_does_not_change_model(self):
        parsed = parse_national_team_goals_parameters(frozen_parameters())
        kwargs = parsed.to_build_kwargs()

        kwargs["start_year"] = 1
        kwargs["extra"] = "ignored"

        self.assertEqual(parsed.start_year, 1900)
        self.assertNotIn("extra", parsed.to_build_kwargs())

    def test_build_kwargs_have_exact_order_and_content(self):
        parsed = parse_national_team_goals_parameters(frozen_parameters())

        self.assertEqual(
            list(parsed.to_build_kwargs().items()),
            [
                ("start_year", 1900),
                ("end_year", 2025),
                ("mode", "cumulative"),
                ("duplicate_policy", "warn"),
            ],
        )

    def test_missing_start_year_is_rejected(self):
        self._assert_missing_key("start_year")

    def test_missing_end_year_is_rejected(self):
        self._assert_missing_key("end_year")

    def test_missing_mode_is_rejected(self):
        self._assert_missing_key("mode")

    def test_missing_duplicate_policy_is_rejected(self):
        self._assert_missing_key("duplicate_policy")

    def test_multiple_missing_keys_are_reported_deterministically(self):
        parameters = frozen_parameters(
            {"start_year": 1900, "duplicate_policy": "warn"}
        )

        with self.assertRaises(DatasetBuilderParametersError) as captured:
            parse_national_team_goals_parameters(parameters)

        self.assertIn("Missing keys: end_year, mode.", str(captured.exception))

    def test_unknown_key_is_rejected(self):
        parameters = frozen_parameters(extra="value")

        with self.assertRaisesRegex(
            DatasetBuilderParametersError,
            "Unknown keys: extra",
        ):
            parse_national_team_goals_parameters(parameters)

    def test_multiple_unknown_keys_are_reported_deterministically(self):
        parameters = frozen_parameters(zulu=1, alpha=2)

        with self.assertRaises(DatasetBuilderParametersError) as captured:
            parse_national_team_goals_parameters(parameters)

        self.assertIn("Unknown keys: alpha, zulu.", str(captured.exception))

    def test_missing_and_unknown_keys_are_reported_together(self):
        values = valid_mapping(extra=1)
        del values["mode"]

        with self.assertRaises(DatasetBuilderParametersError) as captured:
            parse_national_team_goals_parameters(frozen_parameters(values))

        message = str(captured.exception)
        self.assertIn("Missing keys: mode.", message)
        self.assertIn("Unknown keys: extra.", message)

    def test_boolean_start_year_is_rejected(self):
        self._assert_invalid_field("start_year", True, "bool")

    def test_boolean_end_year_is_rejected(self):
        self._assert_invalid_field("end_year", False, "bool")

    def test_float_start_year_is_rejected(self):
        self._assert_invalid_field("start_year", 1900.0, "float")

    def test_float_end_year_is_rejected(self):
        self._assert_invalid_field("end_year", 2025.0, "float")

    def test_numeric_string_year_is_rejected(self):
        self._assert_invalid_field("start_year", "1900", "str")

    def test_null_year_is_rejected(self):
        self._assert_invalid_field("start_year", None, "NoneType")

    def test_inverted_interval_is_rejected(self):
        with self.assertRaisesRegex(
            DatasetBuilderParametersError,
            "start_year <= end_year",
        ):
            parse_national_team_goals_parameters(
                frozen_parameters(start_year=2025, end_year=1900)
            )

    def test_equal_years_are_accepted(self):
        parsed = parse_national_team_goals_parameters(
            frozen_parameters(start_year=2000, end_year=2000)
        )

        self.assertEqual((parsed.start_year, parsed.end_year), (2000, 2000))

    def test_unknown_mode_is_rejected(self):
        self._assert_invalid_field("mode", "monthly", "annual, cumulative")

    def test_uppercase_mode_is_rejected(self):
        self._assert_invalid_field("mode", "ANNUAL", "ANNUAL")

    def test_mode_with_outer_spaces_is_rejected(self):
        self._assert_invalid_field("mode", " annual ", " annual ")

    def test_nontext_mode_is_rejected(self):
        self._assert_invalid_field("mode", 1, "int")

    def test_unknown_duplicate_policy_is_rejected(self):
        self._assert_invalid_field("duplicate_policy", "keep", "keep")

    def test_uppercase_duplicate_policy_is_rejected(self):
        self._assert_invalid_field("duplicate_policy", "WARN", "WARN")

    def test_duplicate_policy_with_outer_spaces_is_rejected(self):
        self._assert_invalid_field("duplicate_policy", " warn ", " warn ")

    def test_nontext_duplicate_policy_is_rejected(self):
        self._assert_invalid_field("duplicate_policy", 1, "int")

    def test_parser_does_not_mutate_frozen_parameters(self):
        parameters = frozen_parameters()
        before = parameters._items

        parse_national_team_goals_parameters(parameters)

        self.assertEqual(parameters._items, before)

    def test_equal_parses_produce_equivalent_objects(self):
        first = parse_national_team_goals_parameters(frozen_parameters())
        second = parse_national_team_goals_parameters(frozen_parameters())

        self.assertEqual(first, second)

    def test_independent_parses_share_no_mutable_state(self):
        first = parse_national_team_goals_parameters(frozen_parameters())
        second = parse_national_team_goals_parameters(frozen_parameters())

        self.assertIsNot(first, second)
        self.assertIsNot(first.to_build_kwargs(), second.to_build_kwargs())

    def test_registry_accepts_valid_parameter_parser(self):
        parser = mock.Mock(return_value="typed")
        registry = DatasetBuilderRegistry((definition(parser=parser),))

        result = registry.parse_parameters("alpha", frozen_parameters())

        self.assertEqual(result, "typed")

    def test_definition_without_parser_still_supports_create(self):
        registry = DatasetBuilderRegistry((definition(),))

        self.assertIsInstance(registry.create("alpha"), FakeBuilder)

    def test_parse_parameters_fails_when_definition_has_no_parser(self):
        registry = DatasetBuilderRegistry((definition(),))

        with self.assertRaisesRegex(
            DatasetBuilderRegistryError,
            "has no parameter parser",
        ):
            registry.parse_parameters("alpha", frozen_parameters())

    def test_noncallable_parameter_parser_is_rejected(self):
        invalid = definition(parser="not callable")

        with self.assertRaisesRegex(
            DatasetBuilderRegistryError,
            "Parameter parser.*must be callable",
        ):
            DatasetBuilderRegistry((invalid,))

    def test_unknown_builder_is_rejected_during_parameter_parsing(self):
        registry = DatasetBuilderRegistry((definition(parser=lambda value: value),))

        with self.assertRaises(UnknownDatasetBuilderError):
            registry.parse_parameters("missing", frozen_parameters())
        with self.assertRaisesRegex(
            DatasetBuilderRegistryError,
            "Invalid requested builder ID",
        ):
            registry.parse_parameters("Missing-ID", frozen_parameters())

    def test_parameter_parser_exception_has_registry_context(self):
        def failing_parser(_parameters):
            raise ValueError("bad typed parameters")

        registry = DatasetBuilderRegistry((definition(parser=failing_parser),))

        with self.assertRaisesRegex(
            DatasetBuilderRegistryError,
            "Parameter parser for builder 'alpha' failed: bad typed parameters",
        ):
            registry.parse_parameters("alpha", frozen_parameters())

    def test_parameter_parser_exception_preserves_original_cause(self):
        original = ValueError("original parser failure")

        def failing_parser(_parameters):
            raise original

        registry = DatasetBuilderRegistry((definition(parser=failing_parser),))

        with self.assertRaises(DatasetBuilderRegistryError) as captured:
            registry.parse_parameters("alpha", frozen_parameters())

        self.assertIs(captured.exception.__cause__, original)

    def test_parameter_parser_is_invoked_exactly_once(self):
        parser = mock.Mock(return_value="typed")
        registry = DatasetBuilderRegistry((definition(parser=parser),))
        parameters = frozen_parameters()

        registry.parse_parameters("alpha", parameters)

        parser.assert_called_once_with(parameters)

    def test_parameter_parsing_does_not_instantiate_builder(self):
        factory = mock.Mock(side_effect=FakeBuilder)
        registry = DatasetBuilderRegistry(
            (definition(parser=lambda value: value, factory=factory),)
        )
        calls_after_registry_validation = factory.call_count

        registry.parse_parameters("alpha", frozen_parameters())

        self.assertEqual(factory.call_count, calls_after_registry_validation)

    def test_parameter_parsing_does_not_call_build(self):
        build = mock.Mock()

        class BuilderWithBuildSpy:
            builder_id = "alpha"
            builder_version = "1.0.0"

            def __init__(self):
                self.build = build

        registry = DatasetBuilderRegistry(
            (
                definition(
                    parser=lambda value: value,
                    factory=BuilderWithBuildSpy,
                ),
            )
        )

        registry.parse_parameters("alpha", frozen_parameters())

        build.assert_not_called()

    def test_default_registry_contains_expected_parser(self):
        registry = create_default_dataset_builder_registry()

        self.assertIs(
            registry._parameter_parsers["national_team_goals"],
            parse_national_team_goals_parameters,
        )

    def test_valid_production_brief_parses_through_default_registry(self):
        brief = load_production_brief(VALID_BRIEF_PATH, root_dir=ROOT_DIR)
        registry = create_default_dataset_builder_registry()

        parsed = registry.parse_parameters(
            brief.dataset.builder_id,
            brief.dataset.parameters,
        )

        self.assertEqual(parsed.mode, "cumulative")

    def test_default_registry_returns_specific_parameter_model(self):
        registry = create_default_dataset_builder_registry()

        parsed = registry.parse_parameters(
            "national_team_goals",
            frozen_parameters(),
        )

        self.assertIsInstance(parsed, NationalTeamGoalsBuildParameters)

    def test_parsed_arguments_match_valid_brief(self):
        brief = load_production_brief(VALID_BRIEF_PATH, root_dir=ROOT_DIR)
        parsed = create_default_dataset_builder_registry().parse_parameters(
            brief.dataset.builder_id,
            brief.dataset.parameters,
        )

        self.assertEqual(
            parsed.to_build_kwargs(),
            {
                "start_year": 1900,
                "end_year": 2025,
                "mode": "cumulative",
                "duplicate_policy": "warn",
            },
        )

    def test_parameter_parsing_reads_no_csv(self):
        failure = AssertionError("Parameter parser attempted file input.")
        with (
            mock.patch.object(Path, "read_bytes", side_effect=failure),
            mock.patch.object(Path, "read_text", side_effect=failure),
            mock.patch.object(pd, "read_csv", side_effect=failure),
        ):
            create_default_dataset_builder_registry().parse_parameters(
                "national_team_goals",
                frozen_parameters(),
            )

    def test_parameter_parsing_writes_no_files(self):
        failure = AssertionError("Parameter parser attempted file output.")
        with (
            mock.patch.object(Path, "write_bytes", side_effect=failure),
            mock.patch.object(Path, "write_text", side_effect=failure),
            mock.patch.object(Path, "mkdir", side_effect=failure),
            mock.patch.object(Path, "touch", side_effect=failure),
        ):
            create_default_dataset_builder_registry().parse_parameters(
                "national_team_goals",
                frozen_parameters(),
            )

    def test_parameter_parsing_creates_no_workspace(self):
        with mock.patch.object(
            ProductionWorkspace,
            "create",
            side_effect=AssertionError("Workspace creation attempted."),
        ):
            create_default_dataset_builder_registry().parse_parameters(
                "national_team_goals",
                frozen_parameters(),
            )

    def test_parameter_parsing_uses_no_network(self):
        failure = AssertionError("Parameter parser attempted network access.")
        with (
            mock.patch.object(socket, "socket", side_effect=failure),
            mock.patch.object(socket, "create_connection", side_effect=failure),
        ):
            create_default_dataset_builder_registry().parse_parameters(
                "national_team_goals",
                frozen_parameters(),
            )

    def test_parameter_parsing_uses_no_subprocesses(self):
        failure = AssertionError("Parameter parser attempted a subprocess.")
        with (
            mock.patch.object(subprocess, "Popen", side_effect=failure),
            mock.patch.object(subprocess, "run", side_effect=failure),
        ):
            create_default_dataset_builder_registry().parse_parameters(
                "national_team_goals",
                frozen_parameters(),
            )

    def test_parameter_module_has_no_streamlit_or_pandas_dependency(self):
        source = inspect.getsource(parameter_module).casefold()

        self.assertNotIn("streamlit", source)
        self.assertNotIn("pandas", source)

    def test_parameter_and_registry_modules_have_no_renderer_or_ffmpeg_dependency(self):
        source = (
            inspect.getsource(parameter_module) + inspect.getsource(registry_module)
        ).casefold()

        self.assertNotIn("renderer", source)
        self.assertNotIn("ffmpeg", source)

    def test_existing_registry_create_behavior_remains_intact(self):
        registry = create_default_dataset_builder_registry()
        first = registry.create("national_team_goals")
        second = registry.create("national_team_goals")

        self.assertIsInstance(first, NationalTeamGoalsDatasetBuilder)
        self.assertIsInstance(second, NationalTeamGoalsDatasetBuilder)
        self.assertIsNot(first, second)

    def test_available_builder_ids_remain_deterministic(self):
        first = DatasetBuilderRegistry(
            (
                definition(builder_id="beta", factory=self._factory_for("beta")),
                definition(builder_id="alpha"),
            )
        )
        second = DatasetBuilderRegistry(
            (
                definition(builder_id="alpha"),
                definition(builder_id="beta", factory=self._factory_for("beta")),
            )
        )

        self.assertEqual(first.available_builder_ids, ("alpha", "beta"))
        self.assertEqual(first.available_builder_ids, second.available_builder_ids)

    def test_registry_parser_storage_is_immutable(self):
        parser = lambda value: value
        registry = DatasetBuilderRegistry((definition(parser=parser),))

        with self.assertRaises(TypeError):
            registry._parameter_parsers["alpha"] = None
        with self.assertRaises(FrozenInstanceError):
            registry._definitions[0].parameter_parser = None
        self.assertIsInstance(registry.available_builder_ids, tuple)

    def test_manual_integration_builds_and_validates_dataset(self):
        brief = load_production_brief(VALID_BRIEF_PATH, root_dir=ROOT_DIR)
        registry = create_default_dataset_builder_registry()
        typed_parameters = registry.parse_parameters(
            brief.dataset.builder_id,
            brief.dataset.parameters,
        )
        workspace = ProductionWorkspace.create(
            job_id=brief.job_id,
            root_dir=self.temp_path / "jobs",
        )
        builder = registry.create(brief.dataset.builder_id)

        result = builder.build(
            source_csv=brief.dataset.source_csv,
            output_csv=workspace.dataset_csv_path,
            expected_source_sha256=brief.dataset.expected_source_sha256,
            **typed_parameters.to_build_kwargs(),
        )

        validated = DatasetValidator(
            DatasetConfig(
                year_column="year",
                name_column="country",
                value_column="value",
            )
        ).validate(pd.read_csv(result.csv_path))
        self.assertIsInstance(
            typed_parameters,
            NationalTeamGoalsBuildParameters,
        )
        self.assertIsInstance(builder, NationalTeamGoalsDatasetBuilder)
        self.assertEqual(result.csv_path, workspace.dataset_csv_path)
        self.assertFalse(validated.empty)

    def _assert_missing_key(self, key):
        values = valid_mapping()
        del values[key]
        with self.assertRaisesRegex(
            DatasetBuilderParametersError,
            f"Missing keys: {key}",
        ):
            parse_national_team_goals_parameters(frozen_parameters(values))

    def _assert_invalid_field(self, field, value, expected_message):
        with self.assertRaises(DatasetBuilderParametersError) as captured:
            parse_national_team_goals_parameters(
                frozen_parameters(**{field: value})
            )
        message = str(captured.exception)
        self.assertIn("national_team_goals", message)
        self.assertIn(field, message)
        self.assertIn(expected_message, message)

    @staticmethod
    def _factory_for(builder_id):
        class Builder:
            builder_version = "1.0.0"

            def build(self, **_kwargs):
                pass

        Builder.builder_id = builder_id
        return Builder


if __name__ == "__main__":
    unittest.main()
