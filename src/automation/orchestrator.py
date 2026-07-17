from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import pandas as pd

from automation.models import DatasetBuildResult, ProductionBrief
from automation.registry import DatasetBuilderRegistry
from automation.workspace import (
    PRODUCTION_STATUS_SCHEMA_VERSION,
    ProductionWorkspace,
)
from config.dataset_config import DatasetConfig
from validators.dataset_validator import DatasetValidator


DATASET_BUILD_MANIFEST_SCHEMA_VERSION = 1
_RESERVED_BUILD_ARGUMENTS = frozenset(
    ("source_csv", "output_csv", "expected_source_sha256")
)


class ProductionOrchestrationError(RuntimeError):
    """Raised when the dataset production stage cannot complete."""


@runtime_checkable
class DatasetBuildParameterArguments(Protocol):
    """Explicit adapter from typed parameters to builder keyword arguments."""

    def to_build_kwargs(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class DatasetProductionResult:
    """Immutable result of one completed dataset production stage."""

    brief: ProductionBrief
    workspace: ProductionWorkspace
    build_result: DatasetBuildResult
    dataset_manifest_path: Path
    status_path: Path

    def __post_init__(self) -> None:
        manifest_path = Path(self.dataset_manifest_path).resolve(strict=False)
        status_path = Path(self.status_path).resolve(strict=False)
        dataset_path = Path(self.build_result.csv_path)
        if manifest_path != self.workspace.dataset_build_manifest_path:
            raise ValueError(
                "dataset_manifest_path must be the workspace dataset manifest."
            )
        if status_path != self.workspace.status_path:
            raise ValueError("status_path must be the workspace status path.")
        if (
            not dataset_path.is_absolute()
            or dataset_path.resolve(strict=False) != self.workspace.dataset_csv_path
        ):
            raise ValueError("build_result.csv_path must be the workspace dataset CSV.")
        object.__setattr__(self, "dataset_manifest_path", manifest_path)
        object.__setattr__(self, "status_path", status_path)


@dataclass(frozen=True)
class ProductionOrchestrator:
    """Orchestrate only the build-and-validation stage of dataset production."""

    registry: DatasetBuilderRegistry

    def __post_init__(self) -> None:
        if not isinstance(self.registry, DatasetBuilderRegistry):
            raise TypeError("registry must be a DatasetBuilderRegistry.")

    def prepare_dataset(
        self,
        brief: ProductionBrief,
        *,
        workspace_root_dir: Path,
        source_root_dir: Path,
    ) -> DatasetProductionResult:
        job_id = brief.job_id if isinstance(brief, ProductionBrief) else "<invalid>"
        try:
            (
                source_path,
                source_reference,
                builder,
                build_kwargs,
            ) = self._validate_without_side_effects(
                brief,
                source_root_dir=source_root_dir,
            )
        except Exception as exc:
            raise self._error(
                job_id,
                "preflight",
                "validating dataset production inputs",
            ) from exc

        try:
            workspace = ProductionWorkspace.create(
                job_id=brief.job_id,
                root_dir=workspace_root_dir,
            )
        except Exception as exc:
            raise self._error(
                brief.job_id,
                "workspace",
                "creating the production workspace",
            ) from exc

        dataset_path = workspace.dataset_csv_path
        phase = "status"
        try:
            workspace.replace_status(self._running_status(brief.job_id))

            phase = "builder"
            build_result = builder.build(
                source_csv=source_path,
                output_csv=dataset_path,
                expected_source_sha256=brief.dataset.expected_source_sha256,
                **build_kwargs,
            )
            self._validate_build_result(
                build_result,
                workspace=workspace,
                expected_dataset_path=dataset_path,
                requested_builder_id=brief.dataset.builder_id,
                builder_version=builder.builder_version,
            )

            phase = "validation"
            self._validate_dataset(build_result)

            phase = "manifest"
            manifest = self._dataset_manifest(
                brief=brief,
                build_result=build_result,
                source_reference=source_reference,
                build_kwargs=build_kwargs,
                workspace=workspace,
            )
            workspace.publish_dataset_build_manifest(manifest)

            phase = "status"
            workspace.replace_status(self._ready_status(brief.job_id))
        except Exception as exc:
            self._record_failed_status_best_effort(
                workspace,
                job_id=brief.job_id,
                phase=phase,
                original_error=exc,
            )
            raise self._error(
                brief.job_id,
                phase,
                self._operation_for_phase(phase),
            ) from exc

        return DatasetProductionResult(
            brief=brief,
            workspace=workspace,
            build_result=build_result,
            dataset_manifest_path=workspace.dataset_build_manifest_path,
            status_path=workspace.status_path,
        )

    def _validate_without_side_effects(
        self,
        brief: ProductionBrief,
        *,
        source_root_dir: Path,
    ) -> tuple[Path, str, object, dict[str, object]]:
        if not isinstance(brief, ProductionBrief):
            raise TypeError("brief must be a validated ProductionBrief.")

        root = Path(source_root_dir).resolve(strict=True)
        if not root.is_dir():
            raise NotADirectoryError("source_root_dir must be an existing directory.")

        source_path = brief.dataset.source_csv
        if not isinstance(source_path, Path):
            raise TypeError("Dataset source path must be a pathlib.Path.")
        if not source_path.is_absolute():
            raise ValueError("Dataset source path must be absolute and resolved.")
        resolved_source = source_path.resolve(strict=True)
        if resolved_source != source_path:
            raise ValueError("Dataset source path must be absolute and resolved.")
        if not resolved_source.is_file():
            raise ValueError("Dataset source path must be a regular file.")
        if not resolved_source.is_relative_to(root):
            raise ValueError("Dataset source path must remain inside source_root_dir.")
        source_reference = resolved_source.relative_to(root).as_posix()

        typed_parameters = self.registry.parse_parameters(
            brief.dataset.builder_id,
            brief.dataset.parameters,
        )
        builder = self.registry.create(brief.dataset.builder_id)
        if not isinstance(typed_parameters, DatasetBuildParameterArguments):
            raise TypeError(
                "Typed builder parameters must provide to_build_kwargs()."
            )
        build_kwargs = typed_parameters.to_build_kwargs()
        if not isinstance(build_kwargs, dict):
            raise TypeError("to_build_kwargs() must return a new dictionary.")
        if any(not isinstance(key, str) for key in build_kwargs):
            raise TypeError("Builder keyword argument names must be strings.")
        reserved = sorted(set(build_kwargs) & _RESERVED_BUILD_ARGUMENTS)
        if reserved:
            raise ValueError(
                "Typed parameters must not provide reserved build arguments: "
                + ", ".join(reserved)
                + "."
            )
        return source_path, source_reference, builder, dict(build_kwargs)

    @staticmethod
    def _validate_build_result(
        build_result: object,
        *,
        workspace: ProductionWorkspace,
        expected_dataset_path: Path,
        requested_builder_id: str,
        builder_version: str,
    ) -> None:
        if not isinstance(build_result, DatasetBuildResult):
            raise TypeError("Dataset builder must return DatasetBuildResult.")

        declared_path = build_result.csv_path
        if not isinstance(declared_path, Path) or declared_path != expected_dataset_path:
            raise ValueError(
                "Dataset builder reported a CSV path different from the workspace output."
            )
        if not declared_path.is_absolute():
            raise ValueError("Dataset builder CSV path must be absolute.")
        try:
            resolved_dataset = declared_path.resolve(strict=True)
        except OSError as exc:
            raise ValueError("Dataset builder did not create the declared CSV.") from exc
        if resolved_dataset != declared_path or not resolved_dataset.is_relative_to(
            workspace.root_path
        ):
            raise ValueError("Dataset builder output must remain inside the workspace.")
        if not resolved_dataset.is_file():
            raise ValueError("Dataset builder output must be a regular CSV file.")
        if build_result.builder_id != requested_builder_id:
            raise ValueError("Dataset build result declares a different builder_id.")
        if build_result.builder_version != builder_version:
            raise ValueError("Dataset build result declares a different builder_version.")

        columns = (
            build_result.period_column,
            build_result.category_column,
            build_result.value_column,
        )
        if any(not isinstance(column, str) or not column.strip() for column in columns):
            raise ValueError("Dataset build result columns must be non-empty strings.")
        if len(set(columns)) != len(columns):
            raise ValueError("Dataset build result columns must be distinct.")

    @staticmethod
    def _validate_dataset(build_result: DatasetBuildResult) -> None:
        dataframe = pd.read_csv(build_result.csv_path, encoding="utf-8")
        DatasetValidator(
            DatasetConfig(
                year_column=build_result.period_column,
                name_column=build_result.category_column,
                value_column=build_result.value_column,
            )
        ).validate(dataframe)

    @staticmethod
    def _dataset_manifest(
        *,
        brief: ProductionBrief,
        build_result: DatasetBuildResult,
        source_reference: str,
        build_kwargs: dict[str, object],
        workspace: ProductionWorkspace,
    ) -> dict:
        return {
            "dataset_build_manifest_schema_version": (
                DATASET_BUILD_MANIFEST_SCHEMA_VERSION
            ),
            "job_id": brief.job_id,
            "builder": {
                "id": build_result.builder_id,
                "version": build_result.builder_version,
            },
            "source": {
                "path": source_reference,
                "sha256": build_result.source_sha256,
                "size_bytes": build_result.source_size_bytes,
                "min_date": build_result.source_min_date.isoformat(),
                "max_date": build_result.source_max_date.isoformat(),
                "matches_read": build_result.matches_read,
                "matches_used": build_result.matches_used,
                "discarded_rows": build_result.discarded_rows,
            },
            "parameters": {
                key: build_kwargs[key] for key in sorted(build_kwargs)
            },
            "dataset": {
                "path": build_result.csv_path.relative_to(
                    workspace.root_path
                ).as_posix(),
                "sha256": build_result.output_sha256,
                "size_bytes": build_result.output_size_bytes,
                "columns": {
                    "period": build_result.period_column,
                    "category": build_result.category_column,
                    "value": build_result.value_column,
                },
                "row_count": build_result.row_count,
                "period_count": build_result.period_count,
                "category_count": build_result.category_count,
            },
            "warnings": list(build_result.warnings),
        }

    @staticmethod
    def _running_status(job_id: str) -> dict:
        return {
            "production_status_schema_version": PRODUCTION_STATUS_SCHEMA_VERSION,
            "job_id": job_id,
            "state": "running",
            "stage": "dataset",
            "message": "Building and validating dataset.",
        }

    @staticmethod
    def _ready_status(job_id: str) -> dict:
        return {
            "production_status_schema_version": PRODUCTION_STATUS_SCHEMA_VERSION,
            "job_id": job_id,
            "state": "dataset_ready",
            "stage": "dataset",
            "message": "Dataset built and validated.",
            "artifacts": {
                "dataset": "dataset/dataset.csv",
                "dataset_manifest": "manifests/dataset_build.json",
            },
        }

    @staticmethod
    def _record_failed_status_best_effort(
        workspace: ProductionWorkspace,
        *,
        job_id: str,
        phase: str,
        original_error: Exception,
    ) -> None:
        failed_status = {
            "production_status_schema_version": PRODUCTION_STATUS_SCHEMA_VERSION,
            "job_id": job_id,
            "state": "failed",
            "stage": "dataset",
            "message": "Dataset production failed.",
            "error": {
                "type": type(original_error).__name__,
                "phase": phase,
            },
        }
        try:
            workspace.replace_status(failed_status)
        except Exception as status_error:
            original_error.add_note(
                "Writing the failed dataset status also failed: "
                f"{type(status_error).__name__}."
            )

    @staticmethod
    def _operation_for_phase(phase: str) -> str:
        return {
            "status": "updating dataset production status",
            "builder": "building the dataset",
            "validation": "validating the dataset",
            "manifest": "publishing the dataset manifest",
        }[phase]

    @staticmethod
    def _error(job_id: str, phase: str, operation: str) -> ProductionOrchestrationError:
        return ProductionOrchestrationError(
            f"Production job {job_id!r} failed during {phase!r} while {operation}."
        )
