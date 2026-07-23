import os
from pathlib import Path


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ProjectPathError(ValueError):
    pass


def resolve_project_path(
    value,
    *,
    project_root,
    required=False,
    field_name=None,
):
    """Resolve a project path without depending on the process cwd."""
    label = field_name or "project path"
    raw_value = _path_value(value, label=label, required=required)
    if raw_value is None:
        return None

    root = _project_root(project_root)
    path = Path(raw_value.replace("\\", "/"))

    if path.is_absolute():
        return path.resolve()

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
    return root.resolve()
