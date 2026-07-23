import os
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from config.project_file_loader import ProjectFileError, load_project_file
from importers.data_source_loader import DataSourceLoader
from studio.package_paths import (
    DEFAULT_PROJECT_ROOT,
    ProjectPathError,
    resolve_project_path,
)
from validators.dataset_validator import DatasetValidator


@dataclass(frozen=True)
class PreflightCheck:
    key: str
    label: str
    level: str
    message: str

    def as_dict(self):
        return {
            "key": self.key,
            "label": self.label,
            "level": self.level,
            "message": self.message,
        }


@dataclass(frozen=True)
class RenderPreflight:
    project_file: str
    checks: tuple[PreflightCheck, ...]

    @property
    def ready(self):
        return all(check.level != "error" for check in self.checks)

    def as_dict(self):
        return {
            "project_file": self.project_file,
            "ready": self.ready,
            "checks": [check.as_dict() for check in self.checks],
        }


def run_render_preflight(project_file, *, root_dir=None, ffmpeg_path=None):
    checks = []

    try:
        root_path = _project_root(root_dir)
        project_path = resolve_project_path(
            project_file,
            project_root=root_path,
            required=True,
            field_name="project file",
        )
    except ProjectPathError as exc:
        checks.append(_error("project", "Project JSON", str(exc)))
        return RenderPreflight(str(project_file), tuple(checks))

    try:
        preset = load_project_file(project_path)
    except (ProjectFileError, ValueError, OSError) as exc:
        checks.append(_error("project", "Project JSON", str(exc)))
        return RenderPreflight(str(project_path), tuple(checks))

    checks.append(_ok("project", "Project JSON", "Configuration is valid."))
    try:
        data_source_config = _absolute_data_source_config(
            preset.data_source_config,
            root_path,
        )
        dataframe = DataSourceLoader(data_source_config).load()
    except (ProjectPathError, ValueError, OSError) as exc:
        data_source_config = None
        checks.append(_error("data_source", "Data source", str(exc)))
    else:
        checks.append(
            _ok(
                "data_source",
                "Data source",
                f"Loaded {len(dataframe):,} rows.",
            )
        )

        try:
            validated = DatasetValidator(
                config=preset.dataset_config
            ).validate(dataframe)
        except (ValueError, OSError) as exc:
            checks.append(_error("dataset", "Dataset", str(exc)))
        else:
            checks.append(_ok("dataset", "Dataset", "Required columns are valid."))
            period_count = int(
                validated[preset.dataset_config.year_column].nunique()
            )
            if period_count < 2:
                checks.append(
                    _error(
                        "periods",
                        "Timeline",
                        "At least two distinct time periods are required.",
                    )
                )
            else:
                checks.append(
                    _ok(
                        "periods",
                        "Timeline",
                        f"{period_count:,} distinct time periods.",
                    )
                )

    configured_ffmpeg = (
        shutil.which("ffmpeg") if ffmpeg_path is None else ffmpeg_path
    )
    if configured_ffmpeg:
        checks.append(
            _ok("ffmpeg", "FFmpeg", f"Available at {configured_ffmpeg}.")
        )
    else:
        checks.append(
            _error(
                "ffmpeg",
                "FFmpeg",
                "FFmpeg was not found on PATH.",
            )
        )

    try:
        output_path = resolve_project_path(
            preset.chart_config.output_file,
            project_root=root_path,
            required=True,
            field_name="chart.output_file",
        )
    except ProjectPathError as exc:
        checks.append(_error("output", "Video output", str(exc)))
    else:
        output_error = _output_error(output_path, project_path, data_source_config)
        if output_error:
            checks.append(_error("output", "Video output", output_error))
        else:
            checks.append(_ok("output", "Video output", str(output_path)))

    checks.extend(_asset_checks(preset, root_path))
    return RenderPreflight(str(project_path), tuple(checks))


