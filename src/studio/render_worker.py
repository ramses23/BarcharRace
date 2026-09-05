import argparse
import sys
import traceback
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path
from time import monotonic


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config.project_file_loader import load_project_file
from pipeline.render_job import RenderJob
from studio.package_paths import ProjectPathError, resolve_project_path
from studio.project_runtime import resolve_project_preset_paths
from studio.project_storage import atomic_write_json
from studio.render_output import (
    RenderOutputPromotionError,
    promote_render_output,
    temporary_render_output_path,
)
from studio.short_export import resolve_export_output_path
from studio.workspace_paths import load_workspace_settings
from utils.cpu_limiter import CpuLimitConfig


def run_worker(
    project_file,
    root_dir,
    status_file,
    job_id,
    *,
    output_root=None,
    app_root=None,
):
    root_path = Path(root_dir).resolve()
    project_path = resolve_project_path(
        project_file,
        project_root=root_path,
        required=True,
        field_name="project file",
    )
    if not project_path.is_relative_to(root_path):
        raise ProjectPathError(
            f"Project file must remain inside project_root: {root_path}"
        )
    status_path = Path(status_file).resolve()
    preset = load_project_file(project_path)
    if is_dataclass(preset):
        preset = resolve_project_preset_paths(
            preset,
            project_root=root_path,
            output_root=Path(output_root).resolve() if output_root else root_path,
            app_root=Path(app_root).resolve() if app_root else None,
        )
        final_output = Path(preset.chart_config.output_file)
    else:
        final_output = _resolve_path(preset.chart_config.output_file, root_path)
    final_output = resolve_export_output_path(
        final_output,
        getattr(preset, "export_config", None),
    )
    final_output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = temporary_render_output_path(final_output)
    base_status = {
        "job_id": job_id,
        "state": "running",
        "stage": "starting",
        "message": "Preparing render.",
        "progress": 0.0,
        "current": 0,
        "total": 0,
        "project_file": str(project_path),
        "output_file": str(final_output),
        "temporary_output": str(temporary_output),
    }
    atomic_write_json(base_status, status_path)
    callback = _progress_writer(status_path, base_status)
    chart_config = replace(
        preset.chart_config,
        output_file=str(temporary_output),
    )
    settings = load_workspace_settings(
        app_root=Path(app_root).resolve() if app_root else SRC_DIR.parent,
    )
    cpu_limit_config = CpuLimitConfig(
        enabled=settings.render_cpu_limit_enabled,
        percent=settings.render_cpu_limit_percent,
    )

    try:
        result = RenderJob(
            config=chart_config,
            data_source_config=preset.data_source_config,
            dataset_config=preset.dataset_config,
            fun_fact_config=getattr(preset, "fun_fact_config", None),
            export_config=getattr(preset, "export_config", None),
            project_root=root_path,
            progress_callback=callback,
            cpu_limit_config=cpu_limit_config,
            output_file_is_effective=True,
        ).run()
        promote_render_output(temporary_output, final_output)
        result = replace(result, output_file=str(final_output))
        completed_status = {
            **base_status,
            "state": "completed",
            "stage": "complete",
            "message": "Video rendered successfully.",
            "progress": 1.0,
            "result": asdict(result),
        }
        atomic_write_json(completed_status, status_path)
        return 0
    except BaseException as exc:
        promotion_failed = isinstance(exc, RenderOutputPromotionError)
        if not promotion_failed:
            temporary_output.unlink(missing_ok=True)
        traceback.print_exc()
        failed_status = {
            **base_status,
            "state": "failed",
            "stage": "failed",
            "message": (
                "Render completed but final file promotion failed."
                if promotion_failed
                else "Render failed."
            ),
            "error": f"{type(exc).__name__}: {exc}",
        }
        if promotion_failed:
            failed_status["temporary_output_preserved"] = exc.partial_preserved
        atomic_write_json(failed_status, status_path)
        return 1


def _progress_writer(status_path, base_status, minimum_interval=0.25):
    last_write = 0.0
    last_stage = None

    def update(progress):
        nonlocal last_write, last_stage
        current_time = monotonic()
        stage_changed = progress.stage != last_stage

        if not stage_changed and current_time - last_write < minimum_interval:
            return

        try:
            atomic_write_json(
                {
                    **base_status,
                    "state": "running",
                    "stage": progress.stage,
                    "message": progress.message,
                    "progress": progress.progress,
                    "current": progress.current,
                    "total": progress.total,
                },
                status_path,
            )
        except OSError as exc:
            print(
                f"Warning: progress status update skipped: {exc}",
                file=sys.stderr,
                flush=True,
            )

        last_write = current_time
        last_stage = progress.stage

    return update


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="BarChartStudio render worker")
    parser.add_argument("--project", required=True)
    parser.add_argument("--root-dir", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--app-root")
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--job-id", required=True)
    return parser.parse_args(argv)


def _resolve_path(path, root_path):
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = root_path / resolved
    return resolved.resolve()


def main(argv=None):
    args = parse_args(argv)
    return run_worker(
        args.project,
        args.root_dir,
        args.status_file,
        args.job_id,
        output_root=args.output_root,
        app_root=args.app_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
