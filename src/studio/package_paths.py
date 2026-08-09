import os
from pathlib import Path

from studio.workspace_paths import APP_ROOT


# Backward-compatible alias for callers that still read repository examples.
# New user flows must supply their production or scratch project root explicitly.
DEFAULT_PROJECT_ROOT = APP_ROOT


class ProjectPathError(ValueError):
    pass


def resolve_project_path(
    value,
    *,
    project_root,
    required=False,
    field_name=None,
    allow_absolute=True,
    reject_links=True,
):
    """Resolve a project path without depending on the process cwd."""
    label = field_name or "project path"
    raw_value = _path_value(value, label=label, required=required)
    if raw_value is None:
        return None

    root = _project_root(project_root)
    path = Path(raw_value.replace("\\", "/"))

    if path.is_absolute():
        if not allow_absolute:
            raise ProjectPathError(
                f"{label} must be portable and relative to project_root."
            )
        resolved = path.resolve()
        if reject_links:
            _reject_link_path(path)
        return resolved

    if path.anchor:
        raise ProjectPathError(
            f"{label} has an incomplete absolute path: {raw_value!r}."
        )

    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProjectPathError(
            f"{label} value {raw_value!r} escapes project root "
            f"{str(root)!r}; resolved path: {resolved}"
        ) from exc

    if reject_links:
        _reject_link_path(root / path, stop_at=root)

    return resolved


def _path_value(value, *, label, required):
    if value is None:
        if required:
            raise ProjectPathError(f"{label} is required; received None.")
        return None

    if not isinstance(value, (str, os.PathLike)):
        raise ProjectPathError(
            f"{label} must be a string or Path; received "
            f"{type(value).__name__}."
        )

    raw_value = os.fspath(value)
    if not isinstance(raw_value, str):
        raise ProjectPathError(
            f"{label} must be a string or Path; received "
            f"{type(raw_value).__name__}."
        )

    raw_value = raw_value.strip()
    if raw_value:
        return raw_value
    if required:
        raise ProjectPathError(f"{label} is required; received an empty value.")
    return None


def _project_root(project_root):
    raw_root = _path_value(
        project_root,
        label="project_root",
        required=True,
    )
    root = Path(raw_root.replace("\\", "/"))
    if not root.is_absolute():
        raise ProjectPathError(
            f"project_root must be absolute; received {raw_root!r}."
        )
    resolved = root.resolve()
    if _is_link(root):
        raise ProjectPathError(
            f"project_root must not be a symbolic link or junction: {root}"
        )
    return resolved


def _reject_link_path(path, *, stop_at=None):
    current = Path(path)
    stop = Path(stop_at).resolve() if stop_at is not None else None
    while True:
        if current.exists() and _is_link(current):
            raise ProjectPathError(
                f"Project paths must not use symbolic links or junctions: {current}"
            )
        if stop is not None and current.resolve() == stop:
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
