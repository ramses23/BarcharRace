import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_TEMPLATE = (
    REPOSITORY_ROOT
    / "templates"
    / "production_package"
    / "ABRIR_PRODUCCION.cmd"
)
CMD_EXE = os.environ.get("COMSPEC") or shutil.which("cmd.exe")
CMD_AVAILABLE = bool(CMD_EXE and Path(CMD_EXE).is_file())
AUTOLOAD_MODULE = """
import json
import os
import sys
from pathlib import Path

capture_path = os.environ.get("LAUNCHER_TEST_CAPTURE")
if capture_path:
    Path(capture_path).write_text(
        json.dumps(
            {
                "argv": sys.argv[1:],
                "cwd": os.getcwd(),
                "executable": sys.executable,
            }
        ),
        encoding="utf-8",
    )
raise SystemExit(int(os.environ.get("LAUNCHER_TEST_EXIT_CODE", "0")))
""".lstrip()


class ProductionPackageLauncherStructureTest(unittest.TestCase):
    def test_template_is_generic_and_contains_required_guards(self):
        source = LAUNCHER_TEMPLATE.read_text(encoding="utf-8")

        for required in (
            "setlocal EnableExtensions DisableDelayedExpansion",
            "%~dp0",
            "BARCHARTSTUDIO_ROOT",
            "%PRODUCTION_DIR%..\\..",
            "BARCHARTSTUDIO_PYTHON",
            "%STUDIO_ROOT%\\.venv\\Scripts\\python.exe",
            "src\\tools\\open_production_package.py",
            'set "PACKAGE_DIR=%PRODUCTION_DIR%package"',
            'set "MANIFEST_PATH=%PACKAGE_DIR%\\manifest.json"',
            "pushd",
            "popd",
            "-m src.tools.open_production_package",
            "--root",
            "%*",
            "exit /b %PYTHON_EXIT_CODE%",
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)

        lowered = source.casefold()
        for forbidden in (
            "barchartstudio-hybrid",
            str(REPOSITORY_ROOT).casefold(),
            "powershell",
            "curl ",
            "invoke-webrequest",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)


