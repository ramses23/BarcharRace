import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

from config.project_file_loader import load_project_file
from studio.project_builder import load_project_data
from studio.workspace_paths import assert_user_write_path


BINDING_SCHEMA_VERSION = 2
LEGACY_BINDING_SCHEMA_VERSION = 1
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
    project_relative_path: str = ""
    production_reference: str = ""


@dataclass(frozen=True)
class ProductionPackageBinding:
    state_path: Path
    project: LinkedProject
    package_manifest_sha256: str
    package_reference: str
    bound_at: str
    production_reference: str = ""


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
    root_dir=None,
    workspace_root=None,
    app_root=None,
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
        if data["schema_version"] == BINDING_SCHEMA_VERSION:
            if workspace_root is None:
                raise ProductionPackageBindingError(
                    "workspace_root is required for this production binding."
                )
            project = resolve_linked_project(
                data["project_relative_path"],
                workspace_root=workspace_root,
                production_reference=data["production_reference"],
                require_portable_relative=True,
            )
        else:
            if root_dir is None:
                raise ProductionPackageBindingError(
                    "root_dir is required for a legacy production binding."
                )
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
        production_reference=project.production_reference,
    )


def write_production_package_binding(
    package_path,
    *,
    root_dir=None,
    workspace_root=None,
    app_root=None,
    project_path,
    package_manifest_sha256,
):
    if not SHA256_PATTERN.fullmatch(str(package_manifest_sha256)):
        raise ProductionPackageBindingError(
            "Package manifest SHA-256 is invalid."
        )

    package = Path(package_path).resolve(strict=True)
    state_path = binding_path_for_package(package)
    if app_root is not None:
        state_path = assert_user_write_path(
            state_path,
            app_root=app_root,
            operation="Production package binding",
        )
    if _is_link(state_path):
        raise ProductionPackageBindingError(
            f"Binding file must not be a symbolic link: {state_path}"
        )
    if package.is_dir() and state_path.resolve().is_relative_to(package):
        raise ProductionPackageBindingError(
            "Binding file must remain outside the signed package directory."
        )

    if workspace_root is not None:
        if root_dir is not None:
            raise ProductionPackageBindingError(
                "Use workspace_root or root_dir, not both."
            )
        project = resolve_linked_project(
            project_path,
            workspace_root=workspace_root,
        )
        schema_version = BINDING_SCHEMA_VERSION
    else:
        if root_dir is None:
            raise ProductionPackageBindingError(
                "workspace_root is required for production bindings."
            )
        project = resolve_linked_project(project_path, root_dir=root_dir)
        schema_version = LEGACY_BINDING_SCHEMA_VERSION
    bound_at = datetime.now(timezone.utc).isoformat()
    package_reference = _package_reference(package, state_path)
    data = {
        "schema_version": schema_version,
        "package_manifest_sha256": package_manifest_sha256,
        "package_reference": package_reference,
        "bound_at": bound_at,
    }
    if schema_version == BINDING_SCHEMA_VERSION:
        data.update(
            {
                "production_reference": project.production_reference,
                "project_relative_path": project.project_relative_path,
            }
        )
    else:
        data["project_path"] = project.relative_path
    _atomic_write_binding(data, state_path)
    return ProductionPackageBinding(
        state_path=state_path,
        project=project,
        package_manifest_sha256=package_manifest_sha256,
        package_reference=package_reference,
        bound_at=bound_at,
        production_reference=project.production_reference,
    )


def resolve_linked_project(
    project_path,
    *,
    root_dir=None,
    workspace_root=None,
    production_reference=None,
    require_portable_relative=False,
):
    if workspace_root is not None:
        if root_dir is not None:
            raise ProductionPackageBindingError(
                "Use workspace_root or root_dir, not both."
            )
        return _resolve_workspace_linked_project(
            project_path,
            workspace_root=workspace_root,
            production_reference=production_reference,
            require_portable_relative=require_portable_relative,
        )
    if root_dir is None:
        raise ProductionPackageBindingError("root_dir is required.")
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


