import argparse
import os
import sys
import traceback
from dataclasses import asdict, replace
from pathlib import Path
from time import monotonic


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config.project_file_loader import load_project_file
from pipeline.render_job import RenderJob
from studio.project_storage import atomic_write_json


def run_worker(project_file, root_dir, status_file, job_id):
    project_path = Path(project_file).resolve()
    root_path = Path(root_dir).resolve()
    status_path = Path(status_file).resolve()
    preset = load_project_file(project_path)
    final_output = _resolve_path(preset.chart_config.output_file, root_path)
    final_output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = final_output.with_name(
        f".{final_output.stem}.{job_id}.partial{final_output.suffix}"
    )
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

    try:
        result = RenderJob(
            config=chart_config,
            data_source_config=preset.data_source_config,
            dataset_config=preset.dataset_config,
            progress_callback=callback,
        ).run()
        os.replace(temporary_output, final_output)
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
        temporary_output.unlink(missing_ok=True)
        traceback.print_exc()
        failed_status = {
            **base_status,
            "state": "failed",
            "stage": "failed",
            "message": "Render failed.",
            "error": f"{type(exc).__name__}: {exc}",
        }
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
        last_write = current_time
        last_stage = progress.stage

    return update


def _resolve_path(path, root_path):
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = root_path / resolved
    return resolved.resolve()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="BarChartStudio render worker")
    parser.add_argument("--project", required=True)
    parser.add_argument("--root-dir", required=True)
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--job-id", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    return run_worker(
        args.project,
        args.root_dir,
        args.status_file,
        args.job_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
