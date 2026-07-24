import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

from config.project_file_loader import load_project_file
from studio.project_builder import load_project_data


BINDING_SCHEMA_VERSION = 1
BINDING_FILENAME = ".barchartstudio-launch.json"
MAX_BINDING_BYTES = 64 * 1024
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class ProductionPackageBindingError(ValueError):
    pass


@dataclass(frozen=True)
class LinkedProject:
    absolute_path: Path
    relative_path: str
    name: str


@dataclass(frozen=True)
class ProductionPackageBinding:
    state_path: Path
    project: LinkedProject
    package_manifest_sha256: str
    package_reference: str
    bound_at: str


def binding_path_for_package(package_path):
    package = Path(package_path).resolve(strict=True)
    if package.is_dir():
        return package.parent / BINDING_FILENAME
    if package.is_file() and package.suffix.lower() == ".zip":
        return package.with_name(f"{package.name}.barchartstudio-launch.json")
    raise ProductionPackageBindingError(
        "Package path must reference a .zip file or a directory."
    )


def load_production_package_binding(
    package_path,
    *,
    root_dir,
    package_manifest_sha256,
):
    package = Path(package_path).resolve(strict=True)
    state_path = binding_path_for_package(package)
    if not state_path.exists() and not state_path.is_symlink():
        return None
    if _is_link(state_path):
        raise ProductionPackageBindingError(
            f"Binding file must not be a symbolic link: {state_path}"
        )
    if not state_path.is_file():
        raise ProductionPackageBindingError(
            f"Binding path is not a regular file: {state_path}"
        )
    try:
        if state_path.stat().st_size > MAX_BINDING_BYTES:
            raise ProductionPackageBindingError(
                f"Binding file is too large: {state_path}"
            )
        raw_data = json.loads(state_path.read_text(encoding="utf-8"))
    except ProductionPackageBindingError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionPackageBindingError(
            f"Binding file is corrupt: {state_path}. {exc}"
        ) from exc

    data = _validated_binding_data(raw_data, state_path=state_path)
    expected_reference = _package_reference(package, state_path)
    if data["package_reference"] != expected_reference:
        raise ProductionPackageBindingError(
            "Binding does not refer to the current production package. "
            "Use --reimport to create a new binding."
        )
    if data["package_manifest_sha256"] != package_manifest_sha256:
        raise ProductionPackageBindingError(
            "Production package manifest changed after this project was linked. "
            "Use --reimport to import and link the current package explicitly."
        )

    try:
        project = resolve_linked_project(
            data["project_path"],
            root_dir=root_dir,
            require_portable_relative=True,
        )
    except FileNotFoundError as exc:
        raise ProductionPackageBindingError(
            "The linked editable project was deleted. Use --reimport or "
            "--adopt-project PROJECT_PATH."
        ) from exc

    return ProductionPackageBinding(
        state_path=state_path,
        project=project,
        package_manifest_sha256=data["package_manifest_sha256"],
        package_reference=data["package_reference"],
        bound_at=data["bound_at"],
    )


def write_production_package_binding(
    package_path,
    *,
    root_dir,
    project_path,
    package_manifest_sha256,
):
    if not SHA256_PATTERN.fullmatch(str(package_manifest_sha256)):
        raise ProductionPackageBindingError(
            "Package manifest SHA-256 is invalid."
        )

    package = Path(package_path).resolve(strict=True)
    state_path = binding_path_for_package(package)
    if _is_link(state_path):
        raise ProductionPackageBindingError(
            f"Binding file must not be a symbolic link: {state_path}"
        )
    if package.is_dir() and state_path.resolve().is_relative_to(package):
        raise ProductionPackageBindingError(
            "Binding file must remain outside the signed package directory."
        )

    project = resolve_linked_project(project_path, root_dir=root_dir)
    bound_at = datetime.now(timezone.utc).isoformat()
    package_reference = _package_reference(package, state_path)
    data = {
        "schema_version": BINDING_SCHEMA_VERSION,
        "project_path": project.relative_path,
        "package_manifest_sha256": package_manifest_sha256,
        "package_reference": package_reference,
        "bound_at": bound_at,
    }
    _atomic_write_binding(data, state_path)
    return ProductionPackageBinding(
        state_path=state_path,
        project=project,
        package_manifest_sha256=package_manifest_sha256,
        package_reference=package_reference,
        bound_at=bound_at,
    )


