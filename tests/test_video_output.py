import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from ui.video_output import resolve_video_path, show_finished_video


class VideoOutputTest(unittest.TestCase):
    def test_resolves_relative_video_from_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            self.assertEqual(
                resolve_video_path("output/video.mp4", root_dir=root),
                (root / "output" / "video.mp4").resolve(),
            )

    @patch("ui.video_output.st")
    def test_shows_playback_and_download_for_finished_video(self, streamlit):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "finished.mp4"
            video_path.write_bytes(b"video-bytes")

            shown = show_finished_video(video_path)

        self.assertTrue(shown)
        streamlit.video.assert_called_once_with(str(video_path.resolve()))
        kwargs = streamlit.download_button.call_args.kwargs
        self.assertEqual(kwargs["file_name"], "finished.mp4")
        self.assertEqual(kwargs["mime"], "video/mp4")
        self.assertEqual(kwargs["on_click"], "ignore")

    @patch("ui.video_output.st")
    def test_warns_when_finished_video_is_missing(self, streamlit):
        shown = show_finished_video("missing.mp4")

        self.assertFalse(shown)
        streamlit.warning.assert_called_once()
        streamlit.video.assert_not_called()


if __name__ == "__main__":
    unittest.main()
