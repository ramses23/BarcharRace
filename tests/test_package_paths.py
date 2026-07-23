import tempfile
import unittest
from contextlib import chdir
from pathlib import Path

import _test_path
from studio.package_paths import ProjectPathError, resolve_project_path


class PackagePathsTest(unittest.TestCase):
    def test_resolves_relative_path_against_root_independent_of_cwd(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            other_cwd = root / "other"
            other_cwd.mkdir()
            expected = root / "data" / "dataset.csv"

            before = resolve_project_path(
                "data/dataset.csv",
                project_root=root,
                required=True,
            )
            with chdir(other_cwd):
                after = resolve_project_path(
                    "data/dataset.csv",
                    project_root=root,
                    required=True,
                )

        self.assertEqual(before, expected)
        self.assertEqual(after, expected)

    def test_preserves_absolute_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            absolute = (root / "outside-compatible.csv").resolve()

            resolved = resolve_project_path(
                absolute,
                project_root=root / "project-root",
                required=True,
            )

        self.assertEqual(resolved, absolute)

    def test_normalizes_posix_and_windows_separators(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            expected = (root / "assets" / "logos" / "a.png").resolve()

            posix = resolve_project_path(
                "assets/logos/a.png",
                project_root=root,
            )
            windows = resolve_project_path(
                r"assets\logos\a.png",
                project_root=root,
            )

        self.assertEqual(posix, expected)
        self.assertEqual(windows, expected)

    def test_rejects_relative_path_that_escapes_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()

            with self.assertRaisesRegex(
                ProjectPathError,
                "escapes project root",
            ):
                resolve_project_path(
                    "../outside.csv",
                    project_root=root,
                    field_name="data_source.csv_path",
                )

    def test_reports_required_empty_and_incompatible_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()

            with self.assertRaisesRegex(ProjectPathError, "received an empty value"):
                resolve_project_path("  ", project_root=root, required=True)
            with self.assertRaisesRegex(ProjectPathError, "received int"):
                resolve_project_path(12, project_root=root)

            self.assertIsNone(resolve_project_path(None, project_root=root))


if __name__ == "__main__":
    unittest.main()
