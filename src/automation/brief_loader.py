from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from automation.models import DatasetBrief, FrozenParameters, JsonScalar, ProductionBrief
from automation.workspace import validate_job_id


PRODUCTION_BRIEF_SCHEMA_VERSION = 1
_TOP_LEVEL_FIELDS = frozenset(
    ("production_brief_schema_version", "job_id", "dataset")
)
_DATASET_FIELDS = frozenset(
    ("builder", "source_csv", "expected_source_sha256", "parameters")
)
_BUILDER_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_]{0,63}\Z")
_LOWERCASE_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_WINDOWS_DRIVE_PATTERN = re.compile(r"[a-zA-Z]:")


class ProductionBriefError(ValueError):
    pass


def validate_builder_id(builder_id: object) -> str:
    """Validate and return a stable dataset builder identifier."""
    if not isinstance(builder_id, str) or not _BUILDER_ID_PATTERN.fullmatch(
        builder_id
    ):
        raise ValueError(
            "builder_id must be 1-64 characters, begin with a lowercase "
            "letter or digit, and contain only lowercase letters, digits, "
            "or underscores."
        )
    return builder_id


def load_production_brief(
    brief_path: str | Path,
    *,
    root_dir: str | Path,
) -> ProductionBrief:
    brief_file = _resolve_brief_file(brief_path)
    authorized_root = _resolve_root_dir(root_dir)
    data = _read_strict_json(brief_file)
    _require_object(data, "production brief", brief_file)
    _reject_unknown_fields(data, _TOP_LEVEL_FIELDS, "production brief", brief_file)

    schema_version = _require_field(
        data,
        "production_brief_schema_version",
        "production brief",
        brief_file,
    )
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise _error(
            brief_file,
            "Field 'production_brief_schema_version' must be integer 1.",
        )
    if schema_version != PRODUCTION_BRIEF_SCHEMA_VERSION:
        raise _error(
            brief_file,
            "Unsupported production_brief_schema_version "
            f"{schema_version}; only version 1 is supported.",
        )

    job_id = _require_field(data, "job_id", "production brief", brief_file)
    try:
        validated_job_id = validate_job_id(job_id)
    except ValueError as exc:
        raise _error(brief_file, f"Invalid field 'job_id': {exc}") from exc

    dataset_data = _require_field(data, "dataset", "production brief", brief_file)
    _require_object(dataset_data, "dataset", brief_file)
    _reject_unknown_fields(dataset_data, _DATASET_FIELDS, "dataset", brief_file)

    builder_id = _validate_builder_id(
        _require_field(dataset_data, "builder", "dataset", brief_file),
        brief_file,
    )
    source_csv = _resolve_source_csv(
        _require_field(dataset_data, "source_csv", "dataset", brief_file),
        root_dir=authorized_root,
        brief_file=brief_file,
    )
    expected_sha256 = _validate_expected_sha256(
        dataset_data.get("expected_source_sha256"),
        brief_file,
    )
    parameters = _validate_parameters(
        _require_field(dataset_data, "parameters", "dataset", brief_file),
        brief_file,
    )

    return ProductionBrief(
        schema_version=schema_version,
        job_id=validated_job_id,
        dataset=DatasetBrief(
            builder_id=builder_id,
            source_csv=source_csv,
            expected_source_sha256=expected_sha256,
            parameters=parameters,
        ),
    )


def _resolve_brief_file(brief_path: str | Path) -> Path:
    try:
        path = Path(brief_path).resolve(strict=True)
    except (OSError, TypeError) as exc:
        raise ProductionBriefError(f"Production brief file not found: {brief_path}") from exc
    if not path.is_file():
        raise ProductionBriefError(f"Production brief path is not a file: {path}")
    return path


def _resolve_root_dir(root_dir: str | Path) -> Path:
    try:
        root = Path(root_dir).resolve(strict=True)
    except (OSError, TypeError) as exc:
        raise ProductionBriefError(f"root_dir does not exist: {root_dir}") from exc
    if not root.is_dir():
        raise ProductionBriefError(f"root_dir is not a directory: {root}")
    return root


