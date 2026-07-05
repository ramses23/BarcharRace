import subprocess
from pathlib import Path

from config.chart_config import ChartConfig


class VideoExporter:

    def __init__(self, config=None, fps=None):
        self.config = config or ChartConfig()
        self.fps = fps or self.config.fps

    def export(self, frames_dir=None, output_file=None):

        frames_dir = Path(frames_dir or self.config.frames_dir)
        output_file = Path(output_file or self.config.output_file)

        output_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-framerate", str(self.fps),
            "-i", str(frames_dir / self.config.ffmpeg_frame_pattern),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            str(output_file)
        ]

        print("Generando video...")

        subprocess.run(cmd, check=True)

        print(f"Video generado en: {output_file}")
