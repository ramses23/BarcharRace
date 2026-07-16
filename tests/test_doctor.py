import tempfile
import unittest
from pathlib import Path

import _test_path
from tools.doctor import (
    _expected_python,
    _pinned_requirements,
    run_doctor,
)


class DoctorTest(unittest.TestCase):
    def test_reads_expected_python_major_minor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".python-version").write_text("3.13.7\n", encoding="utf-8")

            self.assertEqual(_expected_python(root), "3.13")

    def test_reads_only_exact_pins(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            requirements = Path(temp_dir) / "requirements.txt"
            requirements.write_text(
                "streamlit==1.59.0\nnumpy>=2\n# comment\nPillow==12.3.0\n",
                encoding="utf-8",
            )

            self.assertEqual(
                _pinned_requirements(requirements),
                {"streamlit": "1.59.0", "pillow": "12.3.0"},
            )

    def test_current_repository_passes_doctor(self):
        checks = run_doctor(
            allow_global=True,
            skip_ffmpeg=True,
        )

        self.assertFalse(
            [check for check in checks if check.level == "error"],
        )
        self.assertTrue(any(check.key == "sample_project" for check in checks))
        self.assertTrue(
            any(check.key == "dependency_streamlit" for check in checks)
        )


if __name__ == "__main__":
    unittest.main()
