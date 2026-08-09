import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4


APP_NAME = "BarChartStudio"
APP_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_SCHEMA_VERSION = 1
SETTINGS_FILENAME = "settings.json"
SETTINGS_FILE_ENV = "BARCHARTSTUDIO_SETTINGS_FILE"
WORKSPACE_ROOT_ENV = "BARCHARTSTUDIO_WORKSPACE"
WORKSPACE_DIRECTORIES = ("productions", "scratch", "packages", "cache")
MAX_SETTINGS_BYTES = 64 * 1024
SLUG_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}")


class WorkspacePathError(ValueError):
    pass


class AppRootWriteError(WorkspacePathError):
    pass


@dataclass(frozen=True)
class WorkspaceSettings:
    workspace_root: Path
    settings_path: Path
    configured: bool


@dataclass(frozen=True)
class WorkspaceLayout:
    app_root: Path
    workspace_root: Path

    @property
    def examples_root(self):
        return self.app_root / "examples"

    @property
    def presets_root(self):
        return self.app_root / "presets"

    @property
    def productions_root(self):
        return self.workspace_root / "productions"

    @property
    def scratch_root(self):
        return self.workspace_root / "scratch"

    @property
    def packages_root(self):
        return self.workspace_root / "packages"

    @property
    def cache_root(self):
        return self.workspace_root / "cache"

    def production_root(self, slug, *, create=False):
        root = self.productions_root / validate_slug(slug)
        if create:
            _create_user_directory(root, layout=self)
        return root

    def scratch_project_root(self, slug, *, create=False):
        root = self.scratch_root / validate_slug(slug)
        if create:
            _create_user_directory(root, layout=self)
        return root


@dataclass(frozen=True)
class ProjectLocation:
    identifier: str
    absolute_path: Path
    project_root: Path
    relative_path: str
    kind: str
    label: str
    writable: bool


def default_workspace_root(app_root=APP_ROOT):
    app_root = _absolute_path(app_root, label="app_root")
    return app_root.parent / f"{app_root.name}Workspace"


def default_settings_path(*, environ=None):
    environment = os.environ if environ is None else environ
    override = environment.get(SETTINGS_FILE_ENV)
    if override:
        return _absolute_path(override, label=SETTINGS_FILE_ENV)

    local_app_data = environment.get("LOCALAPPDATA")
    if local_app_data:
        base = _absolute_path(local_app_data, label="LOCALAPPDATA")
    else:
        xdg_config = environment.get("XDG_CONFIG_HOME")
        if xdg_config:
            base = _absolute_path(xdg_config, label="XDG_CONFIG_HOME")
        else:
            base = Path.home().resolve() / ".config"
    return base / APP_NAME / SETTINGS_FILENAME


