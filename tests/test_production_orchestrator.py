import hashlib
import inspect
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import date
from pathlib import Path
from unittest import mock

import pandas as pd


TESTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TESTS_DIR.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import automation.orchestrator as orchestrator_module
import automation.workspace as workspace_module
from automation.brief_loader import load_production_brief
from automation.builders import NationalTeamGoalsDatasetBuilder
from automation.models import (
    DatasetBrief,
    DatasetBuildResult,
    FrozenParameters,
    ProductionBrief,
)
from automation.orchestrator import (
    DATASET_BUILD_MANIFEST_SCHEMA_VERSION,
    DatasetProductionResult,
    ProductionOrchestrationError,
    ProductionOrchestrator,
)
from automation.registry import (
    DatasetBuilderDefinition,
    DatasetBuilderRegistry,
    create_default_dataset_builder_registry,
)
from automation.workspace import ProductionWorkspace
from config.dataset_config import DatasetConfig
from validators.dataset_validator import DatasetValidator


VALID_BRIEF_PATH = (
    TESTS_DIR / "automation" / "fixtures" / "valid_production_brief.json"
)
SOURCE_FIXTURE_PATH = (
    TESTS_DIR / "automation" / "fixtures" / "national_team_goals_source.csv"
).resolve()


@dataclass(frozen=True)
class FakeTypedParameters:
    items: tuple[tuple[str, object], ...] = (
        ("start_year", 2000),
        ("end_year", 2003),
        ("mode", "annual"),
        ("duplicate_policy", "allow"),
    )

    def to_build_kwargs(self):
        return dict(self.items)


class ParserProbe:
    def __init__(self, *, result=None, error=None):
        self.result = result or FakeTypedParameters()
        self.error = error
        self.calls = 0
        self.received = []

    def __call__(self, parameters):
        self.calls += 1
        self.received.append(parameters)
        if self.error is not None:
            raise self.error
        return self.result


class BuilderProbe:
    def __init__(
        self,
        *,
        behavior="valid",
        build_error=None,
        result_overrides=None,
        warnings=(),
        external_path=None,
        fail_factory_after_validation=False,
    ):
        self.behavior = behavior
        self.build_error = build_error
        self.result_overrides = result_overrides or {}
        self.warnings = tuple(warnings)
        self.external_path = external_path
        self.fail_factory_after_validation = fail_factory_after_validation
        self.factory_calls = 0
        self.build_calls = 0
        self.received_kwargs = []
        self.running_status = None

    def factory(self):
        self.factory_calls += 1
        if self.fail_factory_after_validation and self.factory_calls > 1:
            raise RuntimeError("factory failed during orchestration")
        return ProbeBuilder(self)


class ProbeBuilder:
    builder_id = "alpha"
    builder_version = "1.0.0"

    def __init__(self, probe):
        self.probe = probe

    def build(self, **kwargs):
        self.probe.build_calls += 1
        self.probe.received_kwargs.append(dict(kwargs))
        output_path = Path(kwargs["output_csv"])
        status_path = output_path.parents[1] / "status.json"
        if status_path.is_file():
            self.probe.running_status = json.loads(
                status_path.read_text(encoding="utf-8")
            )
        if self.probe.build_error is not None:
            raise self.probe.build_error
        if self.probe.behavior == "wrong_type":
            return "not a DatasetBuildResult"

        result_path = output_path
        if self.probe.behavior == "external":
            result_path = Path(self.probe.external_path).resolve()
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(
                "year,country,value\n2000,Alpha,1\n",
                encoding="utf-8",
                newline="\n",
            )
        elif self.probe.behavior == "no_file":
            pass
        elif self.probe.behavior == "directory":
            output_path.mkdir()
        elif self.probe.behavior == "invalid_dataset":
            output_path.write_text(
                "year,country\n2000,Alpha\n",
                encoding="utf-8",
                newline="\n",
            )
        else:
            output_path.write_text(
                "year,country,value\n2000,Alpha,1\n",
                encoding="utf-8",
                newline="\n",
            )

        if self.probe.behavior == "preexisting_manifest":
            manifest_path = output_path.parents[1] / "manifests" / "dataset_build.json"
            manifest_path.write_bytes(b"preserve existing manifest\n")

        result = fake_build_result(
            source_path=Path(kwargs["source_csv"]),
            output_path=result_path,
            kwargs=kwargs,
            warnings=self.probe.warnings,
        )
        return replace(result, **self.probe.result_overrides)


