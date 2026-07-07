import json
import tempfile
import unittest
from pathlib import Path

import _test_path
from studio.project_builder import (
    build_project_data,
    category_values,
    clean_category_styles,
    default_project_paths,
    inspect_csv,
    load_project_data,
    preferred_column,
    project_form_values,
    project_name_from_title,
    save_project_data,
    year_values,
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
            category_styles={
                "Coal": {"label": "Carbon", "color": "#333333"},
                "Solar": {"label": "Solar"},
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "project.json"
            saved_path = save_project_data(project_data, project_path)
            loaded = json.loads(saved_path.read_text(encoding="utf-8"))

        self.assertEqual(loaded["name"], "electricity")
        self.assertEqual(loaded["chart"]["title"], "Electricity")
        self.assertEqual(loaded["data_source"]["source_label_override"], "Source: Test")
        self.assertEqual(loaded["dataset"]["value_column"], "value")
        self.assertEqual(loaded["categories"]["Coal"]["label"], "Carbon")
        self.assertEqual(loaded["categories"]["Coal"]["color"], "#333333")
        self.assertNotIn("Solar", loaded["categories"])

    def test_extracts_category_values_from_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "electricity.csv"
            csv_path.write_text(
                "year,country,value\n"
                "2020, Coal ,100\n"
                "2020,Solar,40\n"
                "2021,Coal,120\n"
                "2021,,20\n",
                encoding="utf-8",
            )

            values = category_values(csv_path, "country")

        self.assertEqual(values, ("Coal", "Solar"))

    def test_extracts_year_values_from_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "electricity.csv"
            csv_path.write_text(
                "year,country,value\n"
                "2021,Coal,120\n"
                "not-a-year,Solar,40\n"
                "2020,Coal,100\n"
                "2021,Solar,50\n",
                encoding="utf-8",
            )

            values = year_values(csv_path, "year")

        self.assertEqual(values, (2020, 2021))

    def test_loads_project_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "project.json"
            project_path.write_text(
                json.dumps({"name": "loaded", "chart": {"title": "Loaded"}}),
                encoding="utf-8",
            )

            loaded = load_project_data(project_path)

        self.assertEqual(loaded["name"], "loaded")
        self.assertEqual(loaded["chart"]["title"], "Loaded")

    def test_extracts_project_form_values_from_existing_project(self):
        values = project_form_values(
            {
                "name": "electricity",
                "chart": {
                    "title": "Electricity",
                    "output_file": "output/custom.mp4",
                    "frames_dir": "output/custom_frames",
                    "layout_preset": "vertical_shorts",
                    "theme": "midnight_contrast",
                    "typography_preset": "compact",
                    "value_format": "integer",
                    "fps": 12,
                    "steps_per_transition": 6,
                    "max_visible_bars": 5,
                },
                "selection": {
                    "top_n": 5,
                    "aggregate_other": True,
                },
                "data_source": {
                    "csv_path": "data/custom.csv",
                    "source_label_override": "Source: Custom",
                },
                "dataset": {
                    "year_column": "period",
                    "name_column": "source",
                    "value_column": "amount",
                },
                "categories": {
                    "Coal": {
                        "label": "Carbon",
                        "color": "#333333",
                    },
                },
            }
        )

        self.assertEqual(values["name"], "electricity")
        self.assertEqual(values["title"], "Electricity")
        self.assertEqual(values["csv_path"], "data/custom.csv")
        self.assertEqual(values["source_label"], "Source: Custom")
        self.assertEqual(values["year_column"], "period")
        self.assertEqual(values["name_column"], "source")
        self.assertEqual(values["value_column"], "amount")
        self.assertEqual(values["layout_preset"], "vertical_shorts")
        self.assertEqual(values["theme"], "midnight_contrast")
        self.assertEqual(values["typography_preset"], "compact")
        self.assertEqual(values["value_format"], "integer")
        self.assertEqual(values["fps"], 12)
        self.assertEqual(values["steps_per_transition"], 6)
        self.assertEqual(values["top_n"], 5)
        self.assertEqual(values["max_visible_bars"], 5)
        self.assertTrue(values["aggregate_other"])
        self.assertEqual(values["output_file"], "output/custom.mp4")
        self.assertEqual(values["frames_dir"], "output/custom_frames")
        self.assertEqual(values["categories"]["Coal"]["label"], "Carbon")
        self.assertEqual(values["categories"]["Coal"]["color"], "#333333")

    def test_preserves_unexposed_fields_when_rebuilding_existing_project(self):
        base_project = {
            "name": "electricity",
            "chart": {
                "title": "Old",
                "left_margin": 420,
                "source_x": 420,
                "bar_shadow_alpha": 0.2,
            },
            "animation": {
                "easing": "linear",
                "enter_exit": False,
            },
            "selection": {
                "top_n": 5,
                "other_label": "Rest",
            },
            "data_source": {
                "source_type": "csv",
                "csv_path": "old.csv",
            },
            "dataset": {
                "year_column": "year",
            },
            "categories": {
                "Coal": {
                    "label": "Carbon",
                    "color": "#333333",
                },
            },
        }

        project_data = build_project_data(
            name="electricity",
            csv_path="data/new.csv",
            year_column="year",
            name_column="country",
            value_column="value",
            title="New",
            source_label="Source: New",
            output_file="output/new.mp4",
            frames_dir="output/new_frames",
            layout_preset="youtube_1080p",
            theme="clean_report",
            typography_preset="editorial",
            value_format="decimal",
            fps=24,
            steps_per_transition=24,
            top_n=8,
            max_visible_bars=8,
            base_project_data=base_project,
        )

        self.assertEqual(project_data["chart"]["title"], "New")
        self.assertEqual(project_data["chart"]["left_margin"], 420)
        self.assertEqual(project_data["chart"]["source_x"], 420)
        self.assertEqual(project_data["chart"]["bar_shadow_alpha"], 0.2)
        self.assertEqual(project_data["animation"]["easing"], "linear")
        self.assertFalse(project_data["animation"]["enter_exit"])
        self.assertEqual(project_data["selection"]["top_n"], 8)
        self.assertEqual(project_data["selection"]["other_label"], "Rest")
        self.assertEqual(project_data["data_source"]["csv_path"], "data/new.csv")
        self.assertEqual(project_data["dataset"]["name_column"], "country")
        self.assertEqual(project_data["categories"]["Coal"]["label"], "Carbon")

    def test_replaces_category_styles_when_rebuilding_project(self):
        base_project = {
            "name": "electricity",
            "categories": {
                "Coal": {
                    "label": "Carbon",
                    "color": "#333333",
                },
            },
        }

        project_data = build_project_data(
            name="electricity",
            csv_path="data/new.csv",
            year_column="year",
            name_column="country",
            value_column="value",
            title="New",
            source_label="Source: New",
            output_file="output/new.mp4",
            frames_dir="output/new_frames",
            layout_preset="youtube_1080p",
            theme="clean_report",
            typography_preset="editorial",
            value_format="decimal",
            fps=24,
            steps_per_transition=24,
            top_n=8,
            max_visible_bars=8,
            category_styles={
                "Coal": {"label": "Coal"},
                "Solar": {"color": "#F2C94C"},
            },
            base_project_data=base_project,
        )

        self.assertNotIn("Coal", project_data["categories"])
        self.assertEqual(project_data["categories"]["Solar"]["color"], "#F2C94C")

    def test_cleans_category_styles(self):
        styles = clean_category_styles(
            {
                "Coal": {"label": " Carbon ", "color": " #333333 "},
                "Solar": {"label": "Solar", "color": ""},
                "": {"label": "Missing"},
                "Wind": "blue",
            }
        )

        self.assertEqual(
            styles,
            {
                "Coal": {
                    "label": "Carbon",
                    "color": "#333333",
                },
            },
        )

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
