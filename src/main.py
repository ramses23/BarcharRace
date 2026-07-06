from cli.cli_options import build_preset_from_cli_options, parse_cli_args
from config.animation_config import list_easings
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


def run(config=None, data_source_config=None, dataset_config=None):
    return RenderJob(
        config=config,
        data_source_config=data_source_config,
        dataset_config=dataset_config,
    ).run()


def run_preset(preset_name=DEFAULT_PRESET_NAME):
    preset = get_preset(preset_name)
    return run_project_preset(preset)


def run_project_preset(preset):
    print(f"Preset activo: {preset.name}")

    return run(
        config=preset.chart_config,
        data_source_config=preset.data_source_config,
        dataset_config=preset.dataset_config,
    )


def main(argv=None):
    options = parse_cli_args(argv)

    if options.list_presets:
        _print_items("Presets disponibles:", list_presets())
        return

    if options.list_themes:
        _print_items("Temas disponibles:", list_themes())
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
            "Usa --list-presets, --list-themes, --list-value-formats "
            "o --list-typographies."
        )
        raise SystemExit(2) from exc

    run_project_preset(preset)


def _print_items(title, items):
    print(title)
    for item in items:
        print(f"- {item}")


if __name__ == "__main__":
    main()
