import json
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_PATH = ROOT_DIR / "projects" / "global_electricity_sources.json"
EXPECTED_CATEGORIES = {
    "Coal",
    "Gas",
    "Hydro",
    "Nuclear",
    "Wind",
    "Solar",
    "Bioenergy",
    "Oil and other fossil",
}


class GlobalElectricityProjectTest(unittest.TestCase):
    def test_approved_project_configuration(self):
        project = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(project["schema_version"], 1)
        self.assertEqual(
            project["chart"]["title"],
            "Global Electricity Sources",
        )
        self.assertEqual(project["chart"]["fps"], 24)
        self.assertEqual(set(project["categories"]), EXPECTED_CATEGORIES)
        self.assertEqual(project["categories"]["Gas"]["label"], "Natural gas")
        self.assertIn(
            "TWh",
            project["data_source"]["source_label_override"],
        )


if __name__ == "__main__":
    unittest.main()
