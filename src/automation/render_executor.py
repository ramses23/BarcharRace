from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from time import sleep

from automation.project_assembler import (
    PROJECT_ASSEMBLY_MANIFEST_SCHEMA_VERSION,
    ProjectAssemblyResult,
)
from automation.production_preflight import (
    PRODUCTION_PREFLIGHT_MANIFEST_SCHEMA_VERSION,
    ProductionPreflightResult,
)
from automation.workspace import ProductionWorkspace
from config.project_file_loader import load_project_file
from pipeline.render_job import RenderProfile, RenderResult
from ui.render_controller import render_result_from_status, start_background_render


PRODUCTION_RENDER_MANIFEST_SCHEMA_VERSION = 1
_TERMINAL_STATES = frozenset(("completed", "failed", "canceled"))
_RESULT_STATES = frozenset(("completed", "canceled"))
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)(?:^|\s)[a-z]:[\\/]")
_PERSONAL_POSIX_PATH = re.compile(r"(?:^|\s)/(?:home|users)/", re.IGNORECASE)


class ProductionRenderError(RuntimeError):
    """Raised when an isolated production render cannot complete safely."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        worker_state: str | None = None,
        worker_message: str | None = None,
        worker_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.worker_state = worker_state
        self.worker_message = worker_message
        self.worker_error = worker_error


@dataclass(frozen=True)
class ProductionRenderProgress:
    """Immutable progress snapshot adapted from a background render status."""

    state: str
    stage: str
    message: str
    progress: float
    current: int
    total: int

    def __post_init__(self) -> None:
        for field_name in ("state", "stage", "message"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")
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


@dataclass(frozen=True)
class ProductionRenderResult:
    """Deeply immutable record of one isolated production render."""

    workspace: ProductionWorkspace
    project_path: Path
    video_path: Path
    manifest_path: Path
    status: str
    video_sha256: str | None
    video_size_bytes: int | None
    frame_count: int | None
    transitions_rendered: int | None
    fps: int | None
    duration_seconds: float | None
    profile: RenderProfile | None
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, ProductionWorkspace):
            raise TypeError("workspace must be a ProductionWorkspace.")
        expected_paths = {
            "project_path": self.workspace.project_json_path,
            "video_path": self.workspace.video_path,
            "manifest_path": self.workspace.production_render_manifest_path,
        }
        for field_name, expected in expected_paths.items():
            path = Path(getattr(self, field_name)).resolve(strict=False)
            if path != expected:
                raise ValueError(f"{field_name} must use its canonical workspace path.")
            object.__setattr__(self, field_name, path)

        if self.status not in _RESULT_STATES:
            raise ValueError("status must be 'completed' or 'canceled'.")

        warnings = tuple(self.warnings)
        if any(not isinstance(warning, str) for warning in warnings):
            raise TypeError("warnings must contain only strings.")
        object.__setattr__(self, "warnings", warnings)

        if self.status == "canceled":
            optional_values = (
                self.video_sha256,
                self.video_size_bytes,
                self.frame_count,
                self.transitions_rendered,
                self.fps,
                self.duration_seconds,
                self.profile,
            )
            if any(value is not None for value in optional_values):
                raise ValueError("Canceled renders must not expose video metrics.")
            return

        if (
            not isinstance(self.video_sha256, str)
            or len(self.video_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.video_sha256)
        ):
            raise ValueError("video_sha256 must be a lowercase SHA-256 digest.")
        for field_name in (
            "video_size_bytes",
            "frame_count",
            "transitions_rendered",
            "fps",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer.")
        if self.fps == 0:
            raise ValueError("fps must be greater than zero.")
        if (
            isinstance(self.duration_seconds, bool)
            or not isinstance(self.duration_seconds, (int, float))
            or not math.isfinite(float(self.duration_seconds))
            or self.duration_seconds < 0
        ):
            raise ValueError("duration_seconds must be a finite non-negative number.")
        object.__setattr__(self, "duration_seconds", float(self.duration_seconds))
        if not isinstance(self.profile, RenderProfile):
            raise TypeError("profile must be a RenderProfile for completed renders.")


@dataclass(frozen=True)
class _RenderPlan:
    project_root: Path
    workspace: ProductionWorkspace
    project_path: Path
    project_sha256: str
    fps: int
    warnings: tuple[str, ...]
    production_status_bytes: bytes


@dataclass(frozen=True)
class ProductionRenderExecutor:
    """Execute one production render through the existing controller and worker."""

    poll_interval_seconds: float = 0.05
    progress_callback: Callable[[ProductionRenderProgress], None] | None = None
    cancel_requested: Callable[[], bool] | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.poll_interval_seconds, bool)
            or not isinstance(self.poll_interval_seconds, (int, float))
            or not math.isfinite(float(self.poll_interval_seconds))
            or self.poll_interval_seconds < 0
        ):
            raise ValueError("poll_interval_seconds must be finite and non-negative.")
        object.__setattr__(
            self,
            "poll_interval_seconds",
            float(self.poll_interval_seconds),
        )
        for field_name in ("progress_callback", "cancel_requested"):
            value = getattr(self, field_name)
            if value is not None and not callable(value):
                raise TypeError(f"{field_name} must be callable or None.")

    def run(
        self,
        *,
        assembly_result: ProjectAssemblyResult,
        preflight_result: ProductionPreflightResult,
        project_root_dir: Path,
    ) -> ProductionRenderResult:
        try:
            plan = self._validate_inputs(
                assembly_result=assembly_result,
                preflight_result=preflight_result,
                project_root_dir=project_root_dir,
            )
        except Exception as exc:
            raise self._error("validation", "validating production render inputs") from exc

        try:
            background_render = start_background_render(
                plan.project_path,
                root_dir=plan.project_root,
            )
        except Exception as exc:
            raise self._error("launch", "starting the isolated render worker") from exc

        try:
            status = self._wait_for_terminal_status(background_render)
        except Exception as exc:
            self._cancel_after_monitoring_error(background_render, original_error=exc)
            raise self._error("monitoring", "monitoring the isolated render worker") from exc

        state = status.get("state")
        if state == "failed":
            worker_error = self._optional_status_text(status, "error")
            worker_message = self._optional_status_text(status, "message")
            try:
                self._verify_failed_render_cleanup(status, plan=plan)
            except Exception as exc:
                raise ProductionRenderError(
                    "Production render failed during 'worker' and its cleanup "
                    "contract could not be verified.",
                    stage="worker",
                    worker_state="failed",
                    worker_message=worker_message,
                    worker_error=worker_error,
                ) from exc
            cause = RuntimeError(worker_error or "The render worker reported failure.")
            raise ProductionRenderError(
                "Production render failed during 'worker' while the isolated worker ran.",
                stage="worker",
                worker_state="failed",
                worker_message=worker_message,
                worker_error=worker_error,
            ) from cause

        if state == "canceled":
            try:
                self._verify_canceled_render(status, plan=plan)
                result = self._canceled_result(plan)
                manifest_data = self._manifest_data(
                    result,
                    preflight_result=preflight_result,
                    plan=plan,
                )
            except Exception as exc:
                raise self._error("adaptation", "adapting a canceled render") from exc
            return self._publish_manifest(result, manifest_data, plan=plan)

        try:
            render_result = render_result_from_status(status)
            result = self._completed_result(
                render_result,
                status=status,
                plan=plan,
            )
            manifest_data = self._manifest_data(
                result,
                preflight_result=preflight_result,
                plan=plan,
            )
        except Exception as exc:
            raise self._error("adaptation", "adapting the completed render result") from exc
        return self._publish_manifest(result, manifest_data, plan=plan)

    def _validate_inputs(
        self,
        *,
        assembly_result: ProjectAssemblyResult,
        preflight_result: ProductionPreflightResult,
        project_root_dir: Path,
    ) -> _RenderPlan:
        if not isinstance(assembly_result, ProjectAssemblyResult):
            raise TypeError("assembly_result must be ProjectAssemblyResult.")
        if not isinstance(preflight_result, ProductionPreflightResult):
            raise TypeError("preflight_result must be ProductionPreflightResult.")
        project_root = self._resolved_directory(
            project_root_dir,
            field_name="project_root_dir",
        )
        workspace = assembly_result.workspace
        if preflight_result.workspace != workspace:
            raise ValueError("Assembly and preflight must belong to the same workspace.")
        if preflight_result.status != "ready":
            raise ValueError("Production preflight status must be exactly 'ready'.")
        if not workspace.root_path.is_dir() or not workspace.root_path.is_relative_to(
            project_root
        ):
            raise ValueError("Production workspace must remain inside project_root_dir.")

        expected_paths = {
            "assembly project": (
                assembly_result.project_path,
                workspace.project_json_path,
            ),
            "preflight project": (
                preflight_result.project_path,
                workspace.project_json_path,
            ),
            "assembly manifest": (
                assembly_result.manifest_path,
                workspace.project_assembly_manifest_path,
            ),
            "preflight manifest": (
                preflight_result.manifest_path,
                workspace.production_preflight_manifest_path,
            ),
            "assembly output": (
                assembly_result.output_path,
                workspace.video_path,
            ),
            "preflight output": (
                preflight_result.output_path,
                workspace.video_path,
            ),
        }
        for label, (declared, canonical) in expected_paths.items():
            path = Path(declared).resolve(strict=False)
            if path != canonical or not path.is_relative_to(project_root):
                raise ValueError(f"{label.capitalize()} path is not canonical and contained.")

        required_files = {
            "assembled project": workspace.project_json_path,
            "project assembly manifest": workspace.project_assembly_manifest_path,
            "production preflight manifest": workspace.production_preflight_manifest_path,
        }
        for label, path in required_files.items():
            if not path.is_file():
                raise ValueError(f"{label.capitalize()} does not exist as a regular file.")
        if workspace.production_render_manifest_path.exists():
            raise FileExistsError("Production render manifest already exists.")
        if workspace.video_path.exists():
            raise FileExistsError("Production video output already exists.")
        self._require_no_partial_output(workspace)

        project_size = workspace.project_json_path.stat().st_size
        project_sha256 = self._sha256(workspace.project_json_path)
        if project_size != assembly_result.project_size_bytes:
            raise ValueError("Project size does not match ProjectAssemblyResult.")
        if project_sha256 != assembly_result.project_sha256:
            raise ValueError("Project SHA-256 does not match ProjectAssemblyResult.")

        assembly_manifest = self._read_json_object(
            workspace.project_assembly_manifest_path,
            "project assembly manifest",
        )
        self._validate_assembly_manifest(
            assembly_manifest,
            assembly_result=assembly_result,
            project_root=project_root,
            project_sha256=project_sha256,
            project_size=project_size,
        )
        preflight_manifest = self._read_json_object(
            workspace.production_preflight_manifest_path,
            "production preflight manifest",
        )
        self._validate_preflight_manifest(
            preflight_manifest,
            preflight_result=preflight_result,
            project_root=project_root,
            project_sha256=project_sha256,
        )

        preset = load_project_file(workspace.project_json_path)
        output_path = self._resolve_reference(
            preset.chart_config.output_file,
            project_root,
            field_name="project output path",
        )
        if output_path != workspace.video_path:
            raise ValueError("Configured project output does not match workspace.video_path.")
        fps = preset.chart_config.fps
        if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
            raise ValueError("Configured project FPS must be a positive integer.")

        production_status_bytes = workspace.status_path.read_bytes()
        warnings = self._manifest_warnings(
            preflight_manifest,
            project_root=project_root,
        )
        return _RenderPlan(
            project_root=project_root,
            workspace=workspace,
            project_path=workspace.project_json_path,
            project_sha256=project_sha256,
            fps=fps,
            warnings=warnings,
            production_status_bytes=production_status_bytes,
        )

    def _wait_for_terminal_status(self, background_render: object) -> dict:
        while True:
            status_method = getattr(background_render, "status", None)
            if not callable(status_method):
                raise TypeError("start_background_render() returned an invalid handle.")
            status = status_method()
            if not isinstance(status, dict):
                raise TypeError("BackgroundRender.status() must return a dictionary.")
            progress = self._adapt_progress(status)
            if self.progress_callback is not None:
                self.progress_callback(progress)

            state = progress.state
            if state in _TERMINAL_STATES:
                is_running = getattr(background_render, "is_running", None)
                if not callable(is_running) or not is_running():
                    return status
            elif self.cancel_requested is not None and self.cancel_requested():
                cancel = getattr(background_render, "cancel", None)
                if not callable(cancel):
                    raise TypeError("BackgroundRender does not expose cancel().")
                canceled_status = cancel()
                if not isinstance(canceled_status, dict):
                    raise TypeError("BackgroundRender.cancel() must return a dictionary.")
                canceled_progress = self._adapt_progress(canceled_status)
                if canceled_progress.state != "canceled":
                    raise ValueError("BackgroundRender.cancel() did not report cancellation.")
                if self.progress_callback is not None:
                    self.progress_callback(canceled_progress)
                return canceled_status

            sleep(self.poll_interval_seconds)

    @staticmethod
    def _adapt_progress(status: dict) -> ProductionRenderProgress:
        state = status.get("state", "starting")
        stage = status.get("stage", "starting")
        message = status.get("message", "Waiting for render worker status.")
        if not all(isinstance(value, str) for value in (state, stage, message)):
            raise TypeError("Worker state, stage, and message must be strings.")
        progress = status.get("progress", 0.0)
        current = status.get("current", 0)
        total = status.get("total", 0)
        if isinstance(progress, bool) or not isinstance(progress, (int, float)):
            raise TypeError("Worker progress must be numeric.")
        if isinstance(current, bool) or not isinstance(current, int):
            raise TypeError("Worker current progress must be an integer.")
        if isinstance(total, bool) or not isinstance(total, int):
            raise TypeError("Worker total progress must be an integer.")
        return ProductionRenderProgress(
            state=state,
            stage=stage,
            message=message,
            progress=max(0.0, min(1.0, float(progress))),
            current=current,
            total=total,
        )

    def _completed_result(
        self,
        render_result: object,
        *,
        status: dict,
        plan: _RenderPlan,
    ) -> ProductionRenderResult:
        if not isinstance(render_result, RenderResult):
            raise TypeError("render_result_from_status() returned an invalid result.")
        if not isinstance(render_result.profile, RenderProfile):
            raise TypeError("Completed RenderResult contains an invalid profile.")
        output_path = Path(render_result.output_file)
        if not output_path.is_absolute():
            output_path = plan.project_root / output_path
        if output_path.resolve(strict=False) != plan.workspace.video_path:
            raise ValueError("RenderResult output does not match workspace.video_path.")
        if not plan.workspace.video_path.is_file():
            if plan.workspace.video_path.exists():
                raise ValueError("Completed production video is not a regular file.")
            raise FileNotFoundError("Completed production video does not exist.")
        self._require_no_partial_output(plan.workspace, status=status)
        self._require_unchanged_production_status(plan)

        video_size_bytes = plan.workspace.video_path.stat().st_size
        video_sha256 = self._sha256(plan.workspace.video_path)
        return ProductionRenderResult(
            workspace=plan.workspace,
            project_path=plan.project_path,
            video_path=plan.workspace.video_path,
            manifest_path=plan.workspace.production_render_manifest_path,
            status="completed",
            video_sha256=video_sha256,
            video_size_bytes=video_size_bytes,
            frame_count=render_result.frames_rendered,
            transitions_rendered=render_result.transitions_rendered,
            fps=plan.fps,
            duration_seconds=render_result.frames_rendered / plan.fps,
            profile=render_result.profile,
            warnings=plan.warnings,
        )

    def _canceled_result(self, plan: _RenderPlan) -> ProductionRenderResult:
        return ProductionRenderResult(
            workspace=plan.workspace,
            project_path=plan.project_path,
            video_path=plan.workspace.video_path,
            manifest_path=plan.workspace.production_render_manifest_path,
            status="canceled",
            video_sha256=None,
            video_size_bytes=None,
            frame_count=None,
            transitions_rendered=None,
            fps=None,
            duration_seconds=None,
            profile=None,
            warnings=plan.warnings,
        )

    def _publish_manifest(
        self,
        result: ProductionRenderResult,
        manifest_data: dict,
        *,
        plan: _RenderPlan,
    ) -> ProductionRenderResult:
        try:
            plan.workspace.publish_production_render_manifest(manifest_data)
        except Exception as exc:
            if self._published_manifest_matches(result.manifest_path, manifest_data):
                return result
            self._remove_partial_manifest(result.manifest_path, original_error=exc)
            raise self._error(
                "manifest",
                "publishing manifests/production_render.json",
            ) from exc
        return result

    @staticmethod
    def _manifest_data(
        result: ProductionRenderResult,
        *,
        preflight_result: ProductionPreflightResult,
        plan: _RenderPlan,
    ) -> dict:
        result_data: dict[str, object] = {"status": result.status}
        video_data = None
        if result.status == "completed":
            result_data.update(
                {
                    "frame_count": result.frame_count,
                    "transitions_rendered": result.transitions_rendered,
                    "fps": result.fps,
                    "duration_seconds": result.duration_seconds,
                }
            )
            video_data = {
                "path": result.video_path.relative_to(plan.project_root).as_posix(),
                "sha256": result.video_sha256,
                "size_bytes": result.video_size_bytes,
            }
        return {
            "production_render_manifest_schema_version": (
                PRODUCTION_RENDER_MANIFEST_SCHEMA_VERSION
            ),
            "project": {
                "path": result.project_path.relative_to(plan.project_root).as_posix(),
                "sha256": plan.project_sha256,
            },
            "preflight": {
                "path": preflight_result.manifest_path.relative_to(
                    plan.project_root
                ).as_posix(),
                "status": preflight_result.status,
            },
            "video": video_data,
            "result": result_data,
            "warnings": list(result.warnings),
        }

    @staticmethod
    def _validate_assembly_manifest(
        manifest: dict,
        *,
        assembly_result: ProjectAssemblyResult,
        project_root: Path,
        project_sha256: str,
        project_size: int,
    ) -> None:
        project = manifest.get("project")
        output = manifest.get("output")
        if (
            manifest.get("project_assembly_manifest_schema_version")
            != PROJECT_ASSEMBLY_MANIFEST_SCHEMA_VERSION
            or not isinstance(project, dict)
            or not isinstance(output, dict)
        ):
            raise ValueError("Project assembly manifest structure is invalid.")
        manifest_project_path = ProductionRenderExecutor._resolve_reference(
            project.get("path"),
            project_root,
            field_name="assembly project path",
        )
        manifest_output_path = ProductionRenderExecutor._resolve_reference(
            output.get("path"),
            project_root,
            field_name="assembly output path",
        )
        if (
            manifest_project_path != assembly_result.project_path
            or project.get("sha256") != project_sha256
            or project.get("size_bytes") != project_size
            or manifest_output_path != assembly_result.output_path
        ):
            raise ValueError("Project assembly manifest does not match its result.")

    @staticmethod
    def _validate_preflight_manifest(
        manifest: dict,
        *,
        preflight_result: ProductionPreflightResult,
        project_root: Path,
        project_sha256: str,
    ) -> None:
        project = manifest.get("project")
        render_output = manifest.get("render_output")
        if (
            manifest.get("production_preflight_manifest_schema_version")
            != PRODUCTION_PREFLIGHT_MANIFEST_SCHEMA_VERSION
            or not isinstance(project, dict)
            or not isinstance(render_output, dict)
        ):
            raise ValueError("Production preflight manifest structure is invalid.")
        manifest_project_path = ProductionRenderExecutor._resolve_reference(
            project.get("path"),
            project_root,
            field_name="preflight project path",
        )
        manifest_output_path = ProductionRenderExecutor._resolve_reference(
            render_output.get("path"),
            project_root,
            field_name="preflight output path",
        )
        if (
            manifest_project_path != preflight_result.project_path
            or project.get("sha256") != project_sha256
            or manifest_output_path != preflight_result.output_path
            or manifest.get("status") != "ready"
        ):
            raise ValueError("Production preflight manifest does not match its result.")

    @staticmethod
    def _manifest_warnings(manifest: dict, *, project_root: Path) -> tuple[str, ...]:
        warnings = manifest.get("warnings", [])
        if not isinstance(warnings, list):
            raise ValueError("Production preflight warnings must be a list.")
        values = []
        for warning in warnings:
            if not isinstance(warning, dict):
                raise ValueError("Production preflight warning entries must be objects.")
            key = warning.get("key")
            message = warning.get("message")
            if not isinstance(key, str) or not key or not isinstance(message, str):
                raise ValueError("Production preflight warning entry is invalid.")
            values.append(
                f"{key}: {ProductionRenderExecutor._sanitize_warning(message, project_root)}"
            )
        return tuple(sorted(values))

    @staticmethod
    def _sanitize_warning(message: str, project_root: Path) -> str:
        sanitized = message
        for variant in sorted(
            {str(project_root), project_root.as_posix()},
            key=len,
            reverse=True,
        ):
            sanitized = re.sub(
                re.escape(variant),
                "<project_root>",
                sanitized,
                flags=re.IGNORECASE,
            )
        if _WINDOWS_ABSOLUTE_PATH.search(sanitized) or _PERSONAL_POSIX_PATH.search(
            sanitized
        ):
            return "Details omitted because they contained an external path."
        return sanitized

    @staticmethod
    def _verify_failed_render_cleanup(status: dict, *, plan: _RenderPlan) -> None:
        if plan.workspace.video_path.exists():
            raise ValueError("Failed render unexpectedly produced the final MP4.")
        ProductionRenderExecutor._require_no_partial_output(
            plan.workspace,
            status=status,
        )
        ProductionRenderExecutor._require_unchanged_production_status(plan)

    @staticmethod
    def _verify_canceled_render(status: dict, *, plan: _RenderPlan) -> None:
        if plan.workspace.video_path.exists():
            raise ValueError("Canceled render unexpectedly produced the final MP4.")
        ProductionRenderExecutor._require_no_partial_output(
            plan.workspace,
            status=status,
        )
        ProductionRenderExecutor._require_unchanged_production_status(plan)

    @staticmethod
    def _require_no_partial_output(
        workspace: ProductionWorkspace,
        *,
        status: dict | None = None,
    ) -> None:
        pattern = (
            f".{workspace.video_path.stem}.*.partial{workspace.video_path.suffix}"
        )
        legacy_partial = workspace.video_path.with_name(
            f".{workspace.video_path.stem}.partial{workspace.video_path.suffix}"
        )
        partials = tuple(workspace.render_dir.glob(pattern))
        if legacy_partial.exists() and legacy_partial not in partials:
            partials = (*partials, legacy_partial)
        if status is not None:
            temporary_output = status.get("temporary_output")
            if isinstance(temporary_output, str) and temporary_output:
                status_partial = Path(temporary_output).resolve(strict=False)
                if status_partial.exists() and status_partial not in partials:
                    partials = (*partials, status_partial)
        if partials:
            raise FileExistsError("A production render partial output still exists.")

    @staticmethod
    def _require_unchanged_production_status(plan: _RenderPlan) -> None:
        if plan.workspace.status_path.read_bytes() != plan.production_status_bytes:
            raise ValueError("The general production status changed during render.")

    @staticmethod
    def _cancel_after_monitoring_error(
        background_render: object,
        *,
        original_error: Exception,
    ) -> None:
        cancel = getattr(background_render, "cancel", None)
        if not callable(cancel):
            return
        try:
            cancel()
        except Exception as cancel_error:
            original_error.add_note(
                "BackgroundRender.cancel() also failed: "
                f"{type(cancel_error).__name__}."
            )

    @staticmethod
    def _optional_status_text(status: dict, key: str) -> str | None:
        value = status.get(key)
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _published_manifest_matches(path: Path, expected: dict) -> bool:
        try:
            payload = path.read_bytes()
            if payload.startswith(b"\xef\xbb\xbf") or not payload.endswith(b"\n"):
                return False
            return json.loads(payload.decode("utf-8")) == expected
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False

    @staticmethod
    def _remove_partial_manifest(path: Path, *, original_error: Exception) -> None:
        if not path.exists():
            return
        try:
            if path.is_file():
                path.unlink()
        except Exception as cleanup_error:
            original_error.add_note(
                "Partial render manifest cleanup also failed: "
                f"{type(cleanup_error).__name__}."
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
    def _resolve_reference(value: object, root: Path, *, field_name: str) -> Path:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} must be a non-empty relative path.")
        pure_path = PurePosixPath(value)
        if (
            "\\" in value
            or ":" in value
            or pure_path.is_absolute()
            or pure_path.as_posix() != value
            or any(part in ("", ".", "..") for part in pure_path.parts)
        ):
            raise ValueError(f"{field_name} must be a portable relative POSIX path.")
        resolved = (root / pure_path).resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise ValueError(f"{field_name} escapes project_root_dir.")
        return resolved

    @staticmethod
    def _read_json_object(path: Path, label: str) -> dict:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{label.capitalize()} must contain a JSON object.")
        return data

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _error(stage: str, operation: str) -> ProductionRenderError:
        return ProductionRenderError(
            f"Production render failed during {stage!r} while {operation}.",
            stage=stage,
        )
