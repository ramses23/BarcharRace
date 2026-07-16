import unittest

import _test_path
from utils.file_size import format_file_size


class FileSizeTest(unittest.TestCase):
    def test_formats_binary_units(self):
        self.assertEqual(format_file_size(512), "512 B")
        self.assertEqual(format_file_size(1536), "1.5 KB")
        self.assertEqual(format_file_size(5 * 1024 * 1024), "5.0 MB")


if __name__ == "__main__":
    unittest.main()
