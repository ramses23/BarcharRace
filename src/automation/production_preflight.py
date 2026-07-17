from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from automation.project_assembler import (
    PROJECT_ASSEMBLY_MANIFEST_SCHEMA_VERSION,
    ProjectAssemblyResult,
)
from automation.workspace import ProductionWorkspace
from config.project_file_loader import load_project_file
from studio import render_preflight


PRODUCTION_PREFLIGHT_MANIFEST_SCHEMA_VERSION = 1
_RESULT_STATUSES = frozenset(("ready", "blocked"))
_ISSUE_LEVELS = frozenset(("error", "warning"))
_CHECK_LEVELS = frozenset(("ok", "error", "warning"))
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)(?:^|\s)[a-z]:[\\/]")
_PERSONAL_POSIX_PATH = re.compile(r"(?:^|\s)/(?:home|users)/", re.IGNORECASE)


class ProductionPreflightError(RuntimeError):
    """Raised when production preflight cannot execute or publish safely."""


@dataclass(frozen=True)
class ProductionPreflightIssue:
    """Immutable simple representation of one blocking error or warning."""

    key: str
    label: str
    level: str
    message: str

    def __post_init__(self) -> None:
        for field_name in ("key", "label", "message"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string.")
        if self.level not in _ISSUE_LEVELS:
            raise ValueError("level must be 'error' or 'warning'.")


@dataclass(frozen=True)
class ProductionPreflightResult:
    """Deeply immutable result of one production preflight execution."""

    workspace: ProductionWorkspace
    project_path: Path
    manifest_path: Path
    status: str
    errors: tuple[ProductionPreflightIssue, ...]
    warnings: tuple[ProductionPreflightIssue, ...]
    output_path: Path
    ffmpeg_available: bool
    error_count: int
    warning_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, ProductionWorkspace):
            raise TypeError("workspace must be a ProductionWorkspace.")
        expected_paths = {
            "project_path": self.workspace.project_json_path,
            "manifest_path": self.workspace.production_preflight_manifest_path,
            "output_path": self.workspace.video_path,
        }
        for field_name, expected in expected_paths.items():
            path = Path(getattr(self, field_name)).resolve(strict=False)
            if path != expected:
                raise ValueError(f"{field_name} must use its canonical workspace path.")
            object.__setattr__(self, field_name, path)

        if self.status not in _RESULT_STATUSES:
            raise ValueError("status must be 'ready' or 'blocked'.")
        if not isinstance(self.ffmpeg_available, bool):
            raise TypeError("ffmpeg_available must be boolean.")

        errors = tuple(self.errors)
        warnings = tuple(self.warnings)
        if any(
            not isinstance(issue, ProductionPreflightIssue)
            or issue.level != "error"
            for issue in errors
        ):
            raise ValueError("errors must contain only error issues.")
        if any(
            not isinstance(issue, ProductionPreflightIssue)
            or issue.level != "warning"
            for issue in warnings
        ):
            raise ValueError("warnings must contain only warning issues.")
        object.__setattr__(self, "errors", errors)
        object.__setattr__(self, "warnings", warnings)

        if (
            isinstance(self.error_count, bool)
            or not isinstance(self.error_count, int)
            or self.error_count != len(errors)
        ):
            raise ValueError("error_count must equal the number of errors.")
        if (
            isinstance(self.warning_count, bool)
            or not isinstance(self.warning_count, int)
            or self.warning_count != len(warnings)
        ):
            raise ValueError("warning_count must equal the number of warnings.")
        if (self.status == "ready") != (not errors):
            raise ValueError("status must be ready exactly when there are no errors.")


@dataclass(frozen=True)
class _PreflightPlan:
    project_root: Path
    workspace: ProductionWorkspace
    project_path: Path
    output_path: Path
    project_sha256: str


