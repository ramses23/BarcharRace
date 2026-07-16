import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _test_path
from studio.project_storage import atomic_write_json


class ProjectStorageTest(unittest.TestCase):
    def test_atomically_writes_json_and_creates_parent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "nested" / "project.json"

            result = atomic_write_json({"name": "demo"}, project_path)

            self.assertEqual(result, project_path)
            self.assertEqual(
                json.loads(project_path.read_text(encoding="utf-8")),
                {"name": "demo"},
            )
            self.assertEqual(list(project_path.parent.glob("*.tmp")), [])

    def test_replace_failure_preserves_existing_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "project.json"
            project_path.write_text('{"name": "original"}\n', encoding="utf-8")

            with patch(
                "studio.project_storage.os.replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    atomic_write_json({"name": "changed"}, project_path)

            self.assertEqual(
                json.loads(project_path.read_text(encoding="utf-8")),
                {"name": "original"},
            )
            self.assertEqual(list(Path(temp_dir).glob("*.tmp")), [])

    def test_rejects_non_json_destination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, ".json extension"):
                atomic_write_json({}, Path(temp_dir) / "project.txt")


if __name__ == "__main__":
    unittest.main()
