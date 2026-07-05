import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from pipeline.render_job import RenderJob


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required for video export")
class RenderJobIntegrationTest(unittest.TestCase):
    def test_renders_tiny_video_with_real_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "sample.csv"
            frames_dir = temp_path / "frames"
            output_file = temp_path / "video.mp4"

            csv_path.write_text(
                "\n".join(
                    [
                        "year,country,value",
                        "2000,USA,100",
                        "2000,Mexico,80",
                        "2001,USA,90",
                        "2001,Mexico,95",
                    ]
                ),
                encoding="utf-8",
            )

            config = ChartConfig(
                width=320,
                height=180,
                dpi=80,
                left_margin=80,
                right_margin=60,
                top_margin=48,
                bottom_margin=24,
                bar_height=14,
                bar_gap=6,
                fps=2,
                steps_per_transition=2,
                frames_dir=str(frames_dir),
                output_file=str(output_file),
                title="Integration",
                title_font_size=10,
                subtitle_font_size=7,
                time_label_font_size=28,
                source_font_size=5,
                label_font_size=7,
                value_font_size=7,
                title_y=16,
                subtitle_y=31,
                time_label_x=292,
                time_label_y=150,
                source_x=80,
                source_y=168,
                logos_enabled=False,
            )
            data_source = DataSourceConfig(
                source_type="csv",
                csv_path=str(csv_path),
            )

            with patch("builtins.print"):
                result = RenderJob(
                    config=config,
                    data_source_config=data_source,
                    dataset_config=DatasetConfig(),
                ).run()

            frame_files = sorted(frames_dir.glob("frame_*.png"))

            self.assertEqual(result.frames_rendered, 2)
            self.assertEqual(result.transitions_rendered, 1)
            self.assertEqual(result.output_file, str(output_file))
            self.assertEqual(len(frame_files), 2)
            self.assertTrue(output_file.exists())
            self.assertGreater(output_file.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
