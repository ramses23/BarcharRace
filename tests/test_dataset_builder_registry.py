import inspect
import socket
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import automation.registry as registry_module
from automation.brief_loader import load_production_brief, validate_builder_id
from automation.builders import NationalTeamGoalsDatasetBuilder
from automation.registry import (
    DatasetBuilderDefinition,
    DatasetBuilderRegistry,
    DatasetBuilderRegistryError,
    UnknownDatasetBuilderError,
    create_default_dataset_builder_registry,
)
from automation.workspace import ProductionWorkspace


VALID_BRIEF_PATH = (
    TESTS_DIR / "automation" / "fixtures" / "valid_production_brief.json"
)


class FakeBuilder:
    def __init__(self, builder_id="alpha", builder_version="1.0.0"):
        self.builder_id = builder_id
        self.builder_version = builder_version

    def build(self, **_kwargs):
        raise AssertionError("Registry tests must never invoke build().")


def definition(builder_id="alpha", factory=None):
    return DatasetBuilderDefinition(
        builder_id=builder_id,
        factory=factory or (lambda: FakeBuilder(builder_id=builder_id)),
    )


class DatasetBuilderRegistryTest(unittest.TestCase):
    def test_creates_registry_with_valid_definition(self):
        registry = DatasetBuilderRegistry((definition(),))

        self.assertEqual(registry.available_builder_ids, ("alpha",))

    def test_available_ids_are_a_sorted_tuple(self):
        registry = DatasetBuilderRegistry(
            (definition("zulu"), definition("alpha"), definition("middle"))
        )

        self.assertIsInstance(registry.available_builder_ids, tuple)
        self.assertEqual(
            registry.available_builder_ids,
            ("alpha", "middle", "zulu"),
        )

    def test_empty_registry_is_valid(self):
        registry = DatasetBuilderRegistry()

        self.assertEqual(registry.available_builder_ids, ())

    def test_default_registry_resolves_national_team_goals(self):
        registry = create_default_dataset_builder_registry()

        self.assertIsInstance(
            registry.create("national_team_goals"),
            NationalTeamGoalsDatasetBuilder,
        )

    def test_resolved_builder_has_registered_id(self):
        builder = create_default_dataset_builder_registry().create(
            "national_team_goals"
        )

        self.assertEqual(builder.builder_id, "national_team_goals")

    def test_resolved_builder_has_nonempty_version(self):
        builder = create_default_dataset_builder_registry().create(
            "national_team_goals"
        )

        self.assertIsInstance(builder.builder_version, str)
        self.assertTrue(builder.builder_version.strip())

    def test_each_resolution_returns_a_new_instance(self):
        registry = create_default_dataset_builder_registry()

        self.assertIsNot(
            registry.create("national_team_goals"),
            registry.create("national_team_goals"),
        )

    def test_default_registries_are_independent(self):
        first = create_default_dataset_builder_registry()
        second = create_default_dataset_builder_registry()

        self.assertIsNot(first, second)
        self.assertIsNot(first._factories, second._factories)

    def test_mutating_source_list_does_not_change_registry(self):
        definitions = [definition("alpha")]
        registry = DatasetBuilderRegistry(definitions)

        definitions.clear()
        definitions.append(definition("beta"))

        self.assertEqual(registry.available_builder_ids, ("alpha",))
        self.assertEqual(registry.create("alpha").builder_id, "alpha")

    def test_duplicate_id_is_rejected(self):
        with self.assertRaisesRegex(
            DatasetBuilderRegistryError,
            "Duplicate registered builder ID",
        ):
            DatasetBuilderRegistry((definition("alpha"), definition("alpha")))

    def test_invalid_id_is_rejected(self):
        with self.assertRaisesRegex(
            DatasetBuilderRegistryError,
            "Invalid registered builder ID",
        ):
            DatasetBuilderRegistry((definition(""),))

    def test_id_with_hyphen_is_rejected(self):
        with self.assertRaises(DatasetBuilderRegistryError):
            DatasetBuilderRegistry((definition("alpha-beta"),))

    def test_id_with_uppercase_is_rejected(self):
        with self.assertRaises(DatasetBuilderRegistryError):
            DatasetBuilderRegistry((definition("Alpha"),))

    def test_noncallable_factory_is_rejected(self):
        invalid = DatasetBuilderDefinition(builder_id="alpha", factory=None)

        with self.assertRaisesRegex(
            DatasetBuilderRegistryError,
            "must be callable",
        ):
            DatasetBuilderRegistry((invalid,))

    def test_factory_exception_during_validation_has_context(self):
        def failing_factory():
            raise RuntimeError("factory exploded")

        with self.assertRaisesRegex(
            DatasetBuilderRegistryError,
            "Factory for builder 'alpha' failed",
        ):
            DatasetBuilderRegistry((definition(factory=failing_factory),))

    def test_factory_returning_none_is_rejected(self):
        with self.assertRaisesRegex(DatasetBuilderRegistryError, "returned None"):
            DatasetBuilderRegistry((definition(factory=lambda: None),))

    def test_builder_without_id_is_rejected(self):
        class MissingId:
            builder_version = "1.0"

            def build(self):
                pass

        with self.assertRaisesRegex(DatasetBuilderRegistryError, "builder_id"):
            DatasetBuilderRegistry((definition(factory=MissingId),))

    def test_builder_without_version_is_rejected(self):
        class MissingVersion:
            builder_id = "alpha"

            def build(self):
                pass

        with self.assertRaisesRegex(DatasetBuilderRegistryError, "builder_version"):
            DatasetBuilderRegistry((definition(factory=MissingVersion),))

    def test_builder_with_empty_version_is_rejected(self):
        with self.assertRaisesRegex(
            DatasetBuilderRegistryError,
            "non-empty string builder_version",
        ):
            DatasetBuilderRegistry(
                (definition(factory=lambda: FakeBuilder(builder_version="   ")),)
            )

    def test_builder_without_build_is_rejected(self):
        class MissingBuild:
            builder_id = "alpha"
            builder_version = "1.0"

        with self.assertRaisesRegex(DatasetBuilderRegistryError, "build"):
            DatasetBuilderRegistry((definition(factory=MissingBuild),))

    def test_builder_with_noncallable_build_is_rejected(self):
        class NoncallableBuild:
            builder_id = "alpha"
            builder_version = "1.0"
            build = "not callable"

        with self.assertRaisesRegex(DatasetBuilderRegistryError, "callable build"):
            DatasetBuilderRegistry((definition(factory=NoncallableBuild),))

    def test_builder_id_must_match_registered_id(self):
        with self.assertRaisesRegex(
            DatasetBuilderRegistryError,
            "declares builder_id 'beta'",
        ):
            DatasetBuilderRegistry(
                (definition(factory=lambda: FakeBuilder(builder_id="beta")),)
            )

    def test_unknown_builder_raises_specific_error(self):
        registry = DatasetBuilderRegistry((definition("alpha"),))

        with self.assertRaises(UnknownDatasetBuilderError):
            registry.create("missing")

    def test_unknown_message_has_sorted_available_ids(self):
        registry = DatasetBuilderRegistry(
            (definition("zulu"), definition("alpha"), definition("middle"))
        )

        with self.assertRaisesRegex(
            UnknownDatasetBuilderError,
            "Available builder IDs: alpha, middle, zulu",
        ):
            registry.create("missing")

    def test_resolution_in_empty_registry_is_clear(self):
        with self.assertRaisesRegex(
            UnknownDatasetBuilderError,
            r"Available builder IDs: \(none\)",
        ):
            DatasetBuilderRegistry().create("missing")

    def test_factory_can_fail_on_later_resolution(self):
        calls = 0

        def stateful_factory():
            nonlocal calls
            calls += 1
            if calls == 1:
                return FakeBuilder()
            raise RuntimeError("later failure")

        registry = DatasetBuilderRegistry((definition(factory=stateful_factory),))

        with self.assertRaisesRegex(DatasetBuilderRegistryError, "failed"):
            registry.create("alpha")
        self.assertEqual(calls, 2)

    def test_factory_exception_preserves_original_cause(self):
        original = RuntimeError("original cause")

        def failing_factory():
            raise original

        with self.assertRaises(DatasetBuilderRegistryError) as captured:
            DatasetBuilderRegistry((definition(factory=failing_factory),))

        self.assertIs(captured.exception.__cause__, original)

    def test_brief_and_registry_share_exact_builder_id_rules(self):
        valid_ids = (
            "a",
            "0",
            "a_b9",
            "a" * 64,
            "9" + "_" * 63,
        )
        invalid_ids = (
            None,
            7,
            "",
            "_alpha",
            "Alpha",
            "alpha-beta",
            "alpha beta",
            "a" * 65,
            "á",
        )

        for builder_id in valid_ids + invalid_ids:
            with self.subTest(builder_id=builder_id):
                validator_accepts = self._validator_accepts(builder_id)
                registry_accepts = self._registry_accepts(builder_id)
                brief_accepts = self._brief_accepts(builder_id)
                self.assertEqual(registry_accepts, validator_accepts)
                self.assertEqual(brief_accepts, validator_accepts)

    def test_brief_loader_calls_shared_validator(self):
        with mock.patch(
            "automation.brief_loader.validate_builder_id",
            wraps=validate_builder_id,
        ) as validator:
            brief = load_production_brief(VALID_BRIEF_PATH, root_dir=ROOT_DIR)

        validator.assert_called_once_with("national_team_goals")
        self.assertEqual(brief.dataset.builder_id, "national_team_goals")

    def test_registry_performs_no_file_writes(self):
        failure = AssertionError("Registry attempted a file write.")
        with (
            mock.patch.object(Path, "write_text", side_effect=failure),
            mock.patch.object(Path, "write_bytes", side_effect=failure),
            mock.patch.object(Path, "mkdir", side_effect=failure),
            mock.patch.object(Path, "touch", side_effect=failure),
        ):
            registry = create_default_dataset_builder_registry()
            registry.create("national_team_goals")

    def test_registry_performs_no_network_access(self):
        failure = AssertionError("Registry attempted network access.")
        with (
            mock.patch.object(socket, "socket", side_effect=failure),
            mock.patch.object(socket, "create_connection", side_effect=failure),
        ):
            registry = create_default_dataset_builder_registry()
            registry.create("national_team_goals")

    def test_registry_performs_no_subprocesses(self):
        failure = AssertionError("Registry attempted to launch a subprocess.")
        with (
            mock.patch.object(subprocess, "Popen", side_effect=failure),
            mock.patch.object(subprocess, "run", side_effect=failure),
        ):
            registry = create_default_dataset_builder_registry()
            registry.create("national_team_goals")

    def test_registry_does_not_import_streamlit(self):
        source = inspect.getsource(registry_module).casefold()

        self.assertNotIn("streamlit", source)

    def test_registry_has_no_renderer_or_ffmpeg_dependency(self):
        source = inspect.getsource(registry_module).casefold()

        self.assertNotIn("renderer", source)
        self.assertNotIn("ffmpeg", source)

    def test_definition_order_does_not_change_observable_ids(self):
        forward = DatasetBuilderRegistry(
            (definition("alpha"), definition("beta"), definition("gamma"))
        )
        reverse = DatasetBuilderRegistry(
            (definition("gamma"), definition("beta"), definition("alpha"))
        )

        self.assertEqual(
            forward.available_builder_ids,
            reverse.available_builder_ids,
        )

    def test_registry_exposes_no_mutable_internal_dictionary(self):
        registry = DatasetBuilderRegistry((definition(),))

        with self.assertRaises(TypeError):
            registry._factories["beta"] = lambda: FakeBuilder("beta")
        with self.assertRaises(FrozenInstanceError):
            registry.available_builder_ids = ()
        self.assertIsInstance(registry._definitions, tuple)

    def test_production_brief_resolves_through_default_registry_only(self):
        write_failure = AssertionError("Integration attempted a file write.")
        with (
            mock.patch.object(Path, "write_text", side_effect=write_failure),
            mock.patch.object(Path, "write_bytes", side_effect=write_failure),
            mock.patch.object(Path, "mkdir", side_effect=write_failure),
            mock.patch.object(Path, "touch", side_effect=write_failure),
            mock.patch.object(
                ProductionWorkspace,
                "create",
                side_effect=AssertionError("Workspace creation is forbidden."),
            ),
            mock.patch.object(
                NationalTeamGoalsDatasetBuilder,
                "build",
                side_effect=AssertionError("build() is forbidden."),
            ) as build,
        ):
            brief = load_production_brief(VALID_BRIEF_PATH, root_dir=ROOT_DIR)
            registry = create_default_dataset_builder_registry()
            builder = registry.create(brief.dataset.builder_id)

        self.assertIsInstance(builder, NationalTeamGoalsDatasetBuilder)
        self.assertEqual(builder.builder_id, brief.dataset.builder_id)
        build.assert_not_called()

    @staticmethod
    def _validator_accepts(builder_id):
        try:
            validate_builder_id(builder_id)
        except ValueError:
            return False
        return True

    @staticmethod
    def _registry_accepts(builder_id):
        factory = lambda: FakeBuilder(builder_id=builder_id)
        try:
            DatasetBuilderRegistry((definition(builder_id, factory),))
        except DatasetBuilderRegistryError:
            return False
        return True

    @staticmethod
    def _brief_accepts(builder_id):
        data = {
            "production_brief_schema_version": 1,
            "job_id": "registry-rule-test",
            "dataset": {
                "builder": builder_id,
                "source_csv": (
                    "tests/automation/fixtures/national_team_goals_source.csv"
                ),
                "expected_source_sha256": None,
                "parameters": {},
            },
        }
        with mock.patch(
            "automation.brief_loader._read_strict_json",
            return_value=data,
        ):
            try:
                load_production_brief(VALID_BRIEF_PATH, root_dir=ROOT_DIR)
            except ValueError:
                return False
        return True


if __name__ == "__main__":
    unittest.main()
