import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pipeline.render_job import RenderProfile, RenderResult
from studio.package_paths import ProjectPathError, resolve_project_path
from studio.project_storage import atomic_write_json
from studio.workspace_paths import assert_user_write_path


@dataclass
class BackgroundRender:
    job_id: str
    project_file: str
    status_path: Path
    log_path: Path
    process: subprocess.Popen

    @property
    def pid(self):
        return self.process.pid

    def is_running(self):
        return self.process.poll() is None

    def status(self):
        status = _read_status(self.status_path)

        if status.get("state") in {"completed", "failed", "canceled"}:
            return status

        return_code = self.process.poll()
        if return_code is None:
            return status

        failed_status = {
            **status,
            "state": "failed",
            "message": f"Render worker exited with code {return_code}.",
            "error": f"See render log: {self.log_path}",
        }
        temporary_output = failed_status.get("temporary_output")
        if temporary_output:
            Path(temporary_output).unlink(missing_ok=True)
        atomic_write_json(failed_status, self.status_path)
        return failed_status

    def cancel(self):
        status = self.status()
        if status.get("state") in {"completed", "failed", "canceled"}:
            return status

        _terminate_process_tree(self.process)
        temporary_output = status.get("temporary_output")
        if temporary_output:
            Path(temporary_output).unlink(missing_ok=True)

        canceled_status = {
            **status,
            "state": "canceled",
            "message": "Render canceled by the user.",
            "progress": float(status.get("progress", 0.0)),
        }
        atomic_write_json(canceled_status, self.status_path)
        return canceled_status


def start_background_render(
    project_file,
    *,
    root_dir=None,
    project_root=None,
    output_root=None,
    app_root=None,
    job_root=None,
    worker_path=None,
):
    if root_dir is not None and project_root is not None:
        raise ValueError("Use project_root or root_dir, not both.")
    root_value = project_root if project_root is not None else root_dir
    if root_value is None:
        raise ValueError("project_root is required.")
    root_path = Path(root_value).resolve()
    app_path = Path(app_root).resolve() if app_root is not None else root_path
    output_path = Path(output_root).resolve() if output_root is not None else root_path
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
    job_id = uuid4().hex
    jobs_path = (
        Path(job_root).resolve()
        if job_root is not None
        else root_path / "output" / ".render_jobs"
    )
    if app_root is not None:
        jobs_path = assert_user_write_path(
            jobs_path,
            app_root=app_path,
            operation="Render job state",
        )
    job_dir = jobs_path / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    status_path = job_dir / "status.json"
    log_path = job_dir / "render.log"
    worker_path = Path(
        worker_path or app_path / "src" / "studio" / "render_worker.py"
    ).resolve()
    initial_status = {
        "job_id": job_id,
        "state": "starting",
        "stage": "starting",
        "message": "Starting isolated render process.",
        "progress": 0.0,
        "current": 0,
        "total": 0,
        "project_file": str(project_path),
        "log_path": str(log_path),
    }
    atomic_write_json(initial_status, status_path)
    command = [
        sys.executable,
        str(worker_path),
        "--project",
        str(project_path),
        "--root-dir",
        str(root_path),
        "--output-root",
        str(output_path),
    ]
    if app_root is not None:
        command.extend(("--app-root", str(app_path)))
    command.extend(
        (
            "--status-file",
            str(status_path),
            "--job-id",
            job_id,
        )
    )
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            command,
            cwd=app_path,
            env=environment,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )

    return BackgroundRender(
        job_id=job_id,
        project_file=str(project_path),
        status_path=status_path,
        log_path=log_path,
        process=process,
    )


def render_result_from_status(status):
    result_data = status.get("result")
    if not isinstance(result_data, dict):
        return None

    profile_data = result_data.get("profile")
    if not isinstance(profile_data, dict):
        return None

    return RenderResult(
        frames_rendered=int(result_data.get("frames_rendered", 0)),
        transitions_rendered=int(result_data.get("transitions_rendered", 0)),
        removed_frames=int(result_data.get("removed_frames", 0)),
        output_file=str(result_data.get("output_file", "")),
        profile=RenderProfile(**profile_data),
    )


def _read_status(status_path):
    try:
        status = json.loads(Path(status_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {
            "state": "starting",
            "stage": "starting",
            "message": "Waiting for render worker status.",
            "progress": 0.0,
            "current": 0,
            "total": 0,
        }

    return status if isinstance(status, dict) else {}


def _terminate_process_tree(process):
    if process.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
