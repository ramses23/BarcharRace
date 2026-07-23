import argparse
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = DEFAULT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.studio.project_bundle import import_project_bundle
from src.utils.file_size import format_file_size


AUTOLOAD_PROJECT_ENV = "BARCHARTSTUDIO_AUTOLOAD_PROJECT"
AUTOLOAD_TOKEN_ENV = "BARCHARTSTUDIO_AUTOLOAD_TOKEN"
PROJECT_STUDIO_PATH = Path("src") / "ui" / "project_studio.py"
EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def build_parser():
    parser = argparse.ArgumentParser(
        prog="open_production_package",
        description=(
            "Import a BarChartStudio production package and open its editable "
            "project in Project Studio."
        ),
    )
    parser.add_argument(
        "package_path",
        metavar="PACKAGE_PATH",
        type=Path,
        help="Path to a production ZIP or extracted package folder.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        help=(
            "BarChartStudio root. Defaults to the root containing this module."
        ),
    )
    parser.add_argument(
        "--port",
        type=_port_number,
        default=8501,
        help="Streamlit server port. Default: 8501.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Start Streamlit without opening a browser automatically.",
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Import the package without starting Project Studio.",
    )
    return parser


def run_from_options(options):
    root = _resolved_root(options.root)
    package_path = options.package_path.resolve(strict=True)
    imported = import_project_bundle(package_path, root_dir=root)
    project_path = Path(imported.project_path).resolve(strict=True)
    project_relative = project_path.relative_to(root).as_posix()

    _print_import_summary(
        project_relative=project_relative,
        file_count=imported.file_count,
        uncompressed_size=imported.uncompressed_size,
    )
    if options.no_launch:
        return EXIT_SUCCESS

    return launch_project_studio(
        root=root,
        project_relative=project_relative,
        port=options.port,
        headless=options.headless,
    )


def launch_project_studio(*, root, project_relative, port, headless):
    environment = os.environ.copy()
    environment[AUTOLOAD_PROJECT_ENV] = project_relative
    environment[AUTOLOAD_TOKEN_ENV] = uuid4().hex
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        PROJECT_STUDIO_PATH.as_posix(),
        f"--server.port={port}",
        f"--server.headless={'true' if headless else 'false'}",
    ]
    completed = subprocess.run(
        command,
        cwd=root,
        env=environment,
        check=False,
        shell=False,
    )
    return completed.returncode


def main(argv=None):
    options = build_parser().parse_args(argv)
    try:
        return run_from_options(options)
    except Exception as exc:
        print(
            f"Could not open production package: {exc}",
            file=sys.stderr,
        )
        return EXIT_FAILURE


def _resolved_root(value):
    root = DEFAULT_ROOT if value is None else value
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"BarChartStudio root is not a directory: {root}")
    return root


def _print_import_summary(*, project_relative, file_count, uncompressed_size):
    print("Production package imported")
    print(f"Project: {Path(project_relative).stem}")
    print(f"Editable path: {project_relative}")
    print(f"Imported files: {file_count:,}")
    print(f"Imported size: {format_file_size(uncompressed_size)}")


def _port_number(value):
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be from 1 to 65535")
    return port


if __name__ == "__main__":
    raise SystemExit(main())