@dataclass(frozen=True)
class ProductionPreflightRunner:
    """Run the existing render preflight without starting a render."""

    def run(
        self,
        *,
        assembly_result: ProjectAssemblyResult,
        project_root_dir: Path,
    ) -> ProductionPreflightResult:
        try:
            plan = self._validate_inputs(
                assembly_result=assembly_result,
                project_root_dir=project_root_dir,
            )
        except Exception as exc:
            raise self._error("validation", "validating production preflight inputs") from exc

        try:
            raw_result = render_preflight.run_render_preflight(
                plan.project_path,
                root_dir=plan.project_root,
            )
        except Exception as exc:
            raise self._error("preflight", "executing the existing render preflight") from exc

        try:
            result = self._adapt_result(raw_result, plan=plan)
            manifest_data = self._manifest_data(result, plan=plan)
        except Exception as exc:
            raise self._error("adaptation", "adapting the render preflight result") from exc

        try:
            plan.workspace.publish_production_preflight_manifest(manifest_data)
        except Exception as exc:
            if self._published_manifest_matches(
                plan.workspace.production_preflight_manifest_path,
                manifest_data,
            ):
                return result
            self._remove_partial_manifest(
                plan.workspace.production_preflight_manifest_path,
                original_error=exc,
            )
            raise self._error(
                "manifest",
                "publishing manifests/production_preflight.json",
            ) from exc
        return result

    def _validate_inputs(
        self,
        *,
        assembly_result: ProjectAssemblyResult,
        project_root_dir: Path,
    ) -> _PreflightPlan:
        if not isinstance(assembly_result, ProjectAssemblyResult):
            raise TypeError("assembly_result must be ProjectAssemblyResult.")
        project_root = self._resolved_directory(
            project_root_dir,
            field_name="project_root_dir",
        )
        workspace = assembly_result.workspace
        if not workspace.root_path.is_dir() or not workspace.root_path.is_relative_to(
            project_root
        ):
            raise ValueError("Assembly workspace must remain inside project_root_dir.")

        expected_paths = {
            "project": (assembly_result.project_path, workspace.project_json_path),
            "assembly manifest": (
                assembly_result.manifest_path,
                workspace.project_assembly_manifest_path,
            ),
            "dataset": (assembly_result.dataset_path, workspace.dataset_csv_path),
            "render output": (assembly_result.output_path, workspace.video_path),
        }
        for label, (declared, canonical) in expected_paths.items():
            declared_path = Path(declared).resolve(strict=False)
            if declared_path != canonical or not declared_path.is_relative_to(project_root):
                raise ValueError(f"Assembly {label} path is not canonical and contained.")

        if workspace.production_preflight_manifest_path.exists():
            raise FileExistsError("Production preflight manifest already exists.")
        if not assembly_result.project_path.is_file():
            raise ValueError("Assembled project does not exist as a regular file.")
        if not assembly_result.manifest_path.is_file():
            raise ValueError("Project assembly manifest does not exist.")
        if not assembly_result.dataset_path.is_file():
            raise ValueError("Assembled dataset does not exist as a regular file.")

        project_size = assembly_result.project_path.stat().st_size
        project_sha256 = self._sha256(assembly_result.project_path)
        if project_size != assembly_result.project_size_bytes:
            raise ValueError("Project size does not match ProjectAssemblyResult.")
        if project_sha256 != assembly_result.project_sha256:
            raise ValueError("Project SHA-256 does not match ProjectAssemblyResult.")

        status = self._read_json_object(workspace.status_path, "workspace status")
        allowed_statuses = {
            ("dataset_ready", "dataset"),
            ("project_ready", "project"),
        }
        if (
            (status.get("state"), status.get("stage")) not in allowed_statuses
            or status.get("job_id") != workspace.job_id
        ):
            raise ValueError(
                "Workspace status must be dataset_ready or project_ready for this job."
            )

        assembly_manifest = self._read_json_object(
            assembly_result.manifest_path,
            "project assembly manifest",
        )
        self._validate_assembly_manifest(
            assembly_manifest,
            assembly_result=assembly_result,
            project_root=project_root,
        )
        preset = load_project_file(assembly_result.project_path)
        self._validate_project_references(
            preset,
            assembly_result=assembly_result,
            project_root=project_root,
        )
        return _PreflightPlan(
            project_root=project_root,
            workspace=workspace,
            project_path=assembly_result.project_path,
            output_path=assembly_result.output_path,
            project_sha256=project_sha256,
        )

    def _validate_assembly_manifest(
        self,
        manifest: dict,
        *,
        assembly_result: ProjectAssemblyResult,
        project_root: Path,
    ) -> None:
        project = manifest.get("project")
        dataset = manifest.get("dataset")
        output = manifest.get("output")
        logos = manifest.get("logos")
        if (
            manifest.get("project_assembly_manifest_schema_version")
            != PROJECT_ASSEMBLY_MANIFEST_SCHEMA_VERSION
            or not isinstance(project, dict)
            or not isinstance(dataset, dict)
            or not isinstance(output, dict)
            or not isinstance(logos, dict)
        ):
            raise ValueError("Project assembly manifest structure is invalid.")

        project_path = self._resolve_reference(
            project.get("path"),
            project_root,
            field_name="assembly project path",
        )
        dataset_path = self._resolve_reference(
            dataset.get("path"),
            project_root,
            field_name="assembly dataset path",
        )
        output_path = self._resolve_reference(
            output.get("path"),
            project_root,
            field_name="assembly output path",
        )
        if (
            project_path != assembly_result.project_path
            or project.get("sha256") != assembly_result.project_sha256
            or project.get("size_bytes") != assembly_result.project_size_bytes
            or dataset_path != assembly_result.dataset_path
            or output_path != assembly_result.output_path
            or logos.get("primary_count") != assembly_result.primary_logo_count
            or logos.get("secondary_count") != assembly_result.secondary_logo_count
        ):
            raise ValueError("Project assembly manifest does not match its result.")

        if dataset.get("size_bytes") != assembly_result.dataset_path.stat().st_size:
            raise ValueError("Dataset size does not match the assembly manifest.")
        if dataset.get("sha256") != self._sha256(assembly_result.dataset_path):
            raise ValueError("Dataset SHA-256 does not match the assembly manifest.")

        logo_manifest_reference = logos.get("manifest")
        if logo_manifest_reference is not None:
            logo_manifest = self._resolve_reference(
                logo_manifest_reference,
                project_root,
                field_name="logo manifest path",
            )
            if not logo_manifest.is_file():
                raise ValueError("Referenced logo resolution manifest does not exist.")

    def _validate_project_references(
        self,
        preset: object,
        *,
        assembly_result: ProjectAssemblyResult,
        project_root: Path,
    ) -> None:
        source = preset.data_source_config
        if source.source_type != "csv":
            raise ValueError("Assembled production project must use its CSV dataset.")
        dataset_path = self._resolve_reference(
            source.csv_path,
            project_root,
            field_name="project dataset path",
        )
        if dataset_path != assembly_result.dataset_path or not dataset_path.is_file():
            raise ValueError("Project dataset reference is missing or inconsistent.")

        output_path = self._resolve_reference(
            preset.chart_config.output_file,
            project_root,
            field_name="project output path",
        )
        if output_path != assembly_result.output_path:
            raise ValueError("Project output reference is inconsistent.")

        logo_paths = (
            *preset.dataset_config.category_logos.values(),
            *preset.dataset_config.category_secondary_logos.values(),
        )
        for value in logo_paths:
            logo_path = self._resolve_reference(
                value,
                project_root,
                field_name="project logo path",
            )
            if not logo_path.is_file():
                raise ValueError("A referenced project logo does not exist.")

    @staticmethod
    def _adapt_result(
        raw_result: object,
        *,
        plan: _PreflightPlan,
    ) -> ProductionPreflightResult:
        if not isinstance(raw_result, render_preflight.RenderPreflight):
            raise TypeError("run_render_preflight() returned an invalid result.")
        errors = []
        warnings = []
        ffmpeg_available = False
        for check in raw_result.checks:
            if not isinstance(check, render_preflight.PreflightCheck):
                raise TypeError("Render preflight returned an invalid check.")
            if check.level not in _CHECK_LEVELS:
                raise ValueError("Render preflight returned an unknown check level.")
            if check.key == "ffmpeg" and check.level == "ok":
                ffmpeg_available = True
            if check.level not in _ISSUE_LEVELS:
                continue
            issue = ProductionPreflightIssue(
                key=check.key,
                label=check.label,
                level=check.level,
                message=check.message,
            )
            (errors if check.level == "error" else warnings).append(issue)

        errors_tuple = tuple(errors)
        warnings_tuple = tuple(warnings)
        return ProductionPreflightResult(
            workspace=plan.workspace,
            project_path=plan.project_path,
            manifest_path=plan.workspace.production_preflight_manifest_path,
            status="blocked" if errors_tuple else "ready",
            errors=errors_tuple,
            warnings=warnings_tuple,
            output_path=plan.output_path,
            ffmpeg_available=ffmpeg_available,
            error_count=len(errors_tuple),
            warning_count=len(warnings_tuple),
        )

    @staticmethod
    def _manifest_data(
        result: ProductionPreflightResult,
        *,
        plan: _PreflightPlan,
    ) -> dict:
        def issue_data(issue: ProductionPreflightIssue) -> dict:
            return {
                "key": issue.key,
                "label": issue.label,
                "level": issue.level,
                "message": ProductionPreflightRunner._sanitize_message(
                    issue.message,
                    plan.project_root,
                    label=issue.label,
                ),
            }

        errors = sorted(
            (issue_data(issue) for issue in result.errors),
            key=lambda item: (
                item["key"],
                item["label"],
                item["level"],
                item["message"],
            ),
        )
        warnings = sorted(
            (issue_data(issue) for issue in result.warnings),
            key=lambda item: (
                item["key"],
                item["label"],
                item["level"],
                item["message"],
            ),
        )
        return {
            "production_preflight_manifest_schema_version": (
                PRODUCTION_PREFLIGHT_MANIFEST_SCHEMA_VERSION
            ),
            "project": {
                "path": result.project_path.relative_to(plan.project_root).as_posix(),
                "sha256": plan.project_sha256,
            },
            "render_output": {
                "path": result.output_path.relative_to(plan.project_root).as_posix()
            },
            "status": result.status,
            "ffmpeg_available": result.ffmpeg_available,
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "errors": errors,
            "warnings": warnings,
        }

    @staticmethod
    def _sanitize_message(message: str, project_root: Path, *, label: str) -> str:
        sanitized = message
        variants = sorted(
            {str(project_root), project_root.as_posix()},
            key=len,
            reverse=True,
        )
        for variant in variants:
            sanitized = re.sub(
                re.escape(variant),
                "<project_root>",
                sanitized,
                flags=re.IGNORECASE,
            )
        if _WINDOWS_ABSOLUTE_PATH.search(sanitized) or _PERSONAL_POSIX_PATH.search(
            sanitized
        ):
            return f"{label}: details omitted because they contained an external path."
        return sanitized

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
                "Partial preflight manifest cleanup also failed: "
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
        if not path.is_file():
            raise ValueError(f"{label.capitalize()} does not exist.")
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
    def _error(stage: str, operation: str) -> ProductionPreflightError:
        return ProductionPreflightError(
            f"Production preflight failed during {stage!r} while {operation}."
        )
