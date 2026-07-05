import argparse
from dataclasses import dataclass, replace

from config.project_preset import DEFAULT_PRESET_NAME, get_preset
from config.theme_config import get_theme
from config.value_format_config import get_value_format


@dataclass(frozen=True)
class CliOptions:
    preset_name: str = DEFAULT_PRESET_NAME
    list_presets: bool = False
    list_themes: bool = False
    list_value_formats: bool = False
    output_file: str | None = None
    frames_dir: str | None = None
    title: str | None = None
    theme_name: str | None = None
    value_format_name: str | None = None
    fps: int | None = None
    steps_per_transition: int | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None


def build_argument_parser():
    parser = argparse.ArgumentParser(
        prog="BarChartStudio",
        description="Render BarChartStudio videos from project presets.",
    )

    parser.add_argument(
        "preset",
        nargs="?",
        default=DEFAULT_PRESET_NAME,
        help=f"Preset to render. Default: {DEFAULT_PRESET_NAME}",
    )
    parser.add_argument(
        "--list-presets",
        "-l",
        action="store_true",
        help="List available project presets.",
    )
    parser.add_argument(
        "--list-themes",
        action="store_true",
        help="List available visual themes.",
    )
    parser.add_argument(
        "--list-value-formats",
        action="store_true",
        help="List available numeric value formats.",
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output_file",
        help="Override the output MP4 path.",
    )
    parser.add_argument(
        "--frames-dir",
        help="Override the temporary PNG frames directory.",
    )
    parser.add_argument(
        "--title",
        help="Override the chart title.",
    )
    parser.add_argument(
        "--theme",
        dest="theme_name",
        help="Override the preset visual theme.",
    )
    parser.add_argument(
        "--value-format",
        dest="value_format_name",
        help="Override the numeric value format.",
    )
    parser.add_argument(
        "--fps",
        type=_positive_int,
        help="Override video frames per second.",
    )
    parser.add_argument(
        "--steps-per-transition",
        "--steps",
        dest="steps_per_transition",
        type=_positive_int,
        help="Override generated frames per time transition.",
    )
    parser.add_argument(
        "--duration",
        type=_positive_float,
        help="Override seconds per time transition.",
    )
    parser.add_argument(
        "--width",
        type=_positive_int,
        help="Override render width in pixels.",
    )
    parser.add_argument(
        "--height",
        type=_positive_int,
        help="Override render height in pixels.",
    )

    return parser


def parse_cli_args(argv):
    parser = build_argument_parser()
    namespace = parser.parse_args(argv)

    if namespace.duration is not None and namespace.steps_per_transition is not None:
        parser.error("Use --duration or --steps-per-transition, not both.")

    return CliOptions(
        preset_name=namespace.preset,
        list_presets=namespace.list_presets,
        list_themes=namespace.list_themes,
        list_value_formats=namespace.list_value_formats,
        output_file=namespace.output_file,
        frames_dir=namespace.frames_dir,
        title=namespace.title,
        theme_name=namespace.theme_name,
        value_format_name=namespace.value_format_name,
        fps=namespace.fps,
        steps_per_transition=namespace.steps_per_transition,
        duration=namespace.duration,
        width=namespace.width,
        height=namespace.height,
    )


def build_preset_from_cli_options(options):
    preset = get_preset(options.preset_name)
    return apply_cli_overrides(preset, options)


def apply_cli_overrides(preset, options):
    chart_updates = {}

    if options.output_file is not None:
        chart_updates["output_file"] = options.output_file

    if options.frames_dir is not None:
        chart_updates["frames_dir"] = options.frames_dir

    if options.title is not None:
        chart_updates["title"] = options.title

    if options.theme_name is not None:
        chart_updates["theme"] = get_theme(options.theme_name)

    if options.value_format_name is not None:
        chart_updates["value_format"] = get_value_format(options.value_format_name)

    effective_fps = options.fps or preset.chart_config.fps

    if options.fps is not None:
        chart_updates["fps"] = options.fps

    if options.duration is not None and options.steps_per_transition is not None:
        raise ValueError("Use --duration or --steps-per-transition, not both.")

    if options.duration is not None:
        chart_updates["steps_per_transition"] = max(
            1,
            round(options.duration * effective_fps),
        )

    if options.steps_per_transition is not None:
        chart_updates["steps_per_transition"] = options.steps_per_transition

    if options.width is not None:
        chart_updates["width"] = options.width

    if options.height is not None:
        chart_updates["height"] = options.height

    if not chart_updates:
        return preset

    return replace(
        preset,
        chart_config=replace(preset.chart_config, **chart_updates),
    )


def _positive_int(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc

    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")

    return parsed


def _positive_float(value):
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc

    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")

    return parsed
