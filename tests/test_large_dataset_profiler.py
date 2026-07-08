import csv
import tempfile
import unittest
from pathlib import Path

import _test_path
from tools.profile_large_dataset import (
    build_chart_config,
    generate_synthetic_dataset,
    parse_args,
    synthetic_value,
)


class LargeDatasetProfilerTest(unittest.TestCase):
    def test_generates_synthetic_dataset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "profile.csv"

            generate_synthetic_dataset(
                csv_path,
                start_year=2000,
                years=3,
                categories=4,
            )

            with csv_path.open(encoding="utf-8") as csv_file:
                rows = list(csv.DictReader(csv_file))

        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0]["year"], "2000")
        self.assertEqual(rows[0]["country"], "Category 001")
        self.assertEqual(rows[-1]["year"], "2002")
        self.assertEqual(rows[-1]["country"], "Category 004")
        self.assertGreater(float(rows[0]["value"]), 0)

    def test_synthetic_values_are_deterministic(self):
        first = synthetic_value(year_index=2, category_index=5, categories=10)
        second = synthetic_value(year_index=2, category_index=5, categories=10)

        self.assertEqual(first, second)

    def test_builds_chart_config_from_args(self):
        args = parse_args(
            [
                "--years",
                "5",
                "--categories",
                "20",
                "--top-n",
                "7",
                "--steps",
                "3",
                "--fps",
                "8",
                "--layout",
                "compact_dashboard",
                "--typography",
                "compact",
                "--output",
                "output/profile.mp4",
                "--frames-dir",
                "output/profile_frames",
                "--png-compress-level",
                "0",
                "--video-crf",
                "24",
                "--ffmpeg-preset",
                "slow",
            ]
        )

        config = build_chart_config(args)

        self.assertEqual(config.output_file, "output/profile.mp4")
        self.assertEqual(config.frames_dir, "output/profile_frames")
        self.assertEqual(config.selection.top_n, 7)
        self.assertEqual(config.steps_per_transition, 3)
        self.assertEqual(config.fps, 8)
        self.assertEqual(config.layout_preset, "compact_dashboard")
        self.assertEqual(config.typography_preset, "compact")
        self.assertFalse(config.logos_enabled)
        self.assertEqual(config.png_compress_level, 0)
        self.assertEqual(config.video_crf, 24)
        self.assertEqual(config.ffmpeg_preset, "slow")


if __name__ == "__main__":
    unittest.main()
