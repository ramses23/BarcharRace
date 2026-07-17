from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TYPE_CHECKING, runtime_checkable

import pandas as pd

from automation.models import DatasetBuildResult, ProductionBrief, ProductionBriefV2
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
_RUN_RESULT_STATES = frozenset(("blocked", "preflight_ready", "completed", "canceled"))


if TYPE_CHECKING:
    from automation.logo_resolver import LogoResolutionResult
    from automation.production_preflight import ProductionPreflightResult
    from automation.project_assembler import ProjectAssemblyResult
    from automation.render_executor import ProductionRenderResult


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
class ProductionRunProgress:
    """Deeply immutable progress event for the complete production pipeline."""

    state: str
    stage: str
    message: str
    progress: float
    current: int = 0
    total: int = 0
    artifacts: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("state", "stage", "message"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string.")
        if (
            isinstance(self.progress, bool)
            or not isinstance(self.progress, (int, float))
            or not math.isfinite(float(self.progress))
            or not 0.0 <= float(self.progress) <= 1.0
        ):
            raise ValueError("progress must be a finite number between 0 and 1.")
        object.__setattr__(self, "progress", float(self.progress))
        for field_name in ("current", "total"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer.")
        artifacts = tuple(self.artifacts)
        keys = []
        for item in artifacts:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not all(isinstance(value, str) and value for value in item)
            ):
                raise ValueError("artifacts must contain non-empty string pairs.")
            keys.append(item[0])
        if len(keys) != len(set(keys)):
            raise ValueError("artifact keys must be unique.")
        object.__setattr__(self, "artifacts", artifacts)


@dataclass(frozen=True)
class ProductionRunResult:
    """Immutable aggregate of the stages available after a production run."""

    brief: ProductionBriefV2
    workspace: ProductionWorkspace
    status: str
    dataset_result: DatasetProductionResult
    logo_result: LogoResolutionResult | None
    assembly_result: ProjectAssemblyResult
    preflight_result: ProductionPreflightResult
    render_result: ProductionRenderResult | None
    status_path: Path

    def __post_init__(self) -> None:
        from automation.logo_resolver import LogoResolutionResult
        from automation.production_preflight import ProductionPreflightResult
        from automation.project_assembler import ProjectAssemblyResult
        from automation.render_executor import ProductionRenderResult

        if not isinstance(self.brief, ProductionBriefV2):
            raise TypeError("brief must be ProductionBriefV2.")
        if not isinstance(self.workspace, ProductionWorkspace):
            raise TypeError("workspace must be ProductionWorkspace.")
        if self.status not in _RUN_RESULT_STATES:
            raise ValueError("Production run status is invalid.")
        if not isinstance(self.dataset_result, DatasetProductionResult):
            raise TypeError("dataset_result must be DatasetProductionResult.")
        if self.dataset_result.workspace != self.workspace:
            raise ValueError("dataset_result belongs to another workspace.")
        if self.logo_result is not None and (
            not isinstance(self.logo_result, LogoResolutionResult)
            or self.logo_result.workspace != self.workspace
        ):
            raise ValueError("logo_result is invalid or belongs to another workspace.")
        if (
            not isinstance(self.assembly_result, ProjectAssemblyResult)
            or self.assembly_result.workspace != self.workspace
        ):
            raise ValueError("assembly_result is invalid or belongs to another workspace.")
        if (
            not isinstance(self.preflight_result, ProductionPreflightResult)
            or self.preflight_result.workspace != self.workspace
        ):
            raise ValueError("preflight_result is invalid or belongs to another workspace.")
        if self.status == "blocked":
            if self.preflight_result.status != "blocked" or self.render_result is not None:
                raise ValueError("Blocked runs require blocked preflight and no render.")
        elif self.status == "preflight_ready":
            if self.preflight_result.status != "ready" or self.render_result is not None:
                raise ValueError("Preflight-ready runs require ready preflight and no render.")
        else:
            if (
                not isinstance(self.render_result, ProductionRenderResult)
                or self.render_result.workspace != self.workspace
                or self.render_result.status != self.status
            ):
                raise ValueError("Final run status must match its render result.")
        status_path = Path(self.status_path).resolve(strict=False)
        if status_path != self.workspace.status_path:
            raise ValueError("status_path must be the canonical workspace status.")
        object.__setattr__(self, "status_path", status_path)


@dataclass(frozen=True)
class _ProductionRunPlan:
    brief: ProductionBriefV2
    project_root: Path
    workspace_root: Path
    source_root: Path
    progress_callback: Callable[[ProductionRunProgress], None] | None
    cancel_requested: Callable[[], bool] | None


@dataclass(frozen=True)
class ProductionOrchestrator:
    """Orchestrate dataset-only or explicitly requested complete production."""

    registry: DatasetBuilderRegistry
    logo_resolver_component: object | None = None
    project_assembler_component: object | None = None
    preflight_runner_component: object | None = None
    render_executor_factory: Callable[..., object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.registry, DatasetBuilderRegistry):
            raise TypeError("registry must be a DatasetBuilderRegistry.")
        component_methods = (
            ("logo_resolver_component", "resolve"),
            ("project_assembler_component", "assemble"),
            ("preflight_runner_component", "run"),
        )
        for field_name, method_name in component_methods:
            component = getattr(self, field_name)
            if component is not None and not callable(
                getattr(component, method_name, None)
            ):
                raise TypeError(f"{field_name} must expose {method_name}().")
        if self.render_executor_factory is not None and not callable(
            self.render_executor_factory
        ):
            raise TypeError("render_executor_factory must be callable or None.")

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

    def run_production(
        self,
        brief: ProductionBriefV2,
        *,
        project_root_dir: Path,
        workspace_root_dir: Path,
        source_root_dir: Path,
        progress_callback: Callable[[ProductionRunProgress], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> ProductionRunResult:
        job_id = brief.job_id if isinstance(brief, ProductionBrief) else "<invalid>"
        try:
            plan = self._validate_production_inputs(
                brief,
                project_root_dir=project_root_dir,
                workspace_root_dir=workspace_root_dir,
                source_root_dir=source_root_dir,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        except Exception as exc:
            raise self._error(
                job_id,
                "preflight",
                "validating complete production inputs",
            ) from exc

        try:
            self._emit_progress(
                plan.progress_callback,
                self._progress_event(
                    state="dataset_running",
                    stage="dataset",
                    message="Building and validating dataset.",
                    progress=0.02,
                ),
            )
        except Exception as exc:
            raise self._error(
                plan.brief.job_id,
                "dataset",
                "reporting dataset production progress",
            ) from exc
        dataset_result = self.prepare_dataset(
            plan.brief,
            workspace_root_dir=plan.workspace_root,
            source_root_dir=plan.source_root,
        )
        workspace = dataset_result.workspace
        phase = "dataset"
        logo_result = None
        assembly_result = None
        preflight_result = None
        render_result = None

        try:
            self._emit_progress(
                plan.progress_callback,
                self._progress_from_status(
                    self._ready_status(plan.brief.job_id),
                    progress=0.25,
                ),
            )

            phase = "assets"
            if (
                plan.brief.assets.primary_logo_dir is not None
                or plan.brief.assets.secondary_logo_dir is not None
            ):
                logo_result = self._logo_resolver().resolve(
                    dataset_csv=dataset_result.build_result.csv_path,
                    category_column=dataset_result.build_result.category_column,
                    workspace=workspace,
                    primary_logo_dir=plan.brief.assets.primary_logo_dir,
                    secondary_logo_dir=plan.brief.assets.secondary_logo_dir,
                    missing_policy=plan.brief.assets.missing_policy,
                )
                assets_message = "Local logo assets resolved."
            else:
                assets_message = "Local logo stage skipped; no directories configured."
            artifacts = self._artifact_items(
                workspace,
                dataset_result=dataset_result,
                logo_result=logo_result,
            )
            self._replace_pipeline_status(
                workspace,
                callback=plan.progress_callback,
                state="assets_ready",
                stage="assets",
                message=assets_message,
                artifacts=artifacts,
                progress=0.38,
            )

            phase = "project"
            from automation.project_assembler import ProjectAssemblyOptions

            assembly_result = self._project_assembler().assemble(
                dataset_result=dataset_result,
                template_project_path=plan.brief.project.template_path,
                project_root_dir=plan.project_root,
                options=ProjectAssemblyOptions(
                    project_name=plan.brief.project.name,
                    title=plan.brief.project.title,
                    source_label=plan.brief.project.source_label,
                ),
                logo_result=logo_result,
            )
            artifacts = self._artifact_items(
                workspace,
                dataset_result=dataset_result,
                logo_result=logo_result,
                assembly_result=assembly_result,
            )
            self._replace_pipeline_status(
                workspace,
                callback=plan.progress_callback,
                state="project_ready",
                stage="project",
                message="Production project assembled and verified.",
                artifacts=artifacts,
                progress=0.52,
            )

            phase = "preflight"
            preflight_result = self._preflight_runner().run(
                assembly_result=assembly_result,
                project_root_dir=plan.project_root,
            )
            artifacts = self._artifact_items(
                workspace,
                dataset_result=dataset_result,
                logo_result=logo_result,
                assembly_result=assembly_result,
                preflight_result=preflight_result,
            )
            if preflight_result.status == "blocked":
                self._replace_pipeline_status(
                    workspace,
                    callback=plan.progress_callback,
                    state="blocked",
                    stage="preflight",
                    message="Production preflight blocked the render.",
                    artifacts=artifacts,
                    progress=1.0,
                )
                return ProductionRunResult(
                    brief=plan.brief,
                    workspace=workspace,
                    status="blocked",
                    dataset_result=dataset_result,
                    logo_result=logo_result,
                    assembly_result=assembly_result,
                    preflight_result=preflight_result,
                    render_result=None,
                    status_path=workspace.status_path,
                )

            self._replace_pipeline_status(
                workspace,
                callback=plan.progress_callback,
                state="preflight_ready",
                stage="preflight",
                message="Production preflight passed.",
                artifacts=artifacts,
                progress=0.68 if plan.brief.render.enabled else 1.0,
            )
            if not plan.brief.render.enabled:
                return ProductionRunResult(
                    brief=plan.brief,
                    workspace=workspace,
                    status="preflight_ready",
                    dataset_result=dataset_result,
                    logo_result=logo_result,
                    assembly_result=assembly_result,
                    preflight_result=preflight_result,
                    render_result=None,
                    status_path=workspace.status_path,
                )

            phase = "render"
            self._replace_pipeline_status(
                workspace,
                callback=plan.progress_callback,
                state="rendering",
                stage="render",
                message="Rendering production video.",
                artifacts=artifacts,
                progress=0.7,
            )
            render_callback = self._render_progress_callback(
                plan.progress_callback,
                artifacts=artifacts,
            )
            executor = self._render_executor_factory()(
                progress_callback=render_callback,
                cancel_requested=plan.cancel_requested,
            )
            if not callable(getattr(executor, "run", None)):
                raise TypeError("render_executor_factory must return an executor with run().")
            render_result = executor.run(
                assembly_result=assembly_result,
                preflight_result=preflight_result,
                project_root_dir=plan.project_root,
            )
            final_state = render_result.status
            if final_state not in ("completed", "canceled"):
                raise ValueError("Production render returned an unsupported final status.")
            artifacts = self._artifact_items(
                workspace,
                dataset_result=dataset_result,
                logo_result=logo_result,
                assembly_result=assembly_result,
                preflight_result=preflight_result,
                render_result=render_result,
            )
            final_message = (
                "Production video completed."
                if final_state == "completed"
                else "Production render canceled."
            )
            self._replace_pipeline_status(
                workspace,
                callback=plan.progress_callback,
                state=final_state,
                stage="render",
                message=final_message,
                artifacts=artifacts,
                progress=1.0,
            )
            return ProductionRunResult(
                brief=plan.brief,
                workspace=workspace,
                status=final_state,
                dataset_result=dataset_result,
                logo_result=logo_result,
                assembly_result=assembly_result,
                preflight_result=preflight_result,
                render_result=render_result,
                status_path=workspace.status_path,
            )
        except Exception as exc:
            self._record_pipeline_failed_status_best_effort(
                workspace,
                job_id=plan.brief.job_id,
                phase=phase,
                original_error=exc,
                callback=plan.progress_callback,
                dataset_result=dataset_result,
                logo_result=logo_result,
                assembly_result=assembly_result,
                preflight_result=preflight_result,
                render_result=render_result,
            )
            raise self._error(
                plan.brief.job_id,
                phase,
                self._operation_for_pipeline_phase(phase),
            ) from exc

    def _validate_production_inputs(
        self,
        brief: ProductionBriefV2,
        *,
        project_root_dir: Path,
        workspace_root_dir: Path,
        source_root_dir: Path,
        progress_callback: Callable[[ProductionRunProgress], None] | None,
        cancel_requested: Callable[[], bool] | None,
    ) -> _ProductionRunPlan:
        if not isinstance(brief, ProductionBriefV2) or brief.schema_version != 2:
            raise TypeError("run_production() requires a validated ProductionBriefV2.")
        project_root = self._resolved_directory(
            project_root_dir,
            field_name="project_root_dir",
        )
        source_root = self._resolved_directory(
            source_root_dir,
            field_name="source_root_dir",
        )
        workspace_root = self._resolved_output_root(
            workspace_root_dir,
            project_root=project_root,
        )
        if not brief.dataset.source_csv.is_relative_to(source_root):
            raise ValueError("Brief dataset source must remain inside source_root_dir.")
        project_paths = [brief.project.template_path]
        if brief.assets.primary_logo_dir is not None:
            project_paths.append(brief.assets.primary_logo_dir)
        if brief.assets.secondary_logo_dir is not None:
            project_paths.append(brief.assets.secondary_logo_dir)
        if any(not path.is_relative_to(project_root) for path in project_paths):
            raise ValueError("Brief project and asset paths must remain in project_root_dir.")
        if progress_callback is not None and not callable(progress_callback):
            raise TypeError("progress_callback must be callable or None.")
        if cancel_requested is not None and not callable(cancel_requested):
            raise TypeError("cancel_requested must be callable or None.")
        return _ProductionRunPlan(
            brief=brief,
            project_root=project_root,
            workspace_root=workspace_root,
            source_root=source_root,
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
        )

    @staticmethod
    def _resolved_directory(path: Path, *, field_name: str) -> Path:
        if not isinstance(path, Path):
            raise TypeError(f"{field_name} must be a pathlib.Path.")
        if not path.is_absolute():
            raise ValueError(f"{field_name} must be absolute and resolved.")
        resolved = path.resolve(strict=True)
        if resolved != path or not resolved.is_dir():
            raise ValueError(f"{field_name} must be an existing resolved directory.")
        return resolved

    @staticmethod
    def _resolved_output_root(path: Path, *, project_root: Path) -> Path:
        if not isinstance(path, Path):
            raise TypeError("workspace_root_dir must be a pathlib.Path.")
        if not path.is_absolute():
            raise ValueError("workspace_root_dir must be absolute and resolved.")
        resolved = path.resolve(strict=False)
        if resolved != path or not resolved.is_relative_to(project_root):
            raise ValueError("workspace_root_dir must remain inside project_root_dir.")
        if resolved.exists() and not resolved.is_dir():
            raise NotADirectoryError("workspace_root_dir must be a directory.")
        return resolved

    def _logo_resolver(self) -> object:
        if self.logo_resolver_component is not None:
            return self.logo_resolver_component
        from automation.logo_resolver import LocalLogoResolver

        return LocalLogoResolver()

    def _project_assembler(self) -> object:
        if self.project_assembler_component is not None:
            return self.project_assembler_component
        from automation.project_assembler import ProductionProjectAssembler

        return ProductionProjectAssembler()

    def _preflight_runner(self) -> object:
        if self.preflight_runner_component is not None:
            return self.preflight_runner_component
        from automation.production_preflight import ProductionPreflightRunner

        return ProductionPreflightRunner()

    def _render_executor_factory(self) -> Callable[..., object]:
        if self.render_executor_factory is not None:
            return self.render_executor_factory
        from automation.render_executor import ProductionRenderExecutor

        return ProductionRenderExecutor

    @staticmethod
    def _progress_event(
        *,
        state: str,
        stage: str,
        message: str,
        progress: float,
        current: int = 0,
        total: int = 0,
        artifacts: tuple[tuple[str, str], ...] = (),
    ) -> ProductionRunProgress:
        return ProductionRunProgress(
            state=state,
            stage=stage,
            message=message,
            progress=progress,
            current=current,
            total=total,
            artifacts=artifacts,
        )

    @staticmethod
    def _emit_progress(
        callback: Callable[[ProductionRunProgress], None] | None,
        progress: ProductionRunProgress,
    ) -> None:
        if callback is not None:
            callback(progress)

    @staticmethod
    def _progress_from_status(data: dict, *, progress: float) -> ProductionRunProgress:
        artifacts = data.get("artifacts", {})
        if not isinstance(artifacts, dict):
            raise TypeError("Production status artifacts must be a dictionary.")
        return ProductionRunProgress(
            state=data["state"],
            stage=data["stage"],
            message=data["message"],
            progress=progress,
            artifacts=tuple(artifacts.items()),
        )

    def _replace_pipeline_status(
        self,
        workspace: ProductionWorkspace,
        *,
        callback: Callable[[ProductionRunProgress], None] | None,
        state: str,
        stage: str,
        message: str,
        artifacts: tuple[tuple[str, str], ...],
        progress: float,
    ) -> None:
        data = self._pipeline_status(
            job_id=workspace.job_id,
            state=state,
            stage=stage,
            message=message,
            artifacts=artifacts,
        )
        workspace.replace_status(data)
        self._emit_progress(
            callback,
            self._progress_from_status(data, progress=progress),
        )

    @staticmethod
    def _pipeline_status(
        *,
        job_id: str,
        state: str,
        stage: str,
        message: str,
        artifacts: tuple[tuple[str, str], ...],
    ) -> dict:
        data = {
            "production_status_schema_version": PRODUCTION_STATUS_SCHEMA_VERSION,
            "job_id": job_id,
            "state": state,
            "stage": stage,
            "message": message,
        }
        if artifacts:
            data["artifacts"] = dict(artifacts)
        return data

    @staticmethod
    def _artifact_items(
        workspace: ProductionWorkspace,
        *,
        dataset_result: DatasetProductionResult,
        logo_result: object | None = None,
        assembly_result: object | None = None,
        preflight_result: object | None = None,
        render_result: object | None = None,
    ) -> tuple[tuple[str, str], ...]:
        paths = [
            ("dataset", dataset_result.build_result.csv_path),
            ("dataset_manifest", dataset_result.dataset_manifest_path),
        ]
        if logo_result is not None:
            paths.append(("logo_manifest", logo_result.manifest_path))
        if assembly_result is not None:
            paths.extend(
                (
                    ("project", assembly_result.project_path),
                    ("project_manifest", assembly_result.manifest_path),
                )
            )
        if preflight_result is not None:
            paths.append(("preflight_manifest", preflight_result.manifest_path))
        if render_result is not None:
            if render_result.status == "completed":
                paths.append(("video", render_result.video_path))
            paths.append(("render_manifest", render_result.manifest_path))

        artifacts = []
        for key, path in paths:
            resolved = Path(path).resolve(strict=False)
            if not resolved.is_relative_to(workspace.root_path):
                raise ValueError(f"Artifact {key!r} escapes its production workspace.")
            artifacts.append((key, resolved.relative_to(workspace.root_path).as_posix()))
        return tuple(artifacts)

    @staticmethod
    def _render_progress_callback(
        callback: Callable[[ProductionRunProgress], None] | None,
        *,
        artifacts: tuple[tuple[str, str], ...],
    ) -> Callable[[object], None] | None:
        if callback is None:
            return None

        def report(progress: object) -> None:
            worker_progress = float(progress.progress)
            callback(
                ProductionRunProgress(
                    state="rendering",
                    stage=str(progress.stage),
                    message=str(progress.message),
                    progress=min(0.99, 0.7 + (0.29 * worker_progress)),
                    current=int(progress.current),
                    total=int(progress.total),
                    artifacts=artifacts,
                )
            )

        return report

    @staticmethod
    def _record_pipeline_failed_status_best_effort(
        workspace: ProductionWorkspace,
        *,
        job_id: str,
        phase: str,
        original_error: Exception,
        callback: Callable[[ProductionRunProgress], None] | None,
        dataset_result: DatasetProductionResult,
        logo_result: object | None,
        assembly_result: object | None,
        preflight_result: object | None,
        render_result: object | None,
    ) -> None:
        try:
            artifacts = ProductionOrchestrator._artifact_items(
                workspace,
                dataset_result=dataset_result,
                logo_result=logo_result,
                assembly_result=assembly_result,
                preflight_result=preflight_result,
                render_result=render_result,
            )
        except Exception as artifact_error:
            artifacts = ()
            original_error.add_note(
                "Collecting failure artifacts also failed: "
                f"{type(artifact_error).__name__}."
            )
        failed_status = ProductionOrchestrator._pipeline_status(
            job_id=job_id,
            state="failed",
            stage=phase,
            message="Production pipeline failed.",
            artifacts=artifacts,
        )
        failed_status["error"] = {
            "type": type(original_error).__name__,
            "phase": phase,
        }
        try:
            workspace.replace_status(failed_status)
        except Exception as status_error:
            original_error.add_note(
                "Writing the failed production status also failed: "
                f"{type(status_error).__name__}."
            )
            return
        try:
            ProductionOrchestrator._emit_progress(
                callback,
                ProductionOrchestrator._progress_from_status(
                    failed_status,
                    progress=1.0,
                ),
            )
        except Exception as callback_error:
            original_error.add_note(
                "Reporting failed production progress also failed: "
                f"{type(callback_error).__name__}."
            )

    @staticmethod
    def _operation_for_pipeline_phase(phase: str) -> str:
        return {
            "dataset": "finishing the dataset stage",
            "assets": "resolving local logo assets",
            "project": "assembling the production project",
            "preflight": "running production preflight",
            "render": "executing the isolated production render",
        }[phase]

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
            "state": "dataset_running",
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