def _absolute_data_source_config(config, root_path):
    if config.source_type == "csv":
        return replace(
            config,
            csv_path=str(
                resolve_project_path(
                    config.csv_path,
                    project_root=root_path,
                    required=True,
                    field_name="data_source.csv_path",
                )
            ),
        )

    if config.source_type == "sqlite":
        return replace(
            config,
            sqlite_database_path=str(
                resolve_project_path(
                    config.sqlite_database_path,
                    project_root=root_path,
                    required=True,
                    field_name="data_source.sqlite_database_path",
                )
            ),
        )

    return config


def _output_error(output_path, project_path, data_source_config):
    if output_path.suffix.lower() != ".mp4":
        return "Video output must use the .mp4 extension."

    if output_path == project_path:
        return "Video output cannot overwrite the project JSON."

    if data_source_config is not None and data_source_config.source_type == "csv":
        input_path = Path(data_source_config.csv_path).resolve()
        if output_path == input_path:
            return "Video output cannot overwrite the source CSV."

    existing_parent = output_path.parent
    while not existing_parent.exists() and existing_parent != existing_parent.parent:
        existing_parent = existing_parent.parent

    if not existing_parent.exists() or not os.access(existing_parent, os.W_OK):
        return f"Output directory is not writable: {output_path.parent}"

    return None


def _asset_checks(preset, root_path):
    checks = []
    chart = preset.chart_config

    if chart.background_mode == "image":
        checks.append(
            _image_asset_check(
                key="background",
                label="Background image",
                field_name="chart.background_image_path",
                value=chart.background_image_path,
                root_path=root_path,
            )
        )

    if chart.bar_texture_enabled and chart.bar_texture_preset == "custom_image":
        checks.append(
            _image_asset_check(
                key="texture",
                label="Custom texture",
                field_name="chart.bar_texture_custom_image",
                value=chart.bar_texture_custom_image,
                root_path=root_path,
            )
        )

    missing_logos = _missing_logo_messages(preset.dataset_config, root_path)
    if missing_logos:
        checks.append(
            PreflightCheck(
                key="logos",
                label="Category logos",
                level="warning",
                message="; ".join(missing_logos),
            )
        )

    return checks


def _project_root(root_dir):
    return resolve_project_path(
        root_dir if root_dir is not None else DEFAULT_PROJECT_ROOT,
        project_root=DEFAULT_PROJECT_ROOT,
        required=True,
        field_name="project root",
    )


def _image_asset_check(*, key, label, field_name, value, root_path):
    try:
        resolved = resolve_project_path(
            value,
            project_root=root_path,
            required=True,
            field_name=field_name,
        )
    except ProjectPathError as exc:
        return _error(key, label, str(exc))

    if not resolved.is_file():
        return _error(
            key,
            label,
            f"Image not found for {field_name}: value={value!r}; "
            f"resolved path: {resolved}",
        )
    return _ok(key, label, str(resolved))


def _missing_logo_messages(dataset_config, root_path):
    messages = []
    logo_maps = (
        ("dataset.category_logos", dataset_config.category_logos),
        (
            "dataset.category_secondary_logos",
            dataset_config.category_secondary_logos,
        ),
    )
    for field_name, values in logo_maps:
        for category, value in sorted(values.items()):
            item_name = f"{field_name}[{category!r}]"
            try:
                resolved = resolve_project_path(
                    value,
                    project_root=root_path,
                    required=True,
                    field_name=item_name,
                )
            except ProjectPathError as exc:
                messages.append(str(exc))
                continue
            if not resolved.is_file():
                messages.append(
                    f"Logo not found for category {category!r} in {field_name}: "
                    f"value={value!r}; resolved path: {resolved}"
                )
    return messages


def _ok(key, label, message):
    return PreflightCheck(key=key, label=label, level="ok", message=message)


def _error(key, label, message):
    return PreflightCheck(key=key, label=label, level="error", message=message)
