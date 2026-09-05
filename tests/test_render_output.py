import hashlib
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from studio.render_output import (
    RenderOutputPromotionError,
    _filesystem_path,
    display_path,
    promote_render_output,
    temporary_render_output_path,
)


INCIDENT_SLUG = "most_popular_mobile_phone_brands_web_usage_share_2010_2026"


class RenderOutputTest(unittest.TestCase):
    def test_temporary_name_is_short_unique_and_independent_of_final_slug(self):
        final_path = Path("output") / f"{INCIDENT_SLUG}.mp4"

        partials = {temporary_render_output_path(final_path) for _ in range(100)}

        self.assertEqual(len(partials), 100)
        for partial in partials:
            self.assertEqual(partial.parent, final_path.parent)
            self.assertNotIn(INCIDENT_SLUG, partial.name)
            self.assertRegex(
                partial.name,
                re.compile(r"^\.render\.[0-9a-f]{16}\.partial\.mp4$"),
            )

    def test_real_incident_path_lengths_promote_and_preserve_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = self._directory_with_absolute_length(temp_dir, 156)
            final_path = output_dir / f"{INCIDENT_SLUG}.mp4"
            partial_path = temporary_render_output_path(final_path)
            old_partial = final_path.with_name(
                f".{final_path.stem}.{'a' * 32}.partial{final_path.suffix}"
            )
            payload = b"complete-render-payload\x00\xff"
            partial_path.write_bytes(payload)

            self.assertEqual(len(str(output_dir)), 156)
            self.assertEqual(len(str(final_path)), 219)
            self.assertEqual(len(str(old_partial)), 261)
            self.assertEqual(len(str(partial_path)), 193)

            promoted = promote_render_output(partial_path, final_path)

            self.assertEqual(promoted, final_path)
            self.assertTrue(final_path.is_file())
            self.assertFalse(partial_path.exists())
            self.assertEqual(
                hashlib.sha256(final_path.read_bytes()).digest(),
                hashlib.sha256(payload).digest(),
            )

    def test_final_path_over_260_characters_is_promoted_with_extended_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = self._directory_with_absolute_length(temp_dir, 205)
            final_path = output_dir / f"{INCIDENT_SLUG}.mp4"
            partial_path = temporary_render_output_path(final_path)
            payload = b"long-final-path"
            partial_path.write_bytes(payload)

            self.assertGreater(len(str(final_path)), 260)
            self.assertLess(len(str(partial_path)), 260)

            try:
                promote_render_output(partial_path, final_path)

                self.assertTrue(os.path.isfile(_filesystem_path(final_path)))
                with open(_filesystem_path(final_path), "rb") as output_file:
                    self.assertEqual(output_file.read(), payload)
            finally:
                if os.path.exists(_filesystem_path(final_path)):
                    os.unlink(_filesystem_path(final_path))

    def test_promotion_overwrites_existing_final_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            final_path = Path(temp_dir) / "race.mp4"
            partial_path = temporary_render_output_path(final_path)
            final_path.write_bytes(b"previous")
            partial_path.write_bytes(b"replacement")

            promote_render_output(partial_path, final_path)

            self.assertEqual(final_path.read_bytes(), b"replacement")
            self.assertFalse(partial_path.exists())

    def test_promotion_failure_preserves_partial_and_reports_both_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            final_path = Path(temp_dir) / "race.mp4"
            partial_path = temporary_render_output_path(final_path)
            partial_path.write_bytes(b"recoverable-render")
            cause = FileNotFoundError(
                2,
                "synthetic missing path",
                _filesystem_path(partial_path),
                3,
                _filesystem_path(final_path),
            )

            with patch("studio.render_output.os.replace", side_effect=cause):
                with self.assertRaises(RenderOutputPromotionError) as raised:
                    promote_render_output(partial_path, final_path)

            self.assertEqual(partial_path.read_bytes(), b"recoverable-render")
            self.assertFalse(final_path.exists())
            message = str(raised.exception)
            self.assertIn(str(partial_path), message)
            self.assertIn(str(final_path), message)
            self.assertIn("WinError 3", message)
            self.assertIn("synthetic missing path", message)
            self.assertNotIn("\\\\?\\", message)
            self.assertIs(raised.exception.cause, cause)

    def test_missing_partial_is_reported_before_promotion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            final_path = Path(temp_dir) / "race.mp4"
            partial_path = temporary_render_output_path(final_path)

            with self.assertRaises(RenderOutputPromotionError) as raised:
                promote_render_output(partial_path, final_path)

            self.assertIn(str(partial_path), str(raised.exception))
            self.assertFalse(raised.exception.partial_preserved)

    @unittest.skipUnless(os.name == "nt", "Windows extended paths only")
    def test_windows_filesystem_path_supports_drive_and_unc_paths(self):
        self.assertEqual(
            _filesystem_path(r"C:\output\race.mp4"),
            r"\\?\C:\output\race.mp4",
        )
        self.assertEqual(
            _filesystem_path(r"\\server\share\output\race.mp4"),
            r"\\?\UNC\server\share\output\race.mp4",
        )
        self.assertEqual(
            _filesystem_path(r"\\?\C:\output\race.mp4"),
            r"\\?\C:\output\race.mp4",
        )

    @unittest.skipUnless(os.name == "nt", "Windows display paths only")
    def test_display_path_normalizes_drive_and_unc_device_paths(self):
        self.assertEqual(
            display_path(r"\\?\C:\output\race.mp4"),
            r"C:\output\race.mp4",
        )
        self.assertEqual(
            display_path(r"\\?\UNC\server\share\output\race.mp4"),
            r"\\server\share\output\race.mp4",
        )
        self.assertEqual(
            display_path(r"C:\output\race.mp4"),
            r"C:\output\race.mp4",
        )

    def test_non_windows_filesystem_path_is_unchanged(self):
        normal_path = os.fspath(Path("output") / "race.mp4")

        with patch("studio.render_output.os.name", "posix"):
            self.assertEqual(_filesystem_path(normal_path), normal_path)
            self.assertEqual(display_path(normal_path), normal_path)

    @staticmethod
    def _directory_with_absolute_length(root, minimum_length):
        directory = Path(root).resolve()
        component_length = minimum_length - len(str(directory)) - 1
        if component_length <= 0:
            raise ValueError("Temporary root is already longer than target length.")
        directory /= "x" * component_length
        directory.mkdir()
        return directory.resolve()


if __name__ == "__main__":
    unittest.main()
