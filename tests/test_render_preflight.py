import json
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path

import _test_path
from studio.package_paths import resolve_project_path
from studio.render_preflight import run_render_preflight


class RenderPreflightTest(unittest.TestCase):
    def test_accepts_valid_csv_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = self._write_project(root)

            result = run_render_preflight(
                project_path,
                root_dir=root,
                ffmpeg_path="C:/tools/ffmpeg.exe",
            )

        self.assertTrue(result.ready)
        self.assertEqual(
            {check.key for check in result.checks},
            {"project", "data_source", "dataset", "periods", "ffmpeg", "output"},
        )

    def test_rejects_missing_columns_and_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = self._write_project(
                root,
                csv_text="year,name\n2020,A\n2021,A\n",
            )

            result = run_render_preflight(
                project_path,
                root_dir=root,
                ffmpeg_path="",
            )

        self.assertFalse(result.ready)
        errors = {check.key: check.message for check in result.checks if check.level == "error"}
        self.assertIn("dataset", errors)
        self.assertIn("ffmpeg", errors)

    def test_rejects_single_period_and_missing_background(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = self._write_project(
                root,
                csv_text="year,name,value\n2020,A,1\n2020,B,2\n",
                chart={
                    "background_mode": "image",
                    "background_image_path": "backgrounds/missing.png",
                },
            )

            result = run_render_preflight(
                project_path,
                root_dir=root,
                ffmpeg_path="ffmpeg",
            )

        errors = {check.key for check in result.checks if check.level == "error"}
        self.assertIn("periods", errors)
        self.assertIn("background", errors)

        background = next(check for check in result.checks if check.key == "background")
        self.assertIn("chart.background_image_path", background.message)
        self.assertIn("backgrounds/missing.png", background.message)
        self.assertIn(
            str((root / "backgrounds" / "missing.png").resolve()),
            background.message,
        )

    def test_resolves_dataset_and_assets_against_root_independent_of_cwd(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            project_path = self._write_project(
                root,
                chart={
                    "background_mode": "image",
                    "background_image_path": "assets/background.png",
                    "bar_texture_enabled": True,
                    "bar_texture_preset": "custom_image",
                    "bar_texture_custom_image": r"assets\texture.png",
                },
                dataset={
                    "category_logos": {"A": "assets/logos/a.png"},
                    "category_secondary_logos": {
                        "A": r"assets\secondary\a.png"
                    },
                },
            )
            for relative_path in (
                "assets/background.png",
                "assets/texture.png",
                "assets/logos/a.png",
                "assets/secondary/a.png",
            ):
                asset = root / relative_path
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_bytes(b"test asset")
            other_cwd = root / "other"
            other_cwd.mkdir()

            with chdir(other_cwd):
                result = run_render_preflight(
                    "projects/project.json",
                    root_dir=root,
                    ffmpeg_path="ffmpeg",
                )

        self.assertTrue(result.ready)
        checks = {check.key: check for check in result.checks}
        self.assertEqual(
            checks["background"].message,
            str(
                resolve_project_path(
                    "assets/background.png",
                    project_root=root,
                )
            ),
        )
        self.assertEqual(
            checks["texture"].message,
            str(
                resolve_project_path(
                    r"assets\texture.png",
                    project_root=root,
                )
            ),
        )
        self.assertNotIn("logos", checks)

    def test_accepts_existing_absolute_dataset_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            project_path = self._write_project(root)
            project = json.loads(project_path.read_text(encoding="utf-8"))
            absolute_csv = (root / "data" / "dataset.csv").resolve()
            project["data_source"]["csv_path"] = str(absolute_csv)
            project_path.write_text(json.dumps(project), encoding="utf-8")

            result = run_render_preflight(
                project_path,
                root_dir=root,
                ffmpeg_path="ffmpeg",
            )

        self.assertTrue(result.ready)

    def _write_project(self, root, csv_text=None, chart=None, dataset=None):
        data_dir = root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        csv_path = data_dir / "dataset.csv"
        csv_path.write_text(
            csv_text
            or "year,name,value\n2020,A,1\n2021,A,2\n",
            encoding="utf-8",
        )
        project = {
            "name": "preflight",
            "data_source": {"csv_path": "data/dataset.csv"},
            "dataset": {
                "year_column": "year",
                "name_column": "name",
                "value_column": "value",
                **(dataset or {}),
            },
            "chart": {
                "output_file": "output/video.mp4",
                **(chart or {}),
            },
        }
        project_path = root / "projects" / "project.json"
        project_path.parent.mkdir(parents=True, exist_ok=True)
        project_path.write_text(json.dumps(project), encoding="utf-8")
        return project_path


if __name__ == "__main__":
    unittest.main()
