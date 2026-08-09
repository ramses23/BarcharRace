from dataclasses import replace
from pathlib import Path

from studio.package_paths import ProjectPathError, resolve_project_path
from studio.workspace_paths import assert_user_write_path


def resolve_project_preset_paths(
    preset,
    *,
    project_root,
    output_root=None,
    app_root=None,
):
    """Resolve one project's portable paths against its explicit roots."""
    project_root = Path(project_root).resolve()
    output_root = Path(output_root or project_root).resolve()
    data_source = _resolved_data_source_config(
        preset.data_source_config,
        project_root,
    )
    dataset = replace(
        preset.dataset_config,
        category_logos=_resolved_path_map(
            preset.dataset_config.category_logos,
            project_root=project_root,
            field_name="dataset.category_logos",
        ),
        category_secondary_logos=_resolved_path_map(
            preset.dataset_config.category_secondary_logos,
            project_root=project_root,
            field_name="dataset.category_secondary_logos",
        ),
    )
    chart = preset.chart_config
    output_file = resolve_project_output_path(
        chart.output_file,
        output_root=output_root,
        field_name="chart.output_file",
    )
    frames_dir = resolve_project_output_path(
        chart.frames_dir,
        output_root=output_root,
        field_name="chart.frames_dir",
    )
    if app_root is not None:
        output_file = assert_user_write_path(
            output_file,
            app_root=app_root,
            operation="Video render",
        )
        frames_dir = assert_user_write_path(
            frames_dir,
            app_root=app_root,
            operation="Frame render",
        )
    background = resolve_project_path(
        chart.background_image_path,
        project_root=project_root,
        required=chart.background_mode == "image",
        field_name="chart.background_image_path",
    )
    texture = resolve_project_path(
        chart.bar_texture_custom_image,
        project_root=project_root,
        required=(
            chart.bar_texture_enabled
            and chart.bar_texture_preset == "custom_image"
        ),
        field_name="chart.bar_texture_custom_image",
    )
    logos_dir = resolve_project_path(
        chart.logos_dir,
        project_root=project_root,
        required=True,
        field_name="chart.logos_dir",
    )
    chart = replace(
        chart,
        output_file=str(output_file),
        frames_dir=str(frames_dir),
        background_image_path=str(background) if background is not None else None,
        bar_texture_custom_image=str(texture) if texture is not None else None,
        logos_dir=str(logos_dir),
    )
    return replace(
        preset,
        chart_config=chart,
        data_source_config=data_source,
        dataset_config=dataset,
    )


def _resolved_data_source_config(config, project_root):
    if config.source_type == "csv":
        return replace(
            config,
            csv_path=str(
                resolve_project_path(
                    config.csv_path,
                    project_root=project_root,
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
                    project_root=project_root,
                    required=True,
                    field_name="data_source.sqlite_database_path",
                )
            ),
        )
    return config


def _resolved_path_map(values, *, project_root, field_name):
    return {
        category: str(
            resolve_project_path(
                value,
                project_root=project_root,
                required=True,
                field_name=f"{field_name}[{category!r}]",
            )
        )
        for category, value in values.items()
    }


def resolve_project_output_path(value, *, output_root, field_name):
    raw_value = str(value or "").strip()
    if not raw_value:
        raise ValueError(f"{field_name} is required.")
    root = Path(output_root).resolve(strict=True)
    resolved = resolve_project_path(
        raw_value,
        project_root=root,
        required=True,
        field_name=field_name,
    )
    if not resolved.is_relative_to(root):
        raise ProjectPathError(
            f"{field_name} must remain inside output_root: {root}"
        )
    return resolved