def _resolve_workspace_linked_project(
    project_path,
    *,
    workspace_root,
    production_reference=None,
    require_portable_relative=False,
):
    workspace = Path(workspace_root).resolve(strict=True)
    if not workspace.is_dir() or _is_link(workspace):
        raise ProductionPackageBindingError(
            f"Workspace root is not a safe directory: {workspace}"
        )

    raw_path = os.fspath(project_path)
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ProductionPackageBindingError(
            "Project path must be a non-empty path."
        )
    raw_path = raw_path.strip()
    portable_path = PurePosixPath(raw_path.replace("\\", "/"))
    windows_path = PureWindowsPath(raw_path)

    if production_reference is not None:
        production_relative = _portable_production_reference(production_reference)
        production_root = workspace.joinpath(*production_relative.parts)
        project_relative = _portable_project_relative_path(portable_path.as_posix())
        candidate = production_root.joinpath(*project_relative.parts)
    elif Path(raw_path).is_absolute() or windows_path.is_absolute():
        if require_portable_relative:
            raise ProductionPackageBindingError(
                "Binding project path must be portable and relative."
            )
        candidate = Path(raw_path)
        lexical_candidate = Path(os.path.abspath(candidate))
        try:
            workspace_relative = lexical_candidate.relative_to(workspace)
        except ValueError as exc:
            raise ProductionPackageBindingError(
                "Project path must remain inside WORKSPACE_ROOT."
            ) from exc
        if (
            len(workspace_relative.parts) < 4
            or workspace_relative.parts[0] != "productions"
            or workspace_relative.parts[2] != "projects"
        ):
            raise ProductionPackageBindingError(
                "Project path must be inside productions/<slug>/projects/."
            )
        production_relative = PurePosixPath(*workspace_relative.parts[:2])
        production_root = workspace.joinpath(*production_relative.parts)
        project_relative = PurePosixPath(*workspace_relative.parts[2:])
    else:
        if production_reference is None:
            raise ProductionPackageBindingError(
                "production_reference is required for a relative project path."
            )
        raise AssertionError("unreachable")

    project_relative = _portable_project_relative_path(
        project_relative.as_posix()
    )
    lexical_candidate = Path(os.path.abspath(candidate))
    production_root = Path(os.path.abspath(production_root))
    try:
        lexical_candidate.relative_to(production_root / "projects")
    except ValueError as exc:
        raise ProductionPackageBindingError(
            "Project path must remain inside the production projects directory."
        ) from exc
    _reject_links_between(lexical_candidate, production_root)
    if not lexical_candidate.exists():
        raise FileNotFoundError(f"Project file was not found: {lexical_candidate}")

    resolved_project = lexical_candidate.resolve(strict=True)
    resolved_production = production_root.resolve(strict=True)
    if (
        not resolved_project.is_file()
        or not resolved_project.is_relative_to(resolved_production / "projects")
    ):
        raise ProductionPackageBindingError(
            "Project path resolves outside the production projects directory."
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
        relative_path=resolved_project.relative_to(workspace).as_posix(),
        name=str(project_name),
        project_relative_path=resolved_project.relative_to(
            resolved_production
        ).as_posix(),
        production_reference=resolved_production.relative_to(workspace).as_posix(),
    )


def _portable_production_reference(value):
    portable = _portable_relative_path(value, label="production_reference")
    if len(portable.parts) != 2 or portable.parts[0] != "productions":
        raise ProductionPackageBindingError(
            "production_reference must use productions/<production_slug>."
        )
    return portable


def _portable_project_relative_path(value):
    portable = _portable_relative_path(value, label="project_relative_path")
    if (
        len(portable.parts) < 2
        or portable.parts[0] != "projects"
        or portable.suffix.lower() != ".json"
    ):
        raise ProductionPackageBindingError(
            "project_relative_path must identify a JSON file under projects/."
        )
    return portable


def _portable_relative_path(value, *, label):
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw.strip():
        raise ProductionPackageBindingError(f"{label} must be a non-empty path.")
    raw = raw.strip()
    portable = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if (
        "\\" in raw
        or portable.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or "." in portable.parts
        or ".." in portable.parts
    ):
        raise ProductionPackageBindingError(
            f"{label} must be a portable relative path."
        )
    return portable


def _reject_links_between(path, root):
    current = Path(path)
    root = Path(root)
    while True:
        if _is_link(current):
            raise ProductionPackageBindingError(
                "Project path must not use symbolic links or junctions."
            )
        if current == root:
            return
        if current == current.parent:
            raise ProductionPackageBindingError(
                "Project path escapes its production root."
            )
        current = current.parent


def _validated_binding_data(data, *, state_path):
    if not isinstance(data, dict):
        raise ProductionPackageBindingError(
            f"Binding file is corrupt: {state_path}. Expected a JSON object."
        )
    if (
        not isinstance(data.get("schema_version"), int)
        or isinstance(data.get("schema_version"), bool)
        or data["schema_version"] not in {
            LEGACY_BINDING_SCHEMA_VERSION,
            BINDING_SCHEMA_VERSION,
        }
    ):
        raise ProductionPackageBindingError(
            f"Binding file uses an unsupported schema: {state_path}"
        )

    required_strings = [
        "package_manifest_sha256",
        "package_reference",
        "bound_at",
    ]
    if data["schema_version"] == BINDING_SCHEMA_VERSION:
        required_strings.extend(
            ("production_reference", "project_relative_path")
        )
    else:
        required_strings.append("project_path")
    for key in required_strings:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ProductionPackageBindingError(
                f"Binding file is corrupt: field {key!r} is invalid."
            )
    if not SHA256_PATTERN.fullmatch(data["package_manifest_sha256"]):
        raise ProductionPackageBindingError(
            "Binding file is corrupt: package_manifest_sha256 is invalid."
        )

    if data["schema_version"] == BINDING_SCHEMA_VERSION:
        _portable_production_reference(data["production_reference"])
        _portable_project_relative_path(data["project_relative_path"])
    else:
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