def _read_strict_json(brief_file: Path) -> Any:
    try:
        raw_data = brief_file.read_bytes()
    except OSError as exc:
        raise _error(brief_file, "Could not read production brief.") from exc
    try:
        text = raw_data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _error(brief_file, "Production brief must use valid UTF-8.") from exc
    if not text.strip():
        raise _error(brief_file, "Production brief JSON is empty.")
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_non_json_constant,
        )
    except ProductionBriefError as exc:
        raise _error(brief_file, str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise _error(
            brief_file,
            f"Invalid production brief JSON: {exc.msg} at line {exc.lineno}, "
            f"column {exc.colno}.",
        ) from exc


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProductionBriefError(f"Duplicate JSON key: '{key}'.")
        result[key] = value
    return result


def _reject_non_json_constant(value: str) -> None:
    raise ProductionBriefError(f"Non-JSON numeric value is not allowed: {value}.")


def _require_object(value: Any, field: str, brief_file: Path) -> None:
    if not isinstance(value, dict):
        raise _error(brief_file, f"Field '{field}' must be a JSON object.")


def _reject_unknown_fields(
    data: dict,
    allowed: frozenset[str],
    location: str,
    brief_file: Path,
) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise _error(
            brief_file,
            f"Unknown field(s) in {location}: {', '.join(unknown)}.",
        )


def _require_field(data: dict, field: str, location: str, brief_file: Path) -> Any:
    if field not in data:
        raise _error(brief_file, f"Missing required field '{field}' in {location}.")
    return data[field]


def _validate_builder_id(value: Any, brief_file: Path) -> str:
    try:
        return validate_builder_id(value)
    except ValueError as exc:
        raise _error(
            brief_file,
            "Field 'dataset.builder' must be 1-64 characters, begin with a "
            "lowercase letter or digit, and contain only lowercase letters, "
            "digits, or underscores.",
        ) from exc


def _resolve_source_csv(
    value: Any,
    *,
    root_dir: Path,
    brief_file: Path,
) -> Path:
    if not isinstance(value, str) or not value:
        raise _error(brief_file, "Field 'dataset.source_csv' must be a non-empty string.")
    if "\\" in value:
        raise _error(brief_file, "Field 'dataset.source_csv' must use '/' separators.")
    if value.startswith("/") or value.startswith("//"):
        raise _error(brief_file, "Field 'dataset.source_csv' must be relative.")
    if _WINDOWS_DRIVE_PATTERN.match(value):
        raise _error(brief_file, "Field 'dataset.source_csv' must not use a Windows drive.")
    segments = value.split("/")
    if any(segment == "" for segment in segments):
        raise _error(brief_file, "Field 'dataset.source_csv' contains an empty segment.")
    if any(segment in (".", "..") for segment in segments):
        raise _error(
            brief_file,
            "Field 'dataset.source_csv' must not contain '.' or '..' segments.",
        )

    unresolved = root_dir.joinpath(*segments)
    try:
        resolved = unresolved.resolve(strict=True)
    except OSError as exc:
        raise _error(brief_file, f"Dataset source CSV does not exist: {value}") from exc
    if not resolved.is_relative_to(root_dir):
        raise _error(brief_file, "Dataset source CSV escapes root_dir.")
    if not resolved.is_file():
        raise _error(brief_file, f"Dataset source CSV is not a file: {value}")
    return resolved


def _validate_expected_sha256(value: Any, brief_file: Path) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _LOWERCASE_SHA256_PATTERN.fullmatch(value):
        raise _error(
            brief_file,
            "Field 'dataset.expected_source_sha256' must be null or exactly "
            "64 lowercase hexadecimal characters.",
        )
    return value


def _validate_parameters(value: Any, brief_file: Path) -> FrozenParameters:
    if not isinstance(value, dict):
        raise _error(brief_file, "Field 'dataset.parameters' must be a JSON object.")
    validated: dict[str, JsonScalar] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise _error(brief_file, "Dataset parameter keys must be non-empty strings.")
        if key != key.strip():
            raise _error(
                brief_file,
                f"Dataset parameter key '{key}' must not have outer whitespace.",
            )
        if item is not None and not isinstance(item, (str, int, float, bool)):
            raise _error(
                brief_file,
                f"Dataset parameter '{key}' must be a JSON scalar.",
            )
        if isinstance(item, float) and not math.isfinite(item):
            raise _error(
                brief_file,
                f"Dataset parameter '{key}' must be a finite JSON number.",
            )
        validated[key] = item
    return FrozenParameters.from_mapping(validated)


def _error(brief_file: Path, message: str) -> ProductionBriefError:
    return ProductionBriefError(f"Production brief '{brief_file}': {message}")
