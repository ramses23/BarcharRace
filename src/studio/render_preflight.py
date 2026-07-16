import os
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from config.project_file_loader import ProjectFileError, load_project_file
from importers.data_source_loader import DataSourceLoader
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
    project_path = Path(project_file).resolve()
    root_path = Path(root_dir or Path.cwd()).resolve()
    checks = []

    try:
        preset = load_project_file(project_path)
    except (ProjectFileError, ValueError, OSError) as exc:
        checks.append(_error("project", "Project JSON", str(exc)))
        return RenderPreflight(str(project_path), tuple(checks))

    checks.append(_ok("project", "Project JSON", "Configuration is valid."))
    data_source_config = _absolute_data_source_config(
        preset.data_source_config,
        root_path,
    )

    try:
        dataframe = DataSourceLoader(data_source_config).load()
    except (ValueError, OSError) as exc:
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

    output_path = _resolve_path(preset.chart_config.output_file, root_path)
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
            csv_path=str(_resolve_path(config.csv_path, root_path)),
        )

    if config.source_type == "sqlite":
        return replace(
            config,
            sqlite_database_path=str(
                _resolve_path(config.sqlite_database_path, root_path)
            ),
        )

    return config


def _output_error(output_path, project_path, data_source_config):
    if output_path.suffix.lower() != ".mp4":
        return "Video output must use the .mp4 extension."

    if output_path == project_path:
        return "Video output cannot overwrite the project JSON."

    if data_source_config.source_type == "csv":
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
        background_path = _resolve_path(chart.background_image_path or "", root_path)
        if not chart.background_image_path or not background_path.is_file():
            checks.append(
                _error(
                    "background",
                    "Background image",
                    f"Image not found: {background_path}",
                )
            )
        else:
            checks.append(
                _ok("background", "Background image", str(background_path))
            )

    if chart.bar_texture_enabled and chart.bar_texture_preset == "custom_image":
        texture_path = _resolve_path(
            chart.bar_texture_custom_image or "",
            root_path,
        )
        if not chart.bar_texture_custom_image or not texture_path.is_file():
            checks.append(
                _error(
                    "texture",
                    "Custom texture",
                    f"Image not found: {texture_path}",
                )
            )
        else:
            checks.append(_ok("texture", "Custom texture", str(texture_path)))

    logo_paths = (
        *preset.dataset_config.category_logos.values(),
        *preset.dataset_config.category_secondary_logos.values(),
    )
    missing_logos = [
        path
        for path in logo_paths
        if path and not _resolve_path(path, root_path).is_file()
    ]
    if missing_logos:
        checks.append(
            PreflightCheck(
                key="logos",
                label="Category logos",
                level="warning",
                message=f"{len(missing_logos)} logo files were not found.",
            )
        )

    return checks


def _resolve_path(path, root_path):
    resolved = Path(str(path).strip())
    if not resolved.is_absolute():
        resolved = root_path / resolved
    return resolved.resolve()


def _ok(key, label, message):
    return PreflightCheck(key=key, label=label, level="ok", message=message)


def _error(key, label, message):
    return PreflightCheck(key=key, label=label, level="error", message=message)
