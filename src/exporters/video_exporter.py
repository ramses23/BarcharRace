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
        cmd = self.build_command(frames_dir, output_file)

        print("Generando video...")

        subprocess.run(cmd, check=True)

        print(f"Video generado en: {output_file}")

    def build_command(self, frames_dir=None, output_file=None):
        frames_dir = Path(frames_dir or self.config.frames_dir)
        output_file = Path(output_file or self.config.output_file)

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(self.fps),
            "-i",
            str(frames_dir / self.config.ffmpeg_frame_pattern),
            "-c:v",
            self.config.video_codec,
        ]

        if self.config.ffmpeg_preset:
            cmd.extend(["-preset", self.config.ffmpeg_preset])

        if self.config.video_bitrate:
            cmd.extend(["-b:v", self.config.video_bitrate])
        elif self.config.video_crf is not None:
            cmd.extend(["-crf", str(self.config.video_crf)])

        if self.config.video_pixel_format:
            cmd.extend(["-pix_fmt", self.config.video_pixel_format])

        cmd.append(str(output_file))

        return cmd


    def build_stream_command(self, output_file=None):
        output_file = Path(output_file or self.config.output_file)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s", f"{self.config.width}x{self.config.height}",
            "-r", str(self.fps), "-i", "-",
            "-c:v", self.config.video_codec,
        ]

        if self.config.ffmpeg_preset:
            cmd.extend(["-preset", self.config.ffmpeg_preset])
        if self.config.video_bitrate:
            cmd.extend(["-b:v", self.config.video_bitrate])
        elif self.config.video_crf is not None:
            cmd.extend(["-crf", str(self.config.video_crf)])
        if self.config.video_pixel_format:
            cmd.extend(["-pix_fmt", self.config.video_pixel_format])

        cmd.append(str(output_file))
        return cmd

    def open_stream(self, output_file=None):
        output_file = Path(output_file or self.config.output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        return subprocess.Popen(
            self.build_stream_command(output_file),
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def finish_stream(self, process):
        if process.stdin is not None:
            process.stdin.close()
        stderr = process.stderr.read() if process.stderr is not None else b""
        return_code = process.wait()
        if return_code:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"FFmpeg stream failed with exit code {return_code}: {message}"
            )

    def abort_stream(self, process):
        if process.poll() is None:
            process.terminate()
        process.wait()