def fake_build_result(*, source_path, output_path, kwargs, warnings=()):
    output_is_file = output_path.is_file()
    return DatasetBuildResult(
        csv_path=output_path,
        builder_id="alpha",
        builder_version="1.0.0",
        mode=kwargs.get("mode", "annual"),
        start_year=kwargs.get("start_year", 2000),
        end_year=kwargs.get("end_year", 2003),
        period_column="year",
        category_column="country",
        value_column="value",
        row_count=1,
        period_count=1,
        category_count=1,
        source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        output_sha256=(
            hashlib.sha256(output_path.read_bytes()).hexdigest()
            if output_is_file
            else "0" * 64
        ),
        source_size_bytes=source_path.stat().st_size,
        output_size_bytes=output_path.stat().st_size if output_is_file else 0,
        source_min_date=date(2000, 1, 1),
        source_max_date=date(2003, 12, 31),
        matches_read=4,
        matches_used=4,
        discarded_rows=0,
        warnings=tuple(warnings),
        effective_parameters=(),
    )


class ProductionOrchestratorTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()
        self.jobs_root = self.temp_path / "jobs"

    def test_real_success_flow_reaches_dataset_ready(self):
        result = self.prepare_real()

        self.assertIsInstance(result, DatasetProductionResult)
        self.assertIsInstance(result.build_result, DatasetBuildResult)
        self.assertIsInstance(
            result.workspace,
            ProductionWorkspace,
        )
        self.assertEqual(self.read_json(result.status_path)["state"], "dataset_ready")

    def test_result_is_immutable(self):
        result = self.prepare_real()

        with self.assertRaises(FrozenInstanceError):
            result.status_path = Path("changed")

    def test_result_paths_are_absolute_and_resolved(self):
        result = self.prepare_real()
        paths = (
            result.brief.dataset.source_csv,
            result.workspace.root_path,
            result.build_result.csv_path,
            result.dataset_manifest_path,
            result.status_path,
        )

        for path in paths:
            self.assertTrue(path.is_absolute())
            self.assertEqual(path, path.resolve())

    def test_dataset_is_inside_workspace(self):
        result = self.prepare_real()

        self.assertTrue(result.build_result.csv_path.is_relative_to(result.workspace.root_path))
        self.assertEqual(result.build_result.csv_path, result.workspace.dataset_csv_path)

    def test_real_dataset_passes_dataset_validator(self):
        result = self.prepare_real()

        validated = DatasetValidator(
            DatasetConfig(
                year_column=result.build_result.period_column,
                name_column=result.build_result.category_column,
                value_column=result.build_result.value_column,
            )
        ).validate(pd.read_csv(result.build_result.csv_path))
        self.assertFalse(validated.empty)

    def test_final_status_is_dataset_ready(self):
        result = self.prepare_real()

        self.assertEqual(
            self.read_json(result.status_path),
            {
                "production_status_schema_version": 1,
                "job_id": result.brief.job_id,
                "state": "dataset_ready",
                "stage": "dataset",
                "message": "Dataset built and validated.",
                "artifacts": {
                    "dataset": "dataset/dataset.csv",
                    "dataset_manifest": "manifests/dataset_build.json",
                },
            },
        )

    def test_final_status_contains_only_relative_artifact_paths(self):
        artifacts = self.read_json(self.prepare_real().status_path)["artifacts"]

        self.assertEqual(artifacts["dataset"], "dataset/dataset.csv")
        self.assertEqual(
            artifacts["dataset_manifest"],
            "manifests/dataset_build.json",
        )
        self.assertTrue(all(":" not in value for value in artifacts.values()))

    def test_dataset_manifest_uses_independent_version_one(self):
        manifest = self.read_json(self.prepare_real().dataset_manifest_path)

        self.assertEqual(
            manifest["dataset_build_manifest_schema_version"],
            DATASET_BUILD_MANIFEST_SCHEMA_VERSION,
        )
        self.assertEqual(DATASET_BUILD_MANIFEST_SCHEMA_VERSION, 1)

    def test_dataset_manifest_is_deterministic(self):
        first = self.prepare_real(workspace_root=self.temp_path / "first")
        second = self.prepare_real(workspace_root=self.temp_path / "second")

        self.assertEqual(
            first.dataset_manifest_path.read_bytes(),
            second.dataset_manifest_path.read_bytes(),
        )

    def test_dataset_manifest_contains_no_absolute_paths(self):
        result = self.prepare_real()
        text = result.dataset_manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(text)

        self.assertEqual(
            manifest["source"]["path"],
            "tests/automation/fixtures/national_team_goals_source.csv",
        )
        self.assertEqual(manifest["dataset"]["path"], "dataset/dataset.csv")
        self.assertNotIn(str(ROOT_DIR), text)
        self.assertNotIn(str(self.temp_path), text)
        self.assertNotIn(str(Path.home()), text)

    def test_dataset_manifest_contains_no_timestamps(self):
        manifest = self.read_json(self.prepare_real().dataset_manifest_path)
        keys = tuple(self.walk_keys(manifest))

        self.assertFalse(any("timestamp" in key.casefold() for key in keys))
        self.assertNotIn("created_at", keys)
        self.assertNotIn("updated_at", keys)

    def test_manifest_parameters_are_sorted(self):
        manifest = self.read_json(self.prepare_real().dataset_manifest_path)

        self.assertEqual(
            list(manifest["parameters"]),
            ["duplicate_policy", "end_year", "mode", "start_year"],
        )

    def test_manifest_hashes_and_sizes_match_build_result(self):
        result = self.prepare_real()
        manifest = self.read_json(result.dataset_manifest_path)

        self.assertEqual(manifest["source"]["sha256"], result.build_result.source_sha256)
        self.assertEqual(
            manifest["source"]["size_bytes"],
            result.build_result.source_size_bytes,
        )
        self.assertEqual(manifest["dataset"]["sha256"], result.build_result.output_sha256)
        self.assertEqual(
            manifest["dataset"]["size_bytes"],
            result.build_result.output_size_bytes,
        )

    def test_manifest_dates_are_iso_strings(self):
        result = self.prepare_real()
        source = self.read_json(result.dataset_manifest_path)["source"]

        self.assertEqual(source["min_date"], result.build_result.source_min_date.isoformat())
        self.assertEqual(source["max_date"], result.build_result.source_max_date.isoformat())

    def test_manifest_preserves_builder_warning_order(self):
        warnings = ("first warning", "second warning")
        result, _probe, _parser, _registry = self.prepare_fake(warnings=warnings)

        self.assertEqual(
            self.read_json(result.dataset_manifest_path)["warnings"],
            list(warnings),
        )

    def test_builder_is_invoked_exactly_once(self):
        _result, probe, _parser, _registry = self.prepare_fake()

        self.assertEqual(probe.build_calls, 1)

    def test_parameter_parser_is_invoked_exactly_once(self):
        _result, _probe, parser, _registry = self.prepare_fake()

        self.assertEqual(parser.calls, 1)

    def test_builder_receives_exact_arguments(self):
        result, probe, _parser, _registry = self.prepare_fake()

        self.assertEqual(
            probe.received_kwargs,
            [
                {
                    "source_csv": SOURCE_FIXTURE_PATH,
                    "output_csv": result.workspace.dataset_csv_path,
                    "expected_source_sha256": None,
                    "start_year": 2000,
                    "end_year": 2003,
                    "mode": "annual",
                    "duplicate_policy": "allow",
                }
            ],
        )

    def test_brief_is_not_modified(self):
        brief = self.load_valid_brief()
        before = brief

        result = self.real_orchestrator().prepare_dataset(
            brief,
            workspace_root_dir=self.jobs_root,
            source_root_dir=ROOT_DIR,
        )

        self.assertIs(result.brief, brief)
        self.assertEqual(brief, before)

    def test_registry_is_not_modified(self):
        registry = create_default_dataset_builder_registry()
        snapshot = (
            registry.available_builder_ids,
            registry._definitions,
            tuple(registry._factories.items()),
            tuple(registry._parameter_parsers.items()),
        )

        ProductionOrchestrator(registry).prepare_dataset(
            self.load_valid_brief(),
            workspace_root_dir=self.jobs_root,
            source_root_dir=ROOT_DIR,
        )

        self.assertEqual(
            snapshot,
            (
                registry.available_builder_ids,
                registry._definitions,
                tuple(registry._factories.items()),
                tuple(registry._parameter_parsers.items()),
            ),
        )

    def test_source_outside_source_root_creates_no_workspace(self):
        unrelated_root = self.temp_path / "unrelated"
        unrelated_root.mkdir()

        with self.assertRaisesRegex(ProductionOrchestrationError, "preflight"):
            self.real_orchestrator().prepare_dataset(
                self.load_valid_brief(),
                workspace_root_dir=self.jobs_root,
                source_root_dir=unrelated_root,
            )

        self.assertFalse(self.jobs_root.exists())

    def test_missing_source_root_creates_no_workspace(self):
        with self.assertRaisesRegex(ProductionOrchestrationError, "preflight"):
            self.real_orchestrator().prepare_dataset(
                self.load_valid_brief(),
                workspace_root_dir=self.jobs_root,
                source_root_dir=self.temp_path / "missing",
            )

        self.assertFalse(self.jobs_root.exists())

    def test_source_root_file_creates_no_workspace(self):
        root_file = self.temp_path / "not-a-directory"
        root_file.write_text("file", encoding="utf-8")

        with self.assertRaisesRegex(ProductionOrchestrationError, "preflight"):
            self.real_orchestrator().prepare_dataset(
                self.load_valid_brief(),
                workspace_root_dir=self.jobs_root,
                source_root_dir=root_file,
            )

        self.assertFalse(self.jobs_root.exists())

    def test_unknown_builder_creates_no_workspace(self):
        brief = self.fake_brief(builder_id="missing")
        registry, _probe, _parser = self.fake_registry()

        with self.assertRaisesRegex(ProductionOrchestrationError, "preflight"):
            ProductionOrchestrator(registry).prepare_dataset(
                brief,
                workspace_root_dir=self.jobs_root,
                source_root_dir=ROOT_DIR,
            )

        self.assertFalse(self.jobs_root.exists())

    def test_invalid_parameters_create_no_workspace(self):
        parser_error = ValueError("invalid fake parameters")
        registry, _probe, _parser = self.fake_registry(parser_error=parser_error)

        with self.assertRaises(ProductionOrchestrationError):
            ProductionOrchestrator(registry).prepare_dataset(
                self.fake_brief(),
                workspace_root_dir=self.jobs_root,
                source_root_dir=ROOT_DIR,
            )

        self.assertFalse(self.jobs_root.exists())

    def test_factory_failure_creates_no_workspace(self):
        registry, _probe, _parser = self.fake_registry(
            fail_factory_after_validation=True
        )

        with self.assertRaises(ProductionOrchestrationError):
            ProductionOrchestrator(registry).prepare_dataset(
                self.fake_brief(),
                workspace_root_dir=self.jobs_root,
                source_root_dir=ROOT_DIR,
            )

        self.assertFalse(self.jobs_root.exists())

    def test_workspace_collision_does_not_execute_builder(self):
        brief = self.fake_brief()
        existing = ProductionWorkspace.create(
            job_id=brief.job_id,
            root_dir=self.jobs_root,
        )
        registry, probe, _parser = self.fake_registry()

        with self.assertRaisesRegex(ProductionOrchestrationError, "workspace"):
            ProductionOrchestrator(registry).prepare_dataset(
                brief,
                workspace_root_dir=self.jobs_root,
                source_root_dir=ROOT_DIR,
            )

        self.assertEqual(probe.build_calls, 0)
        self.assertTrue(existing.root_path.is_dir())

    def test_workspace_collision_preserves_existing_content(self):
        brief = self.fake_brief()
        existing = ProductionWorkspace.create(
            job_id=brief.job_id,
            root_dir=self.jobs_root,
        )
        marker = existing.logs_dir / "keep.txt"
        marker.write_text("preserve", encoding="utf-8")
        registry, _probe, _parser = self.fake_registry()

        with self.assertRaises(ProductionOrchestrationError):
            ProductionOrchestrator(registry).prepare_dataset(
                brief,
                workspace_root_dir=self.jobs_root,
                source_root_dir=ROOT_DIR,
            )

        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_builder_error_leaves_workspace(self):
        error = RuntimeError("directed builder failure")

        with self.assertRaises(ProductionOrchestrationError):
            self.prepare_fake(build_error=error)

        self.assertTrue((self.jobs_root / "fake-job").is_dir())

    def test_builder_error_sets_failed_status(self):
        with self.assertRaises(ProductionOrchestrationError):
            self.prepare_fake(build_error=RuntimeError("builder failure"))

        status = self.read_json(self.jobs_root / "fake-job" / "status.json")
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["error"]["phase"], "builder")
        self.assertEqual(status["error"]["type"], "RuntimeError")

    def test_builder_error_creates_no_dataset_manifest(self):
        with self.assertRaises(ProductionOrchestrationError):
            self.prepare_fake(build_error=RuntimeError("builder failure"))

        self.assertFalse(
            (self.jobs_root / "fake-job" / "manifests" / "dataset_build.json").exists()
        )

    def test_builder_returning_wrong_type_fails(self):
        with self.assertRaisesRegex(ProductionOrchestrationError, "builder") as captured:
            self.prepare_fake(behavior="wrong_type")

        self.assertIsInstance(captured.exception.__cause__, TypeError)

    def test_builder_returning_external_path_fails(self):
        external = self.temp_path / "external" / "dataset.csv"

        with self.assertRaisesRegex(ProductionOrchestrationError, "builder"):
            self.prepare_fake(behavior="external", external_path=external)

        self.assertTrue(external.is_file())
        self.assertFalse(
            (self.jobs_root / "fake-job" / "manifests" / "dataset_build.json").exists()
        )

    def test_builder_returning_other_id_fails(self):
        with self.assertRaisesRegex(ProductionOrchestrationError, "builder"):
            self.prepare_fake(result_overrides={"builder_id": "beta"})

        self.assertEqual(self.failed_phase(), "builder")

    def test_builder_returning_other_version_fails(self):
        with self.assertRaisesRegex(ProductionOrchestrationError, "builder"):
            self.prepare_fake(result_overrides={"builder_version": "2.0.0"})

        self.assertEqual(self.failed_phase(), "builder")

    def test_builder_not_creating_csv_fails(self):
        with self.assertRaisesRegex(ProductionOrchestrationError, "builder"):
            self.prepare_fake(behavior="no_file")

        self.assertEqual(self.failed_phase(), "builder")

    def test_builder_creating_directory_instead_of_csv_fails(self):
        with self.assertRaisesRegex(ProductionOrchestrationError, "builder"):
            self.prepare_fake(behavior="directory")

        self.assertTrue((self.jobs_root / "fake-job" / "dataset" / "dataset.csv").is_dir())
        self.assertEqual(self.failed_phase(), "builder")

    def test_invalid_dataset_sets_failed_status(self):
        with self.assertRaisesRegex(ProductionOrchestrationError, "validation"):
            self.prepare_fake(behavior="invalid_dataset")

        self.assertEqual(self.failed_phase(), "validation")

    def test_invalid_dataset_preserves_csv(self):
        with self.assertRaises(ProductionOrchestrationError):
            self.prepare_fake(behavior="invalid_dataset")

        dataset_path = self.jobs_root / "fake-job" / "dataset" / "dataset.csv"
        self.assertTrue(dataset_path.is_file())
        self.assertIn("year,country", dataset_path.read_text(encoding="utf-8"))

    def test_invalid_dataset_creates_no_manifest(self):
        with self.assertRaises(ProductionOrchestrationError):
            self.prepare_fake(behavior="invalid_dataset")

        self.assertFalse(
            (self.jobs_root / "fake-job" / "manifests" / "dataset_build.json").exists()
        )

    def test_manifest_publication_failure_sets_failed_status(self):
        with mock.patch.object(
            ProductionWorkspace,
            "publish_dataset_build_manifest",
            side_effect=OSError("manifest publication failed"),
        ):
            with self.assertRaisesRegex(ProductionOrchestrationError, "manifest"):
                self.prepare_fake()

        self.assertEqual(self.failed_phase(), "manifest")

    def test_manifest_failure_preserves_dataset(self):
        with mock.patch.object(
            ProductionWorkspace,
            "publish_dataset_build_manifest",
            side_effect=OSError("manifest publication failed"),
        ):
            with self.assertRaises(ProductionOrchestrationError):
                self.prepare_fake()

        self.assertTrue(
            (self.jobs_root / "fake-job" / "dataset" / "dataset.csv").is_file()
        )

    def test_initial_status_write_failure_is_contextual(self):
        with mock.patch.object(
            ProductionWorkspace,
            "replace_status",
            side_effect=OSError("initial status failed"),
        ):
            with self.assertRaisesRegex(ProductionOrchestrationError, "status") as captured:
                self.prepare_fake()

        self.assertIsInstance(captured.exception.__cause__, OSError)
        self.assertTrue((self.jobs_root / "fake-job").is_dir())

    def test_final_status_write_failure_records_failed_state(self):
        original = ProductionWorkspace.replace_status
        calls = 0

        def fail_final(workspace, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("final status failed")
            return original(workspace, data)

        with mock.patch.object(
            ProductionWorkspace,
            "replace_status",
            autospec=True,
            side_effect=fail_final,
        ):
            with self.assertRaisesRegex(ProductionOrchestrationError, "status"):
                self.prepare_fake()

        self.assertEqual(calls, 3)
        self.assertEqual(self.failed_phase(), "status")

    def test_failed_status_error_does_not_hide_builder_error(self):
        original_error = RuntimeError("original builder failure")
        original_replace = ProductionWorkspace.replace_status
        calls = 0

        def fail_failed_status(workspace, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("failed status write failed")
            return original_replace(workspace, data)

        with mock.patch.object(
            ProductionWorkspace,
            "replace_status",
            autospec=True,
            side_effect=fail_failed_status,
        ):
            with self.assertRaises(ProductionOrchestrationError) as captured:
                self.prepare_fake(build_error=original_error)

        self.assertIs(captured.exception.__cause__, original_error)
        self.assertIn("failed dataset status", " ".join(original_error.__notes__))

    def test_workspace_is_never_deleted_after_failure(self):
        with self.assertRaises(ProductionOrchestrationError):
            self.prepare_fake(build_error=RuntimeError("failure"))

        workspace_path = self.jobs_root / "fake-job"
        self.assertTrue(workspace_path.is_dir())
        self.assertTrue((workspace_path / "workspace_manifest.json").is_file())

    def test_failure_does_not_modify_other_workspace(self):
        other = ProductionWorkspace.create(job_id="other-job", root_dir=self.jobs_root)
        marker = other.logs_dir / "keep.txt"
        marker.write_text("untouched", encoding="utf-8")

        with self.assertRaises(ProductionOrchestrationError):
            self.prepare_fake(build_error=RuntimeError("failure"))

        self.assertEqual(marker.read_text(encoding="utf-8"), "untouched")

    def test_preexisting_dataset_manifest_is_not_overwritten(self):
        with self.assertRaisesRegex(ProductionOrchestrationError, "manifest"):
            self.prepare_fake(behavior="preexisting_manifest")

        manifest_path = (
            self.jobs_root / "fake-job" / "manifests" / "dataset_build.json"
        )
        self.assertEqual(manifest_path.read_bytes(), b"preserve existing manifest\n")

    def test_status_and_manifest_are_utf8_without_bom(self):
        result = self.prepare_real()

        for path in (result.status_path, result.dataset_manifest_path):
            content = path.read_bytes()
            self.assertFalse(content.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(content.decode("utf-8"), path.read_text(encoding="utf-8"))

    def test_status_and_manifest_end_with_one_lf(self):
        result = self.prepare_real()

        for path in (result.status_path, result.dataset_manifest_path):
            content = path.read_bytes()
            self.assertTrue(content.endswith(b"\n"))
            self.assertFalse(content.endswith(b"\n\n"))
            self.assertNotIn(b"\r", content)

    def test_success_leaves_no_temporary_files(self):
        result = self.prepare_real()

        self.assertEqual(list(result.workspace.root_path.rglob("*.tmp")), [])

    def test_manifest_publication_failure_cleans_temporary_file(self):
        original_link = os.link

        def fail_dataset_manifest(source, destination, *args, **kwargs):
            if Path(destination).name == "dataset_build.json":
                raise OSError("directed hardlink failure")
            return original_link(source, destination, *args, **kwargs)

        with mock.patch.object(os, "link", side_effect=fail_dataset_manifest):
            with self.assertRaisesRegex(ProductionOrchestrationError, "manifest"):
                self.prepare_fake()

        workspace_path = self.jobs_root / "fake-job"
        self.assertEqual(list(workspace_path.rglob("*.tmp")), [])

    def test_two_roots_produce_equivalent_dataset_and_manifest(self):
        first = self.prepare_real(workspace_root=self.temp_path / "one")
        second = self.prepare_real(workspace_root=self.temp_path / "two")

        self.assertEqual(
            first.build_result.csv_path.read_bytes(),
            second.build_result.csv_path.read_bytes(),
        )
        self.assertEqual(
            first.dataset_manifest_path.read_bytes(),
            second.dataset_manifest_path.read_bytes(),
        )

    def test_orchestration_uses_no_network(self):
        failure = AssertionError("Network access attempted.")
        with (
            mock.patch.object(socket, "socket", side_effect=failure),
            mock.patch.object(socket, "create_connection", side_effect=failure),
        ):
            self.prepare_real()

    def test_orchestration_uses_no_subprocesses(self):
        failure = AssertionError("Subprocess attempted.")
        with (
            mock.patch.object(subprocess, "Popen", side_effect=failure),
            mock.patch.object(subprocess, "run", side_effect=failure),
        ):
            self.prepare_real()

    def test_orchestrator_has_no_streamlit_dependency(self):
        source = inspect.getsource(orchestrator_module).casefold()

        self.assertNotIn("streamlit", source)

    def test_orchestrator_has_no_renderer_or_ffmpeg_dependency(self):
        source = inspect.getsource(orchestrator_module).casefold()

        self.assertNotIn("renderer", source)
        self.assertNotIn("ffmpeg", source)
        self.assertNotIn("renderjob", source)

    def test_orchestration_creates_no_logo_files(self):
        result = self.prepare_real()

        self.assertTrue(result.workspace.logos_dir.is_dir())
        self.assertEqual(list(result.workspace.logos_dir.iterdir()), [])

    def test_orchestration_creates_no_project_json(self):
        result = self.prepare_real()

        self.assertFalse(result.workspace.project_json_path.exists())
        self.assertEqual(list(result.workspace.project_dir.iterdir()), [])

    def test_orchestration_creates_no_video(self):
        result = self.prepare_real()

        self.assertFalse(result.workspace.video_path.exists())
        self.assertEqual(list(result.workspace.render_dir.iterdir()), [])

    def test_source_file_is_not_modified(self):
        before_bytes = SOURCE_FIXTURE_PATH.read_bytes()
        before_stat = SOURCE_FIXTURE_PATH.stat()

        self.prepare_real()

        after_stat = SOURCE_FIXTURE_PATH.stat()
        self.assertEqual(SOURCE_FIXTURE_PATH.read_bytes(), before_bytes)
        self.assertEqual(after_stat.st_size, before_stat.st_size)
        self.assertEqual(after_stat.st_mtime_ns, before_stat.st_mtime_ns)

    def test_builder_does_not_know_orchestrator(self):
        module = sys.modules[NationalTeamGoalsDatasetBuilder.__module__]
        source = inspect.getsource(module)

        self.assertNotIn("ProductionOrchestrator", source)
        self.assertNotIn("automation.orchestrator", source)

    def test_workspace_does_not_know_registry(self):
        source = inspect.getsource(workspace_module)

        self.assertNotIn("DatasetBuilderRegistry", source)
        self.assertNotIn("automation.registry", source)

    def test_running_status_is_visible_during_builder_execution(self):
        _result, probe, _parser, _registry = self.prepare_fake()

        self.assertEqual(
            probe.running_status,
            {
                "production_status_schema_version": 1,
                "job_id": "fake-job",
                "state": "running",
                "stage": "dataset",
                "message": "Building and validating dataset.",
            },
        )

    def test_prepare_dataset_does_not_load_brief_from_disk(self):
        brief = self.load_valid_brief()
        with mock.patch(
            "automation.brief_loader.load_production_brief",
            side_effect=AssertionError("Brief load attempted."),
        ):
            result = self.real_orchestrator().prepare_dataset(
                brief,
                workspace_root_dir=self.jobs_root,
                source_root_dir=ROOT_DIR,
            )

        self.assertIs(result.brief, brief)
        self.assertNotIn("load_production_brief", inspect.getsource(orchestrator_module))

    def prepare_real(self, *, workspace_root=None):
        return self.real_orchestrator().prepare_dataset(
            self.load_valid_brief(),
            workspace_root_dir=workspace_root or self.jobs_root,
            source_root_dir=ROOT_DIR,
        )

    def prepare_fake(self, **options):
        registry, probe, parser = self.fake_registry(**options)
        result = ProductionOrchestrator(registry).prepare_dataset(
            self.fake_brief(),
            workspace_root_dir=self.jobs_root,
            source_root_dir=ROOT_DIR,
        )
        return result, probe, parser, registry

    @staticmethod
    def real_orchestrator():
        return ProductionOrchestrator(create_default_dataset_builder_registry())

    @staticmethod
    def load_valid_brief():
        return load_production_brief(VALID_BRIEF_PATH, root_dir=ROOT_DIR)

    @staticmethod
    def fake_brief(*, builder_id="alpha"):
        return ProductionBrief(
            schema_version=1,
            job_id="fake-job",
            dataset=DatasetBrief(
                builder_id=builder_id,
                source_csv=SOURCE_FIXTURE_PATH,
                expected_source_sha256=None,
                parameters=FrozenParameters.from_mapping({}),
            ),
        )

    @staticmethod
    def fake_registry(
        *,
        parser_error=None,
        fail_factory_after_validation=False,
        **probe_options,
    ):
        probe = BuilderProbe(
            fail_factory_after_validation=fail_factory_after_validation,
            **probe_options,
        )
        parser = ParserProbe(error=parser_error)
        registry = DatasetBuilderRegistry(
            (
                DatasetBuilderDefinition(
                    builder_id="alpha",
                    factory=probe.factory,
                    parameter_parser=parser,
                ),
            )
        )
        return registry, probe, parser

    @staticmethod
    def read_json(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def failed_phase(self):
        return self.read_json(self.jobs_root / "fake-job" / "status.json")["error"][
            "phase"
        ]

    @staticmethod
    def walk_keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from ProductionOrchestratorTest.walk_keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from ProductionOrchestratorTest.walk_keys(item)


if __name__ == "__main__":
    unittest.main()
