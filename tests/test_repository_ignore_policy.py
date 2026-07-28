import subprocess
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

IGNORED_LOCAL_PATHS = (
    "PRODUCCIONES/example/file.txt",
    "PRODUCCIONES_AUTOMATICAS/example/file.txt",
    "projects/imported/example/file.png",
    "production/templates/local/example.json",
    "example/.barchartstudio-launch.json",
    "example/package.barchart.zip",
)

TRACKABLE_EXAMPLE_PATHS = (
    "projects/sample_project.json",
    "projects/global_electricity_sources.json",
    "data/datasets/sample.csv",
    "tests/test_global_electricity_project.py",
)


def is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", "--", path],
        cwd=ROOT_DIR,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(
            f"git check-ignore failed for {path!r}: {result.stderr.strip()}"
        )
    return result.returncode == 0


class RepositoryIgnorePolicyTest(unittest.TestCase):
    def test_local_artifact_paths_are_ignored(self):
        for path in IGNORED_LOCAL_PATHS:
            with self.subTest(path=path):
                self.assertTrue(is_ignored(path), f"{path} should be ignored")

    def test_example_paths_remain_trackable(self):
        for path in TRACKABLE_EXAMPLE_PATHS:
            with self.subTest(path=path):
                self.assertFalse(is_ignored(path), f"{path} should remain trackable")


if __name__ == "__main__":
    unittest.main()
