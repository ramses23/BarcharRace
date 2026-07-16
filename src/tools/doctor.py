import argparse
import importlib.metadata
import json
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
CORE_DISTRIBUTIONS = (
    "matplotlib",
    "numpy",
    "pandas",
    "pillow",
    "streamlit",
)


@dataclass(frozen=True)
class DoctorCheck:
    key: str
    level: str
    message: str


def run_doctor(
    *,
    root_dir=ROOT_DIR,
    allow_global=False,
    skip_ffmpeg=False,
):
    root_path = Path(root_dir).resolve()
    checks = [
        _python_check(root_path),
        _virtual_environment_check(root_path, allow_global=allow_global),
        *_dependency_checks(root_path),
        _write_check(root_path),
        _sample_project_check(root_path),
    ]

    if not skip_ffmpeg:
        checks.extend(_ffmpeg_checks())

    return tuple(checks)


def _python_check(root_path):
    expected = _expected_python(root_path)
    current = f"{sys.version_info.major}.{sys.version_info.minor}"

    if expected and current != expected:
        return DoctorCheck(
            "python",
            "error",
            f"Python {current} is active; this project requires Python {expected}.",
        )

    return DoctorCheck(
        "python",
        "ok",
        f"Python {sys.version.split()[0]} at {Path(sys.executable).resolve()}.",
    )


def _virtual_environment_check(root_path, *, allow_global):
    expected_python = (
        root_path
        / ".venv"
        / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    ).resolve()
    current_python = Path(sys.executable).resolve()
    inside_virtual_environment = sys.prefix != sys.base_prefix
    uses_project_environment = current_python == expected_python

    if inside_virtual_environment and uses_project_environment:
        return DoctorCheck(
            "virtual_environment",
            "ok",
            "The repository .venv interpreter is active.",
        )

    message = (
        f"Active interpreter is not {expected_python}. Run "
        "scripts\\run_studio.ps1 so Streamlit cannot resolve from a global Python."
    )
    return DoctorCheck(
        "virtual_environment",
        "warning" if allow_global else "error",
        message,
    )


def _dependency_checks(root_path):
    pinned = _pinned_requirements(root_path / "requirements.txt")
    checks = []

    for distribution in CORE_DISTRIBUTIONS:
        expected = pinned.get(distribution)
        try:
            installed = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            checks.append(
                DoctorCheck(
                    f"dependency_{distribution}",
                    "error",
                    f"Missing Python package: {distribution}.",
                )
            )
            continue

        if expected and installed != expected:
            checks.append(
                DoctorCheck(
                    f"dependency_{distribution}",
                    "error",
                    f"{distribution} {installed} is installed; lock requires {expected}.",
                )
            )
            continue

        checks.append(
            DoctorCheck(
                f"dependency_{distribution}",
                "ok",
                f"{distribution} {installed}.",
            )
        )

    return tuple(checks)


def _write_check(root_path):
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".barchartstudio_doctor_",
            suffix=".tmp",
            dir=root_path,
        ) as probe:
            probe.write(b"ok")
            probe.flush()
    except OSError as exc:
        return DoctorCheck(
            "repository_write",
            "error",
            f"Repository is not writable: {exc}",
        )

    return DoctorCheck(
        "repository_write",
        "ok",
        f"Repository is writable: {root_path}.",
    )


def _sample_project_check(root_path):
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    try:
        from config.project_file_loader import load_project_file

        project_path = root_path / "projects" / "sample_project.json"
        preset = load_project_file(project_path)
    except (ImportError, OSError, ValueError) as exc:
        return DoctorCheck(
            "sample_project",
            "error",
            f"Sample project could not be loaded: {exc}",
        )

    return DoctorCheck(
        "sample_project",
        "ok",
        f"Sample project is valid: {preset.name}.",
    )


def _ffmpeg_checks():
    checks = []
    for executable in ("ffmpeg", "ffprobe"):
        path = shutil.which(executable)
        checks.append(
            DoctorCheck(
                executable,
                "ok" if path else "error",
                (
                    f"{executable} is available at {path}."
                    if path
                    else f"{executable} was not found on PATH."
                ),
            )
        )
    return tuple(checks)


def _expected_python(root_path):
    version_file = root_path / ".python-version"
    if not version_file.is_file():
        return None

    parts = version_file.read_text(encoding="utf-8").strip().split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else parts[0]


def _pinned_requirements(path):
    requirements = {}
    if not path.is_file():
        return requirements

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        requirements[name.strip().lower()] = version.strip()

    return requirements


def _print_checks(checks):
    labels = {"ok": "OK", "warning": "WARN", "error": "ERROR"}
    for check in checks:
        print(f"[{labels[check.level]}] {check.message}")

    errors = sum(check.level == "error" for check in checks)
    warnings = sum(check.level == "warning" for check in checks)
    print(f"\nDoctor result: {errors} error(s), {warnings} warning(s).")


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Validate the local BarChartStudio development environment.",
    )
    parser.add_argument(
        "--allow-global",
        action="store_true",
        help="Report a non-.venv interpreter as a warning (useful in CI).",
    )
    parser.add_argument(
        "--skip-ffmpeg",
        action="store_true",
        help="Skip FFmpeg and FFprobe availability checks.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of the text report.",
    )
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    checks = run_doctor(
        allow_global=args.allow_global,
        skip_ffmpeg=args.skip_ffmpeg,
    )

    if args.json:
        print(json.dumps([asdict(check) for check in checks], indent=2))
    else:
        _print_checks(checks)

    return 1 if any(check.level == "error" for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