def resolve_linked_project(
    project_path,
    *,
    root_dir,
    require_portable_relative=False,
):
    root = Path(root_dir).resolve(strict=True)
    if not root.is_dir():
        raise ProductionPackageBindingError(
            f"BarChartStudio root is not a directory: {root}"
        )

    projects_entry = root / "projects"
    if _is_link(projects_entry):
        raise ProductionPackageBindingError(
            "The root projects directory must not be a symbolic link."
        )

    raw_path = os.fspath(project_path)
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ProductionPackageBindingError(
            "Project path must be a non-empty path."
        )
    raw_path = raw_path.strip()
    portable_path = PurePosixPath(raw_path.replace("\\", "/"))
    windows_path = PureWindowsPath(raw_path)

    if require_portable_relative:
        if (
            "\\" in raw_path
            or portable_path.is_absolute()
            or windows_path.is_absolute()
            or windows_path.drive
            or ".." in portable_path.parts
        ):
            raise ProductionPackageBindingError(
                "Binding project_path must be a portable relative path."
            )
        candidate = root.joinpath(*portable_path.parts)
    elif Path(raw_path).is_absolute() or windows_path.is_absolute():
        candidate = Path(raw_path)
    else:
        if portable_path.is_absolute() or windows_path.drive:
            raise ProductionPackageBindingError(
                "Project path has an unsupported absolute path."
            )
        candidate = root.joinpath(*portable_path.parts)

    lexical_candidate = Path(os.path.abspath(candidate))
    try:
        lexical_relative = lexical_candidate.relative_to(projects_entry)
    except ValueError as exc:
        raise ProductionPackageBindingError(
            "Project path must remain inside root/projects."
        ) from exc
    if len(lexical_relative.parts) != 1:
        raise ProductionPackageBindingError(
            "Project path must identify a JSON file directly inside "
            "root/projects."
        )
    if lexical_candidate.suffix.lower() != ".json":
        raise ProductionPackageBindingError(
            "Project path must identify a JSON file."
        )

    try:
        projects_root = projects_entry.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Project directory was not found: {projects_entry}"
        ) from exc
    if not projects_root.is_dir() or not projects_root.is_relative_to(root):
        raise ProductionPackageBindingError(
            "The root projects directory resolves outside BarChartStudio."
        )

    current = projects_entry
    for part in lexical_relative.parts:
        current /= part
        if _is_link(current):
            raise ProductionPackageBindingError(
                "Project path must not use symbolic links or junctions."
            )
    if not lexical_candidate.exists():
        raise FileNotFoundError(f"Project file was not found: {lexical_candidate}")

    resolved_project = lexical_candidate.resolve(strict=True)
    if (
        not resolved_project.is_file()
        or not resolved_project.is_relative_to(projects_root)
    ):
        raise ProductionPackageBindingError(
            "Project path resolves outside root/projects."
        )

    try:
        project_data = load_project_data(resolved_project)
        preset = load_project_file(resolved_project)
    except (OSError, ValueError) as exc:
        raise ProductionPackageBindingError(
            f"Project is not a usable Project Studio JSON file: {exc}"
        ) from exc

    project_name = project_data.get("name") or preset.name
    return LinkedProject(
        absolute_path=resolved_project,
        relative_path=resolved_project.relative_to(root).as_posix(),
        name=str(project_name),
    )


def _validated_binding_data(data, *, state_path):
    if not isinstance(data, dict):
        raise ProductionPackageBindingError(
            f"Binding file is corrupt: {state_path}. Expected a JSON object."
        )
    if (
        not isinstance(data.get("schema_version"), int)
        or isinstance(data.get("schema_version"), bool)
        or data["schema_version"] != BINDING_SCHEMA_VERSION
    ):
        raise ProductionPackageBindingError(
            f"Binding file uses an unsupported schema: {state_path}"
        )

    required_strings = (
        "project_path",
        "package_manifest_sha256",
        "package_reference",
        "bound_at",
    )
    for key in required_strings:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ProductionPackageBindingError(
                f"Binding file is corrupt: field {key!r} is invalid."
            )
    if not SHA256_PATTERN.fullmatch(data["package_manifest_sha256"]):
        raise ProductionPackageBindingError(
            "Binding file is corrupt: package_manifest_sha256 is invalid."
        )

    project_path = PurePosixPath(data["project_path"])
    project_windows_path = PureWindowsPath(data["project_path"])
    if (
        "\\" in data["project_path"]
        or project_path.is_absolute()
        or project_windows_path.is_absolute()
        or project_windows_path.drive
        or ".." in project_path.parts
        or len(project_path.parts) != 2
        or project_path.parts[0] != "projects"
        or project_path.suffix.lower() != ".json"
    ):
        raise ProductionPackageBindingError(
            "Binding file is corrupt: project_path is not a portable project "
            "JSON path."
        )

    reference = PurePosixPath(data["package_reference"])
    if (
        "\\" in data["package_reference"]
        or reference.is_absolute()
        or ".." in reference.parts
        or not reference.parts
    ):
        raise ProductionPackageBindingError(
            "Binding file is corrupt: package_reference is not portable."
        )
    try:
        parsed_bound_at = datetime.fromisoformat(data["bound_at"])
    except ValueError as exc:
        raise ProductionPackageBindingError(
            "Binding file is corrupt: bound_at is invalid."
        ) from exc
    if parsed_bound_at.tzinfo is None:
        raise ProductionPackageBindingError(
            "Binding file is corrupt: bound_at must include a timezone."
        )
    return data


def _package_reference(package, state_path):
    try:
        return package.relative_to(state_path.parent.resolve()).as_posix()
    except ValueError as exc:
        raise ProductionPackageBindingError(
            "Package reference cannot be stored as a portable relative path."
        ) from exc


def _atomic_write_binding(data, state_path):
    temporary_path = state_path.with_name(
        f".{state_path.name}.{uuid4().hex}.tmp"
    )
    try:
        with temporary_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, state_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _is_link(path):
    path = Path(path)
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())
