from pathlib import Path

from cli.cli_options import build_preset_from_cli_options, parse_cli_args
from config.animation_config import list_easings
from config.layout_config import list_layout_presets
from config.project_file_loader import ProjectFileError
from config.project_preset import (
    DEFAULT_PRESET_NAME,
    PresetError,
    get_preset,
    list_presets,
)
from config.theme_config import list_themes
from config.typography_config import list_typography_presets
from config.value_format_config import list_value_formats
from pipeline.render_job import RenderJob
from studio.project_runtime import resolve_project_preset_paths
from studio.workspace_paths import (
    APP_ROOT,
    WorkspaceLayout,
    initialize_workspace,
    project_location_from_path,
    safe_slug,
    validate_workspace_root,
    workspace_layout,
)


def run(
    config=None,
    data_source_config=None,
    dataset_config=None,
    fun_fact_config=None,
    project_root=None,
):
    return RenderJob(
        config=config,
        data_source_config=data_source_config,
        dataset_config=dataset_config,
        fun_fact_config=fun_fact_config,
        project_root=project_root,
    ).run()


def run_preset(preset_name=DEFAULT_PRESET_NAME):
    preset = get_preset(preset_name)
    layout = initialize_workspace(
        workspace_layout(app_root=APP_ROOT).workspace_root,
        app_root=APP_ROOT,
    )
    output_root = layout.scratch_project_root(
        f"preset_{safe_slug(preset.name)}",
        create=True,
    )
    preset = resolve_project_preset_paths(
        preset,
        project_root=APP_ROOT,
        output_root=output_root,
        app_root=APP_ROOT,
    )
    return run_project_preset(preset, project_root=APP_ROOT)


def run_project_preset(preset, *, project_root=None):
    print(f"Preset activo: {preset.name}")

    return run(
        config=preset.chart_config,
        data_source_config=preset.data_source_config,
        dataset_config=preset.dataset_config,
        fun_fact_config=preset.fun_fact_config,
        project_root=project_root,
    )


def main(argv=None):
    options = parse_cli_args(argv)

    if options.list_presets:
        _print_items("Presets disponibles:", list_presets())
        return

    if options.list_themes:
        _print_items("Temas disponibles:", list_themes())
        return

    if options.list_layouts:
        _print_items("Layouts disponibles:", list_layout_presets())
        return

    if options.list_value_formats:
        _print_items("Formatos disponibles:", list_value_formats())
        return

    if options.list_typographies:
        _print_items("Tipografias disponibles:", list_typography_presets())
        return

    if options.list_easings:
        _print_items("Easings disponibles:", list_easings())
        return

    try:
        preset = build_preset_from_cli_options(options)
    except (PresetError, ProjectFileError, ValueError) as exc:
        print(exc)
        print(
            "Usa --list-presets, --list-themes, --list-layouts, "
            "--list-value-formats o --list-typographies."
        )
        raise SystemExit(2) from exc

    project_root = _cli_project_root(options)
    if options.project_file is not None:
        output_root = project_root
        if project_root == APP_ROOT:
            layout = initialize_workspace(
                _configured_workspace_layout(options).workspace_root,
                app_root=APP_ROOT,
            )
            output_root = layout.scratch_project_root(
                f"legacy_{safe_slug(Path(options.project_file).stem)}",
                create=True,
            )
        preset = resolve_project_preset_paths(
            preset,
            project_root=project_root,
            output_root=output_root,
            app_root=APP_ROOT,
        )
    else:
        layout = _configured_workspace_layout(options)
        layout = initialize_workspace(
            layout.workspace_root,
            app_root=APP_ROOT,
        )
        output_root = layout.scratch_project_root(
            f"preset_{safe_slug(preset.name)}",
            create=True,
        )
        project_root = APP_ROOT
        preset = resolve_project_preset_paths(
            preset,
            project_root=APP_ROOT,
            output_root=output_root,
            app_root=APP_ROOT,
        )
    run_project_preset(preset, project_root=project_root)


def _print_items(title, items):
    print(title)
    for item in items:
        print(f"- {item}")


def _cli_project_root(options):
    if options.production_root is not None:
        root = Path(options.production_root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise NotADirectoryError(f"production_root is not a directory: {root}")
        if options.project_file is not None:
            project_path = Path(options.project_file).expanduser().resolve(strict=True)
            if not project_path.is_relative_to(root):
                raise ValueError(
                    "The project file must remain inside production_root."
                )
        return root
    if options.project_file is None:
        return None

    project_path = Path(options.project_file).expanduser().resolve(strict=True)
    configured_layout = _configured_workspace_layout(options)
    try:
        return project_location_from_path(project_path, configured_layout).project_root
    except ValueError:
        if project_path.is_relative_to(APP_ROOT):
            return APP_ROOT
        return project_path.parent


def _configured_workspace_layout(options):
    if options.workspace_root is None:
        return workspace_layout(app_root=APP_ROOT)
    return WorkspaceLayout(
        app_root=APP_ROOT,
        workspace_root=validate_workspace_root(
            options.workspace_root,
            app_root=APP_ROOT,
        ),
    )


if __name__ == "__main__":
    main()
