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

from src.studio.production_package_binding import (
    load_production_package_binding,
    resolve_linked_project,
    write_production_package_binding,
)
from src.studio.project_bundle import (
    import_project_bundle,
    inspect_project_bundle,
)
from src.studio.workspace_paths import (
    WORKSPACE_ROOT_ENV,
    load_workspace_settings,
    validate_workspace_root,
)
from src.utils.file_size import format_file_size


AUTOLOAD_PROJECT_ENV = "BARCHARTSTUDIO_AUTOLOAD_PROJECT"
AUTOLOAD_TOKEN_ENV = "BARCHARTSTUDIO_AUTOLOAD_TOKEN"
PROJECT_STUDIO_PATH = Path("src") / "ui" / "project_studio.py"
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_INTERRUPTED = 130


def build_parser():
    parser = argparse.ArgumentParser(
        prog="open_production_package",
        description=(
            "Open the editable project linked to a BarChartStudio production "
            "package, importing it on first use."
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
            "Legacy BarChartStudio root compatibility. New imports should use "
            "--workspace."
        ),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help=(
            "User workspace root. Defaults to the configured BarChartStudio "
            "workspace."
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
    binding_action = parser.add_mutually_exclusive_group()
    binding_action.add_argument(
        "--reimport",
        action="store_true",
        help="Import the package again and replace its editable-project binding.",
    )
    binding_action.add_argument(
        "--adopt-project",
        type=Path,
        metavar="PROJECT_PATH",
        help=(
            "Link an existing JSON project inside a workspace production "
            "without importing the package."
        ),
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Prepare or validate the linked project without starting Studio.",
    )
    return parser


def run_from_options(options):
    root = _resolved_root(options.root)
    legacy_mode = options.root is not None and options.workspace is None
    workspace = None if legacy_mode else _resolved_workspace(options.workspace, root)
    package_path = options.package_path.resolve(strict=True)
    inspection = inspect_project_bundle(package_path)

    if options.adopt_project is not None:
        project = resolve_linked_project(
            options.adopt_project,
            **_binding_roots(root, workspace),
        )
        binding = write_production_package_binding(
            package_path,
            **_binding_roots(root, workspace),
            project_path=project.absolute_path,
            package_manifest_sha256=inspection.manifest_sha256,
        )
        _print_adoption_summary(binding)
    elif options.reimport:
        imported = import_project_bundle(
            package_path,
            **_import_roots(root, workspace),
        )
        binding = write_production_package_binding(
            package_path,
            **_binding_roots(root, workspace),
            project_path=imported.project_path,
            package_manifest_sha256=inspection.manifest_sha256,
        )
        _print_reimport_summary(binding)
    else:
        binding = load_production_package_binding(
            package_path,
            **_binding_roots(root, workspace),
            package_manifest_sha256=inspection.manifest_sha256,
        )
        if binding is None:
            imported = import_project_bundle(
                package_path,
                **_import_roots(root, workspace),
            )
            binding = write_production_package_binding(
                package_path,
                **_binding_roots(root, workspace),
                project_path=imported.project_path,
                package_manifest_sha256=inspection.manifest_sha256,
            )
            _print_import_summary(
                binding=binding,
                file_count=imported.file_count,
                uncompressed_size=imported.uncompressed_size,
            )
        else:
            _print_reopen_summary(binding)

    if options.no_launch:
        return EXIT_SUCCESS

    return launch_project_studio(
        root=root,
        project_relative=binding.project.relative_path,
        workspace_root=workspace,
        port=options.port,
        headless=options.headless,
    )


def launch_project_studio(
    *,
    root,
    project_relative,
    workspace_root=None,
    port,
    headless,
):
    environment = os.environ.copy()
    environment[AUTOLOAD_PROJECT_ENV] = project_relative
    environment[AUTOLOAD_TOKEN_ENV] = uuid4().hex
    if workspace_root is not None:
        environment[WORKSPACE_ROOT_ENV] = str(workspace_root)
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        PROJECT_STUDIO_PATH.as_posix(),
        f"--server.port={port}",
        f"--server.headless={'true' if headless else 'false'}",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=environment,
            check=False,
            shell=False,
        )
    except KeyboardInterrupt:
        print("Project Studio stopped by user.", file=sys.stderr)
        return EXIT_INTERRUPTED
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


def _resolved_workspace(value, app_root):
    if value is None:
        return load_workspace_settings(app_root=app_root).workspace_root
    return validate_workspace_root(value, app_root=app_root)


def _binding_roots(root, workspace):
    return (
        {"root_dir": root}
        if workspace is None
        else {"workspace_root": workspace, "app_root": root}
    )


def _import_roots(root, workspace):
    return (
        {"root_dir": root}
        if workspace is None
        else {"workspace_root": workspace, "app_root": root}
    )


def _print_import_summary(*, binding, file_count, uncompressed_size):
    print("Production package imported")
    _print_project(binding)
    print(f"Imported files: {file_count:,}")
    print(f"Imported size: {format_file_size(uncompressed_size)}")
    print(f"Binding created: {binding.state_path}")


def _print_reopen_summary(binding):
    print("Production package already linked")
    _print_project(binding)
    print(f"Binding: {binding.state_path}")
    print("No package import was performed")


def _print_adoption_summary(binding):
    print("Existing project adopted")
    _print_project(binding)
    print(f"Binding created: {binding.state_path}")


def _print_reimport_summary(binding):
    print("Production package reimported")
    _print_project(binding)
    print(f"Binding updated: {binding.state_path}")


def _print_project(binding):
    print(f"Project: {binding.project.name}")
    print(f"Editable path: {binding.project.relative_path}")


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
