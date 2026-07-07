import json
import tempfile
import unittest
from pathlib import Path

import _test_path
from studio.project_builder import (
    build_project_data,
    default_project_paths,
    inspect_csv,
    preferred_column,
    project_name_from_title,
    save_project_data,
)


class ProjectStudioBuilderTest(unittest.TestCase):
    def test_inspects_csv_and_detects_candidate_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "electricity.csv"
            csv_path.write_text(
                "year,country,value,note\n"
                "2020,Coal,100,a\n"
                "2021,Coal,120,b\n",
                encoding="utf-8",
            )

            inspection = inspect_csv(csv_path)

        self.assertEqual(inspection.columns, ("year", "country", "value", "note"))
        self.assertEqual(inspection.row_count, 2)
        self.assertEqual(inspection.year_candidates, ("year",))
        self.assertEqual(inspection.name_candidates, ("country",))
        self.assertEqual(inspection.value_candidates, ("value",))

    def test_builds_and_saves_project_data(self):
        project_data = build_project_data(
            name="electricity",
            csv_path="data/datasets/electricity.csv",
            year_column="year",
            name_column="country",
            value_column="value",
            title="Electricity",
            source_label="Source: Test",
            output_file="output/electricity.mp4",
            frames_dir="output/electricity_frames",
            layout_preset="youtube_1080p",
            theme="clean_report",
            typography_preset="editorial",
            value_format="decimal",
            fps=24,
            steps_per_transition=24,
            top_n=8,
            max_visible_bars=8,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "project.json"
            saved_path = save_project_data(project_data, project_path)
            loaded = json.loads(saved_path.read_text(encoding="utf-8"))

        self.assertEqual(loaded["name"], "electricity")
        self.assertEqual(loaded["chart"]["title"], "Electricity")
        self.assertEqual(loaded["data_source"]["source_label_override"], "Source: Test")
        self.assertEqual(loaded["dataset"]["value_column"], "value")

    def test_builds_project_name_and_default_paths(self):
        name = project_name_from_title("Electricity by Source!")
        paths = default_project_paths(name)

        self.assertEqual(name, "electricity_by_source")
        self.assertEqual(paths["project_file"], "projects/electricity_by_source.json")
        self.assertEqual(paths["output_file"], "output/electricity_by_source.mp4")

    def test_prefers_candidates_before_fallbacks(self):
        self.assertEqual(
            preferred_column(("value",), ("year", "value"), "year"),
            "value",
        )
        self.assertEqual(
            preferred_column((), ("year", "value"), "value"),
            "value",
        )


if __name__ == "__main__":
    unittest.main()