def load_workspace_settings(
    *,
    app_root=APP_ROOT,
    settings_path=None,
    environ=None,
):
    app_root = _existing_directory(app_root, label="app_root")
    environment = os.environ if environ is None else environ
    path = _settings_path(settings_path, environ=environment)
    _validate_settings_location(path, app_root=app_root)

    environment_workspace = environment.get(WORKSPACE_ROOT_ENV)
    if environment_workspace:
        workspace_root = validate_workspace_root(
            environment_workspace,
            app_root=app_root,
        )
        return WorkspaceSettings(workspace_root, path, configured=False)

    if not path.exists() and not _is_link(path):
        return WorkspaceSettings(
            default_workspace_root(app_root),
            path,
            configured=False,
        )
    if _is_link(path):
        raise WorkspacePathError(
            f"Workspace settings must not be a symbolic link or junction: {path}"
        )
    if not path.is_file():
        raise WorkspacePathError(
            f"Workspace settings path is not a regular file: {path}"
        )
    if path.stat().st_size > MAX_SETTINGS_BYTES:
        raise WorkspacePathError(f"Workspace settings file is too large: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspacePathError(
            f"Workspace settings are not valid JSON: {path}. {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise WorkspacePathError("Workspace settings must contain a JSON object.")
    if set(data) != {"schema_version", "workspace_root"}:
        raise WorkspacePathError(
            "Workspace settings support only schema_version and workspace_root."
        )
    if data.get("schema_version") != SETTINGS_SCHEMA_VERSION:
        raise WorkspacePathError("Workspace settings use an unsupported schema.")
    workspace_root = validate_workspace_root(
        data.get("workspace_root"),
        app_root=app_root,
    )
    return WorkspaceSettings(workspace_root, path, configured=True)


def save_workspace_settings(
    workspace_root,
    *,
    app_root=APP_ROOT,
    settings_path=None,
    environ=None,
):
    app_root = _existing_directory(app_root, label="app_root")
    path = _settings_path(settings_path, environ=environ)
    _validate_settings_location(path, app_root=app_root)
    workspace_root = validate_workspace_root(workspace_root, app_root=app_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_existing_links(path.parent)
    if _is_link(path):
        raise WorkspacePathError(
            f"Workspace settings must not be a symbolic link or junction: {path}"
        )

    payload = {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "workspace_root": str(workspace_root),
    }
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return WorkspaceSettings(workspace_root, path, configured=True)


def workspace_layout(
    *,
    app_root=APP_ROOT,
    settings_path=None,
    environ=None,
):
    settings = load_workspace_settings(
        app_root=app_root,
        settings_path=settings_path,
        environ=environ,
    )
    return WorkspaceLayout(
        app_root=_existing_directory(app_root, label="app_root"),
        workspace_root=settings.workspace_root,
    )


def initialize_workspace(workspace_root, *, app_root=APP_ROOT):
    app_root = _existing_directory(app_root, label="app_root")
    root = validate_workspace_root(workspace_root, app_root=app_root)
    layout = WorkspaceLayout(app_root=app_root, workspace_root=root)
    _create_user_directory(root, layout=layout)
    for directory in WORKSPACE_DIRECTORIES:
        _create_user_directory(root / directory, layout=layout)
    return layout


def validate_workspace_root(value, *, app_root=APP_ROOT):
    app_root = _existing_directory(app_root, label="app_root")
    root = _absolute_path(value, label="workspace_root")
    resolved = root.resolve(strict=False)
    if _paths_overlap(resolved, app_root):
        raise WorkspacePathError(
            "workspace_root must be outside APP_ROOT and must not contain APP_ROOT."
        )
    _reject_existing_links(root)
    if root.exists() and not root.is_dir():
        raise WorkspacePathError(
            f"workspace_root is not a directory: {root}"
        )
    return resolved


def assert_user_write_path(
    path,
    *,
    app_root=APP_ROOT,
    workspace_root=None,
    operation="User content",
):
    app_root = _existing_directory(app_root, label="app_root")
    candidate = _absolute_path(path, label="write path").resolve(strict=False)
    if candidate == app_root or candidate.is_relative_to(app_root):
        raise AppRootWriteError(
            f"{operation} cannot write inside APP_ROOT: {candidate}"
        )
    if workspace_root is not None:
        workspace = validate_workspace_root(workspace_root, app_root=app_root)
        if candidate != workspace and not candidate.is_relative_to(workspace):
            raise WorkspacePathError(
                f"{operation} must remain inside WORKSPACE_ROOT: {workspace}"
            )
        _reject_existing_links(candidate, stop_at=workspace)
    else:
        _reject_existing_links(candidate)
    return candidate


def discover_project_locations(layout, *, include_legacy=True):
    if not isinstance(layout, WorkspaceLayout):
        raise TypeError("layout must be a WorkspaceLayout.")
    locations = []

    if layout.productions_root.is_dir() and not _is_link(layout.productions_root):
        for production_root in sorted(layout.productions_root.iterdir()):
            if not production_root.is_dir() or _is_link(production_root):
                continue
            projects_root = production_root / "projects"
            for path in _direct_json_files(projects_root):
                relative = path.relative_to(production_root).as_posix()
                workspace_relative = path.relative_to(layout.workspace_root).as_posix()
                locations.append(
                    ProjectLocation(
                        identifier=f"production:{workspace_relative}",
                        absolute_path=path,
                        project_root=production_root.resolve(),
                        relative_path=relative,
                        kind="production",
                        label=f"Production / {production_root.name} / {path.stem}",
                        writable=True,
                    )
                )

    if layout.scratch_root.is_dir() and not _is_link(layout.scratch_root):
        for scratch_root in sorted(layout.scratch_root.iterdir()):
            if not scratch_root.is_dir() or _is_link(scratch_root):
                continue
            candidates = []
            direct_project = scratch_root / "project.json"
            if direct_project.is_file() and not _is_link(direct_project):
                candidates.append(direct_project.resolve())
            candidates.extend(_direct_json_files(scratch_root / "projects"))
            for path in sorted(set(candidates)):
                relative = path.relative_to(scratch_root.resolve()).as_posix()
                workspace_relative = path.relative_to(layout.workspace_root).as_posix()
                locations.append(
                    ProjectLocation(
                        identifier=f"scratch:{workspace_relative}",
                        absolute_path=path,
                        project_root=scratch_root.resolve(),
                        relative_path=relative,
                        kind="scratch",
                        label=f"Scratch / {scratch_root.name} / {path.stem}",
                        writable=True,
                    )
                )

    examples_root = layout.examples_root
    for path in _recursive_json_files(examples_root):
        relative = path.relative_to(layout.app_root).as_posix()
        locations.append(
            ProjectLocation(
                identifier=f"example:{relative}",
                absolute_path=path,
                project_root=layout.app_root,
                relative_path=relative,
                kind="example",
                label=f"Example / {path.stem}",
                writable=False,
            )
        )

    if include_legacy:
        for path in _direct_json_files(layout.app_root / "projects"):
            relative = path.relative_to(layout.app_root).as_posix()
            locations.append(
                ProjectLocation(
                    identifier=f"legacy:{relative}",
                    absolute_path=path,
                    project_root=layout.app_root,
                    relative_path=relative,
                    kind="legacy",
                    label=f"Legacy / {path.stem}",
                    writable=False,
                )
            )
    return tuple(locations)


def find_project_location(identifier, layout, *, include_legacy=True):
    identifier = str(identifier or "").strip()
    for location in discover_project_locations(
        layout,
        include_legacy=include_legacy,
    ):
        if location.identifier == identifier:
            return location
        if identifier == _location_portable_path(location, layout):
            return location
        if (
            location.kind in {"legacy", "example"}
            and identifier == location.relative_path
        ):
            return location
    raise WorkspacePathError(f"Project is not available in this workspace: {identifier}")


def project_location_from_path(path, layout):
    if not isinstance(layout, WorkspaceLayout):
        raise TypeError("layout must be a WorkspaceLayout.")
    resolved = Path(path).resolve(strict=True)
    for location in discover_project_locations(layout):
        if location.absolute_path == resolved:
            return location
    raise WorkspacePathError(f"Project path is outside known project roots: {resolved}")


def validate_slug(value):
    slug = str(value or "").strip().casefold()
    if not SLUG_PATTERN.fullmatch(slug):
        raise WorkspacePathError(
            "Workspace slugs must use lowercase letters, numbers, hyphens, or underscores."
        )
    return slug


def safe_slug(value, *, default="project"):
    slug = re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")
    slug = slug[:80] or default
    return slug if SLUG_PATTERN.fullmatch(slug) else default


def _settings_path(settings_path, *, environ=None):
    return (
        default_settings_path(environ=environ)
        if settings_path is None
        else _absolute_path(settings_path, label="settings_path")
    )


def _validate_settings_location(path, *, app_root):
    resolved = path.resolve(strict=False)
    if resolved == app_root or resolved.is_relative_to(app_root):
        raise WorkspacePathError(
            "Workspace settings must be stored outside APP_ROOT."
        )
    _reject_existing_links(path.parent)


def _create_user_directory(path, *, layout):
    target = assert_user_write_path(
        path,
        app_root=layout.app_root,
        workspace_root=layout.workspace_root,
        operation="Workspace initialization",
    )
    target.mkdir(parents=True, exist_ok=True)
    if _is_link(target) or not target.is_dir():
        raise WorkspacePathError(f"Workspace directory is unsafe: {target}")
    return target


def _direct_json_files(directory):
    if not directory.is_dir() or _is_link(directory):
        return ()
    return tuple(
        path.resolve()
        for path in sorted(directory.glob("*.json"))
        if path.is_file() and not _is_link(path)
    )


def _recursive_json_files(directory):
    if not directory.is_dir() or _is_link(directory):
        return ()
    files = []
    root = directory.resolve()
    for path in sorted(directory.rglob("*.json")):
        if not path.is_file() or _is_link(path):
            continue
        resolved = path.resolve()
        if resolved.is_relative_to(root):
            files.append(resolved)
    return tuple(files)


def _location_portable_path(location, layout):
    if location.kind in {"production", "scratch"}:
        return location.absolute_path.relative_to(layout.workspace_root).as_posix()
    return location.absolute_path.relative_to(layout.app_root).as_posix()


def _absolute_path(value, *, label):
    if value is None:
        raise WorkspacePathError(f"{label} is required.")
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw.strip():
        raise WorkspacePathError(f"{label} must be a non-empty path.")
    raw = raw.strip()
    portable = PurePosixPath(raw.replace("\\", "/"))
    windows = PureWindowsPath(raw)
    path = Path(raw).expanduser()
    if not path.is_absolute() or (windows.drive and not windows.root):
        raise WorkspacePathError(f"{label} must be an absolute path: {raw!r}")
    if ".." in portable.parts:
        raise WorkspacePathError(f"{label} must not contain '..' segments.")
    return Path(os.path.abspath(path))


def _existing_directory(value, *, label):
    path = _absolute_path(value, label=label).resolve(strict=True)
    if not path.is_dir():
        raise WorkspacePathError(f"{label} is not a directory: {path}")
    return path


def _paths_overlap(first, second):
    return (
        first == second
        or first.is_relative_to(second)
        or second.is_relative_to(first)
    )


def _reject_existing_links(path, *, stop_at=None):
    path = Path(path)
    stop = Path(stop_at).resolve(strict=False) if stop_at is not None else None
    current = path
    while True:
        if current.exists() and _is_link(current):
            raise WorkspacePathError(
                f"Path must not use symbolic links or junctions: {current}"
            )
        if stop is not None and current.resolve(strict=False) == stop:
            break
        if current == current.parent:
            break
        current = current.parent


def _is_link(path):
    path = Path(path)
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())
