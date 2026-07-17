from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


WORKSPACE_SCHEMA_VERSION = 1
PRODUCTION_STATUS_SCHEMA_VERSION = 1
DEFAULT_PRODUCTION_JOBS_ROOT = (
    Path(__file__).resolve().parents[2] / "output" / ".production_jobs"
).resolve()

_JOB_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)


def validate_job_id(job_id: str) -> str:
    """Validate and return an unchanged portable production job identifier."""

    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job_id must be a non-empty string.")
    if len(job_id) > 64:
        raise ValueError("job_id must not exceed 64 characters.")
    if not _JOB_ID_PATTERN.fullmatch(job_id):
        raise ValueError(
            "job_id must start with a lowercase letter or digit and contain "
            "only lowercase letters, digits, hyphens, or underscores."
        )
    if job_id.casefold() in _WINDOWS_RESERVED_NAMES:
        raise ValueError(f"job_id uses a Windows-reserved name: {job_id}")
    return job_id


@dataclass(frozen=True)
class ProductionWorkspace:
    """Canonical paths for one isolated production job.

    Constructing the value object has no filesystem effects. Use ``create`` to
    reserve and initialize a workspace exclusively. An alternate ``root_dir``
    is the parent directory that will contain job-specific directories.
    """

    job_id: str
    root_path: Path

    _DIRECTORY_NAMES: ClassVar[tuple[str, ...]] = (
        "input",
        "dataset",
        "logos",
        "project",
        "render",
        "logs",
        "manifests",
    )

    def __post_init__(self) -> None:
        validate_job_id(self.job_id)
        resolved_root = Path(self.root_path).resolve(strict=False)
        if resolved_root.name != self.job_id:
            raise ValueError("root_path must end with the exact job_id.")
        object.__setattr__(self, "root_path", resolved_root)

    @classmethod
    def create(
        cls,
        *,
        job_id: str,
        root_dir: str | Path | None = None,
    ) -> ProductionWorkspace:
        validate_job_id(job_id)
        jobs_root = Path(root_dir or DEFAULT_PRODUCTION_JOBS_ROOT).resolve(
            strict=False
        )
        jobs_root.mkdir(parents=True, exist_ok=True)
        workspace_path = (jobs_root / job_id).resolve(strict=False)
        cls._require_direct_child(workspace_path, jobs_root, job_id)
        workspace = cls(job_id=job_id, root_path=workspace_path)

        workspace.root_path.mkdir(exist_ok=False)
        try:
            for directory in workspace.directories:
                cls._create_subdirectory(directory)
            cls._write_json_exclusive(
                workspace._manifest_data(),
                workspace.workspace_manifest_path,
            )
            cls._write_json_exclusive(
                workspace._initial_status_data(),
                workspace.status_path,
            )
        except BaseException as original_error:
            try:
                cls._rollback_created_workspace(
                    workspace.root_path,
                    jobs_root=jobs_root,
                    job_id=job_id,
                )
            except BaseException as rollback_error:
                original_error.add_note(
                    "Production workspace rollback also failed for "
                    f"{workspace.root_path}: {rollback_error}"
                )
            raise

        return workspace

    @property
    def input_dir(self) -> Path:
        return self._child_path("input")

    @property
    def dataset_dir(self) -> Path:
        return self._child_path("dataset")

    @property
    def logos_dir(self) -> Path:
        return self._child_path("logos")

    @property
    def primary_logos_dir(self) -> Path:
        return self._file_path(self.logos_dir, "primary")

    @property
    def secondary_logos_dir(self) -> Path:
        return self._file_path(self.logos_dir, "secondary")

    @property
    def project_dir(self) -> Path:
        return self._child_path("project")

    @property
    def render_dir(self) -> Path:
        return self._child_path("render")

    @property
    def logs_dir(self) -> Path:
        return self._child_path("logs")

    @property
    def manifests_dir(self) -> Path:
        return self._child_path("manifests")

    @property
    def directories(self) -> tuple[Path, ...]:
        return tuple(self._child_path(name) for name in self._DIRECTORY_NAMES)

    @property
    def status_path(self) -> Path:
        return self._child_path("status.json")

    @property
    def workspace_manifest_path(self) -> Path:
        return self._child_path("workspace_manifest.json")

    @property
    def source_csv_path(self) -> Path:
        return self._file_path(self.input_dir, "source.csv")

    @property
    def dataset_csv_path(self) -> Path:
        return self._file_path(self.dataset_dir, "dataset.csv")

    @property
    def dataset_build_manifest_path(self) -> Path:
        return self._file_path(self.manifests_dir, "dataset_build.json")

    @property
    def logo_resolution_manifest_path(self) -> Path:
        return self._file_path(self.manifests_dir, "logo_resolution.json")

    @property
    def project_assembly_manifest_path(self) -> Path:
        return self._file_path(self.manifests_dir, "project_assembly.json")

    @property
    def production_preflight_manifest_path(self) -> Path:
        return self._file_path(self.manifests_dir, "production_preflight.json")

    @property
    def project_json_path(self) -> Path:
        return self._file_path(self.project_dir, "project.json")

    @property
    def video_path(self) -> Path:
        return self._file_path(self.render_dir, "video.mp4")

    @property
    def production_log_path(self) -> Path:
        return self._file_path(self.logs_dir, "production.log")

    def replace_status(self, data: dict) -> None:
        """Atomically replace this workspace's existing production status."""
        self._write_json_replacing(data, self.status_path)

    def publish_dataset_build_manifest(self, data: dict) -> None:
        """Publish the dataset manifest without overwriting an existing file."""
        self._write_json_exclusive(data, self.dataset_build_manifest_path)

    def publish_logo_resolution_manifest(self, data: dict) -> None:
        """Publish the logo manifest without overwriting an existing file."""
        self._write_json_exclusive(data, self.logo_resolution_manifest_path)

    def publish_project_assembly_manifest(self, data: dict) -> None:
        """Publish the project manifest without overwriting an existing file."""
        self._write_json_exclusive(data, self.project_assembly_manifest_path)

    def publish_production_preflight_manifest(self, data: dict) -> None:
        """Publish the preflight manifest without overwriting an existing file."""
        self._write_json_exclusive(data, self.production_preflight_manifest_path)

    def _child_path(self, name: str) -> Path:
        candidate = (self.root_path / name).resolve(strict=False)
        if candidate.parent != self.root_path:
            raise ValueError(f"Workspace path escapes its root: {candidate}")
        return candidate

    def _file_path(self, directory: Path, filename: str) -> Path:
        candidate = (directory / filename).resolve(strict=False)
        if candidate.parent != directory or not candidate.is_relative_to(
            self.root_path
        ):
            raise ValueError(f"Artifact path escapes its workspace: {candidate}")
        return candidate

    def _manifest_data(self) -> dict:
        return {
            "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
            "job_id": self.job_id,
            "paths": {
                "input": "input",
                "dataset": "dataset",
                "logos": "logos",
                "project": "project",
                "render": "render",
                "logs": "logs",
                "manifests": "manifests",
                "status": "status.json",
            },
        }

    def _initial_status_data(self) -> dict:
        return {
            "production_status_schema_version": PRODUCTION_STATUS_SCHEMA_VERSION,
            "job_id": self.job_id,
            "state": "created",
            "stage": "workspace",
            "message": "Production workspace created.",
        }

    @staticmethod
    def _require_direct_child(path: Path, parent: Path, job_id: str) -> None:
        if path.parent != parent or path.name != job_id:
            raise ValueError("Resolved workspace path must remain inside root_dir.")

    @staticmethod
    def _create_subdirectory(path: Path) -> None:
        path.mkdir(exist_ok=False)

    @classmethod
    def _rollback_created_workspace(
        cls,
        workspace_path: Path,
        *,
        jobs_root: Path,
        job_id: str,
    ) -> None:
        cls._require_direct_child(workspace_path, jobs_root, job_id)
        shutil.rmtree(workspace_path)

    @staticmethod
    def _write_json_exclusive(data: dict, destination: Path) -> None:
        temporary_path = ProductionWorkspace._write_json_temporary(
            data,
            destination,
        )
        try:
            try:
                os.link(temporary_path, destination)
            except FileExistsError as exc:
                raise FileExistsError(
                    f"JSON destination already exists: {destination}"
                ) from exc
            except OSError as exc:
                raise OSError(
                    "Atomic JSON publication failed while creating a hardlink "
                    f"for {destination}."
                ) from exc
        except BaseException as original_error:
            ProductionWorkspace._cleanup_json_temporary_after_error(
                temporary_path,
                original_error,
            )
            raise

        try:
            temporary_path.unlink(missing_ok=True)
        except OSError as cleanup_error:
            raise OSError(
                f"Published JSON temporary cleanup failed: {temporary_path}"
            ) from cleanup_error

    @staticmethod
    def _write_json_replacing(data: dict, destination: Path) -> None:
        temporary_path = ProductionWorkspace._write_json_temporary(
            data,
            destination,
        )
        try:
            try:
                os.replace(temporary_path, destination)
            except OSError as exc:
                raise OSError(
                    f"Atomic JSON replacement failed for {destination}."
                ) from exc
        except BaseException as original_error:
            ProductionWorkspace._cleanup_json_temporary_after_error(
                temporary_path,
                original_error,
            )
            raise

    @staticmethod
    def _write_json_temporary(data: dict, destination: Path) -> Path:
        serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="x",
                encoding="utf-8",
                newline="\n",
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(serialized)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
        except BaseException as original_error:
            if temporary_path is not None:
                ProductionWorkspace._cleanup_json_temporary_after_error(
                    temporary_path,
                    original_error,
                )
            raise
        return temporary_path

    @staticmethod
    def _cleanup_json_temporary_after_error(
        temporary_path: Path,
        original_error: BaseException,
    ) -> None:
        try:
            temporary_path.unlink(missing_ok=True)
        except BaseException as cleanup_error:
            original_error.add_note(
                "Temporary JSON cleanup also failed for "
                f"{temporary_path}: {cleanup_error}"
            )