@unittest.skipUnless(
    CMD_AVAILABLE,
    "cmd.exe is required for functional launcher tests",
)
class ProductionPackageLauncherFunctionalTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="barchart-launcher-"
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()

    def test_relative_root_resolution_and_paths_with_spaces(self):
        root = self.temp_path / "Bar Chart Studio raíz"
        self._write_test_module(root)
        production = self._write_production(
            root / "PRODUCCIONES" / "demostración uno"
        )
        capture_path = self.temp_path / "relative-root.json"

        result = self._run_launcher(
            production,
            environment=self._environment(capture_path),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        capture = self._read_capture(capture_path)
        self.assertEqual(Path(capture["cwd"]), root.resolve())
        self.assertEqual(
            Path(capture["argv"][0]),
            (production / "package").resolve(),
        )
        self.assertEqual(capture["argv"][1:3], ["--root", str(root.resolve())])

    def test_root_environment_overrides_relative_resolution(self):
        root = self.temp_path / "explicit root"
        self._write_test_module(root)
        production = self._write_production(
            self.temp_path / "separate delivery" / "demo"
        )
        capture_path = self.temp_path / "root-override.json"
        environment = self._environment(capture_path)
        environment["BARCHARTSTUDIO_ROOT"] = str(root)

        result = self._run_launcher(production, environment=environment)

        self.assertEqual(result.returncode, 0, result.stderr)
        capture = self._read_capture(capture_path)
        self.assertEqual(Path(capture["cwd"]), root.resolve())
        self.assertEqual(capture["argv"][1:3], ["--root", str(root.resolve())])

    def test_python_override_and_arguments_are_forwarded_exactly(self):
        root = self.temp_path / "argument root"
        self._write_test_module(root)
        production = self._write_production(
            root / "PRODUCCIONES" / "argument demo"
        )
        capture_path = self.temp_path / "arguments.json"
        arguments = ("--no-launch", "--port", "8502", "--headless")

        result = self._run_launcher(
            production,
            *arguments,
            environment=self._environment(capture_path),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        capture = self._read_capture(capture_path)
        self.assertTrue(
            Path(capture["executable"]).samefile(Path(sys.executable))
        )
        self.assertEqual(capture["argv"][3:], list(arguments))

    def test_missing_manifest_fails_before_python(self):
        root = self.temp_path / "manifest root"
        self._write_test_module(root)
        production = self._write_production(
            root / "PRODUCCIONES" / "missing manifest"
        )
        (production / "package" / "manifest.json").unlink()
        capture_path = self.temp_path / "missing-manifest.json"

        result = self._run_launcher(
            production,
            environment=self._environment(capture_path),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manifest was not found", result.stderr)
        self.assertIn("manifest.json", result.stderr)
        self.assertFalse(capture_path.exists())

    def test_missing_module_reports_its_path(self):
        root = self.temp_path / "module root"
        root.mkdir()
        production = self._write_production(
            root / "PRODUCCIONES" / "missing module"
        )
        capture_path = self.temp_path / "missing-module.json"

        result = self._run_launcher(
            production,
            environment=self._environment(capture_path),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("command was not found", result.stderr)
        self.assertIn("open_production_package.py", result.stderr)
        self.assertFalse(capture_path.exists())

    def test_missing_python_reports_its_path(self):
        root = self.temp_path / "python root"
        self._write_test_module(root)
        production = self._write_production(
            root / "PRODUCCIONES" / "missing python"
        )
        capture_path = self.temp_path / "missing-python.json"
        environment = self._environment(capture_path)
        environment["BARCHARTSTUDIO_PYTHON"] = str(
            self.temp_path / "missing python.exe"
        )

        result = self._run_launcher(production, environment=environment)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Python was not found", result.stderr)
        self.assertIn("missing python.exe", result.stderr)
        self.assertFalse(capture_path.exists())

    def test_missing_root_reports_its_path(self):
        production = self._write_production(
            self.temp_path / "delivery" / "missing root"
        )
        missing_root = self.temp_path / "root does not exist"
        capture_path = self.temp_path / "missing-root.json"
        environment = self._environment(capture_path)
        environment["BARCHARTSTUDIO_ROOT"] = str(missing_root)

        result = self._run_launcher(production, environment=environment)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("root was not found", result.stderr)
        self.assertIn("root does not exist", result.stderr)
        self.assertFalse(capture_path.exists())

    def test_python_exit_code_is_propagated(self):
        root = self.temp_path / "exit root"
        self._write_test_module(root)
        production = self._write_production(
            root / "PRODUCCIONES" / "exit demo"
        )
        capture_path = self.temp_path / "exit-code.json"
        environment = self._environment(capture_path)
        environment["LAUNCHER_TEST_EXIT_CODE"] = "7"

        result = self._run_launcher(production, environment=environment)

        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertTrue(capture_path.is_file())

    @staticmethod
    def _write_test_module(root):
        module_path = root / "src" / "tools" / "open_production_package.py"
        module_path.parent.mkdir(parents=True)
        module_path.write_text(AUTOLOAD_MODULE, encoding="utf-8")

    @staticmethod
    def _write_production(production):
        package = production / "package"
        package.mkdir(parents=True)
        (package / "manifest.json").write_text("{}\n", encoding="utf-8")
        shutil.copy2(
            LAUNCHER_TEMPLATE,
            production / "ABRIR_PRODUCCION.cmd",
        )
        return production

    def _environment(self, capture_path):
        environment = os.environ.copy()
        environment.pop("BARCHARTSTUDIO_ROOT", None)
        environment["BARCHARTSTUDIO_PYTHON"] = sys.executable
        environment["LAUNCHER_TEST_CAPTURE"] = str(capture_path)
        environment.pop("LAUNCHER_TEST_EXIT_CODE", None)
        return environment

    @staticmethod
    def _read_capture(capture_path):
        return json.loads(capture_path.read_text(encoding="utf-8"))

    @staticmethod
    def _run_launcher(production, *arguments, environment):
        return subprocess.run(
            [
                CMD_EXE,
                "/d",
                "/c",
                "call",
                str(production / "ABRIR_PRODUCCION.cmd"),
                *arguments,
            ],
            cwd=production,
            env=environment,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
