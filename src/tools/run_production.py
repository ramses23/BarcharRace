import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from automation.brief_loader import load_production_brief
from automation.logo_resolver import LocalLogoResolver
from automation.orchestrator import ProductionOrchestrator
from automation.production_preflight import ProductionPreflightRunner
from automation.project_assembler import ProductionProjectAssembler
from automation.registry import create_default_dataset_builder_registry
from automation.render_executor import ProductionRenderExecutor


EXIT_SUCCESS = 0
EXIT_TECHNICAL_FAILURE = 1
EXIT_BLOCKED = 2
EXIT_CANCELED = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_production",
        description="Run one local BarChartStudio production brief v2.",
    )
    parser.add_argument(
        "--brief",
        required=True,
        type=Path,
        help="Production brief v2 JSON path, relative to --root or absolute.",
    )
    parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="BarChartStudio project root containing all referenced inputs.",
    )
    return parser


def create_production_orchestrator() -> ProductionOrchestrator:
    return ProductionOrchestrator(
        create_default_dataset_builder_registry(),
        logo_resolver_component=LocalLogoResolver(),
        project_assembler_component=ProductionProjectAssembler(),
        preflight_runner_component=ProductionPreflightRunner(),
        render_executor_factory=ProductionRenderExecutor,
    )


def run_from_options(options: argparse.Namespace):
    root = options.root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Production root is not a directory: {root}")
    brief_path = options.brief
    if not brief_path.is_absolute():
        brief_path = root / brief_path
    brief_path = brief_path.resolve(strict=True)
    brief = load_production_brief(brief_path, root_dir=root)
    orchestrator = create_production_orchestrator()
    return orchestrator.run_production(
        brief,
        project_root_dir=root,
        workspace_root_dir=(root / "output" / ".production_jobs").resolve(),
        source_root_dir=root,
        progress_callback=print_progress,
    )


def print_progress(progress) -> None:
    detail = ""
    if progress.total:
        detail = f" ({progress.current:,}/{progress.total:,})"
    print(f"[{progress.state}] {progress.message}{detail}", flush=True)


def print_result(result) -> None:
    print("\nProduction result")
    print(f"State: {result.status}")
    print(f"Workspace: {result.workspace.root_path}")
    print(f"Project: {result.assembly_result.project_path}")
    print(
        "Preflight: "
        f"{result.preflight_result.status} "
        f"({result.preflight_result.manifest_path})"
    )
    if result.render_result is not None and result.render_result.status == "completed":
        print(f"MP4: {result.render_result.video_path}")
    else:
        print("MP4: not produced")


def exit_code_for_status(status: str) -> int:
    return {
        "completed": EXIT_SUCCESS,
        "preflight_ready": EXIT_SUCCESS,
        "blocked": EXIT_BLOCKED,
        "canceled": EXIT_CANCELED,
    }.get(status, EXIT_TECHNICAL_FAILURE)


def main(argv=None) -> int:
    options = build_parser().parse_args(argv)
    try:
        result = run_from_options(options)
    except Exception as exc:
        print(f"Production failed: {exc}", file=sys.stderr)
        return EXIT_TECHNICAL_FAILURE

    print_result(result)
    return exit_code_for_status(result.status)


if __name__ == "__main__":
    raise SystemExit(main())
