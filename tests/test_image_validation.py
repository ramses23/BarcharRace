import tempfile
import unittest
from pathlib import Path

import _test_path
from PIL import Image, features
from studio.image_validation import ImageValidationError, validate_image_file


class ImageValidationTest(unittest.TestCase):
    def test_accepts_valid_png(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "image.png"
            Image.new("RGBA", (3, 2), (10, 20, 30, 255)).save(path)

            info = validate_image_file(
                path,
                field_name="categories['A'].logo",
                original_value="assets/a.png",
            )

        self.assertEqual(info.format, "PNG")
        self.assertEqual((info.width, info.height), (3, 2))

    def test_accepts_valid_jpeg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "image.jpg"
            Image.new("RGB", (4, 3), (10, 20, 30)).save(path, format="JPEG")

            info = validate_image_file(
                path,
                field_name="chart.background_image_path",
                original_value="assets/background.jpg",
            )

        self.assertEqual(info.format, "JPEG")
        self.assertEqual((info.width, info.height), (4, 3))

    @unittest.skipUnless(features.check("webp"), "Pillow WebP support is required")
    def test_accepts_valid_webp_when_supported_by_pillow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "image.webp"
            Image.new("RGB", (5, 4), (10, 20, 30)).save(path, format="WEBP")

            info = validate_image_file(
                path,
                field_name="chart.bar_texture_custom_image",
                original_value="assets/texture.webp",
            )

        self.assertEqual(info.format, "WEBP")
        self.assertEqual((info.width, info.height), (5, 4))

    def test_rejects_text_with_png_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "fake.png"
            path.write_text("not an image", encoding="utf-8")

            with self.assertRaisesRegex(
                ImageValidationError,
                "corrupt or unsupported",
            ):
                validate_image_file(path, field_name="categories['A'].logo")

    def test_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "empty.webp"
            path.write_bytes(b"")

            with self.assertRaisesRegex(
                ImageValidationError,
                "corrupt or unsupported",
            ):
                validate_image_file(path, field_name="chart.background_image_path")

    def test_rejects_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "directory.png"
            path.mkdir()

            with self.assertRaisesRegex(
                ImageValidationError,
                "not a regular file",
            ):
                validate_image_file(path, field_name="categories['A'].logo")


if __name__ == "__main__":
    unittest.main()
