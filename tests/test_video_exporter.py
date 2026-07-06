import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from config.chart_config import ChartConfig
from exporters.video_exporter import VideoExporter


class VideoExporterTest(unittest.TestCase):
    def test_builds_default_ffmpeg_command(self):
        config = ChartConfig(
            frames_dir="frames",
            output_file="output/video.mp4",
            fps=24,
        )

        command = VideoExporter(config=config).build_command()

        self.assertEqual(
            command,
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-framerate",
                "24",
                "-i",
                str(Path("frames") / "frame_%04d.png"),
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "output\\video.mp4",
            ],
        )

    def test_builds_command_with_export_overrides(self):
        config = ChartConfig(
            frames_dir="frames",
            output_file="output/video.mp4",
            fps=60,
            video_codec="libx265",
            video_pixel_format="yuv444p",
            video_crf=22,
            ffmpeg_preset="slow",
        )

        command = VideoExporter(config=config).build_command()

        self.assertIn("-c:v", command)
        self.assertEqual(command[command.index("-c:v") + 1], "libx265")
        self.assertEqual(command[command.index("-preset") + 1], "slow")
        self.assertEqual(command[command.index("-crf") + 1], "22")
        self.assertEqual(command[command.index("-pix_fmt") + 1], "yuv444p")

    def test_bitrate_mode_omits_crf(self):
        config = ChartConfig(
            video_crf=18,
            video_bitrate="8M",
        )

        command = VideoExporter(config=config).build_command()

        self.assertNotIn("-crf", command)
        self.assertEqual(command[command.index("-b:v") + 1], "8M")

    def test_export_runs_ffmpeg_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "nested" / "video.mp4"
            config = ChartConfig(
                frames_dir=str(Path(temp_dir) / "frames"),
                output_file=str(output_file),
            )

            with patch("exporters.video_exporter.subprocess.run") as run:
                with patch("builtins.print"):
                    VideoExporter(config=config).export()

            self.assertTrue(output_file.parent.exists())
            run.assert_called_once()
            self.assertEqual(run.call_args.kwargs["check"], True)


if __name__ == "__main__":
    unittest.main()
