import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

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

    def test_retries_transient_permission_errors_during_replace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "project.json"
            original_replace = os.replace
            attempts = 0

            def flaky_replace(source, destination):
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError("destination is temporarily locked")
                original_replace(source, destination)

            with patch(
                "studio.project_storage.os.replace",
                side_effect=flaky_replace,
            ), patch("studio.project_storage.sleep") as wait:
                atomic_write_json({"name": "after retry"}, project_path)

            self.assertEqual(attempts, 3)
            self.assertEqual(
                json.loads(project_path.read_text(encoding="utf-8")),
                {"name": "after retry"},
            )
            self.assertEqual(
                wait.call_args_list,
                [call(0.01), call(0.02)],
            )
            self.assertEqual(list(Path(temp_dir).glob("*.tmp")), [])

    def test_rejects_non_json_destination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, ".json extension"):
                atomic_write_json({}, Path(temp_dir) / "project.txt")


if __name__ == "__main__":
    unittest.main()
