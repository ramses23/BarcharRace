import json
import tempfile
import unittest
from pathlib import Path

import _test_path
from studio.project_builder import (
    apply_category_logo_matches,
    build_project_data,
    category_values,
    clean_category_styles,
    default_project_paths,
    inspect_csv,
    load_project_data,
    logo_match_key,
    match_category_logos,
    preferred_column,
    project_defaults_from_csv_path,
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
            background_mode="image",
            background_color_override="#102030",
            background_image_path="backgrounds/studio.png",
            background_image_fit="contain",
            typography_preset="editorial",
            value_format="decimal",
            fps=24,
            steps_per_transition=24,
            top_n=8,
            max_visible_bars=8,
            png_compress_level=0,
            bar_shape="lollipop",
            bar_gradient_enabled=False,
            bar_border_enabled=True,
            bar_border_color="#123456",
            bar_border_width=2.5,
            bar_shadow_enabled=True,
            bar_shadow_color="#111111",
            bar_shadow_alpha=0.25,
            bar_shadow_offset_x=6,
            bar_shadow_offset_y=3,
            title_font_family="DejaVu Serif",
            label_font_family="DejaVu Sans Mono",
            time_label_font_family="DejaVu Serif",
            source_font_family="DejaVu Sans",
            rank_label_font_family="DejaVu Sans Mono",
            title_text_color="#101112",
            subtitle_text_color="#202122",
            label_text_color="#303132",
            value_text_color="#404142",
            time_label_text_color="#505152",
            source_text_color="#606162",
            rank_label_text_color="#707172",
            title_font_size=42,
            subtitle_font_size=24,
            label_font_size=21,
            value_font_size=19,
            time_label_font_size=128,
            source_font_size=15,
            rank_label_font_size=17,
            title_x=300,
            title_y=90,
            subtitle_x=310,
            subtitle_y=160,
            time_label_x=1500,
            time_label_y=900,
            source_x=300,
            source_y=1000,
            motion_mode="continuous",
            category_styles={
                "Coal": {
                    "label": "Carbon",
                    "color": "#333333",
                    "logo": "logos/coal.png",
                    "secondary_logo": "logos_secondary/coal.png",
                },
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
        self.assertEqual(loaded["chart"]["png_compress_level"], 0)
        self.assertEqual(loaded["chart"]["background_mode"], "image")
        self.assertEqual(
            loaded["chart"]["background_image_path"],
            "backgrounds/studio.png",
        )
        self.assertEqual(loaded["chart"]["background_image_fit"], "contain")
        self.assertEqual(loaded["chart"]["bar_shape"], "lollipop")
        self.assertFalse(loaded["chart"]["bar_gradient_enabled"])
        self.assertTrue(loaded["chart"]["bar_border_enabled"])
        self.assertEqual(loaded["chart"]["bar_border_color"], "#123456")
        self.assertEqual(loaded["chart"]["bar_border_width"], 2.5)
        self.assertEqual(loaded["chart"]["bar_shadow_alpha"], 0.25)
        self.assertEqual(loaded["chart"]["title_font_family"], "DejaVu Serif")
        self.assertEqual(loaded["chart"]["label_font_family"], "DejaVu Sans Mono")
        self.assertEqual(loaded["chart"]["time_label_font_family"], "DejaVu Serif")
        self.assertEqual(loaded["chart"]["source_font_family"], "DejaVu Sans")
        self.assertEqual(
            loaded["chart"]["rank_label_font_family"],
            "DejaVu Sans Mono",
        )
        self.assertEqual(loaded["chart"]["title_text_color"], "#101112")
        self.assertEqual(loaded["chart"]["subtitle_text_color"], "#202122")
        self.assertEqual(loaded["chart"]["label_text_color"], "#303132")
        self.assertEqual(loaded["chart"]["value_text_color"], "#404142")
        self.assertEqual(loaded["chart"]["time_label_text_color"], "#505152")
        self.assertEqual(loaded["chart"]["source_text_color"], "#606162")
        self.assertEqual(loaded["chart"]["rank_label_text_color"], "#707172")
        self.assertEqual(loaded["chart"]["title_font_size"], 42)
        self.assertEqual(loaded["chart"]["rank_label_font_size"], 17)
        self.assertEqual(loaded["chart"]["title_x"], 300)
        self.assertEqual(loaded["chart"]["subtitle_x"], 310)
        self.assertEqual(loaded["chart"]["time_label_y"], 900)
        self.assertEqual(loaded["chart"]["source_y"], 1000)
        self.assertEqual(loaded["animation"]["motion_mode"], "continuous")
        self.assertEqual(loaded["categories"]["Coal"]["label"], "Carbon")
        self.assertEqual(loaded["categories"]["Coal"]["color"], "#333333")
        self.assertEqual(loaded["categories"]["Coal"]["logo"], "logos/coal.png")
        self.assertEqual(
            loaded["categories"]["Coal"]["secondary_logo"],
            "logos_secondary/coal.png",
        )
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

    def test_persists_advanced_bar_appearance_and_restores_form_values(self):
        bar_style = {
            "bar_appearance_mode": "advanced",
            "bar_shape": "capsule",
            "bar_fill_type": "texture",
            "bar_gradient_direction": "diagonal",
            "bar_gradient_color_count": 2,
            "bar_fill_use_category_color": False,
            "bar_fill_color_start": "#112233",
            "bar_fill_color_center": "#445566",
            "bar_fill_color_end": "#778899",
            "bar_texture_enabled": True,
            "bar_texture_preset": "carbon",
            "bar_texture_blend_mode": "soft_light",
            "bar_bevel_enabled": True,
            "bar_inner_shadow_opacity": 0.25,
            "bar_outer_glow_enabled": True,
            "bar_track_enabled": True,
            "bar_logo_position": "inside_right",
            "bar_logo_shape": "circle",
            "bar_logo_padding": 5,
            "bar_logo_border_enabled": True,
            "bar_logo_background_enabled": True,
            "bar_label_position": "inside",
            "bar_label_alignment": "left",
            "bar_value_position": "above",
        }
        project_data = build_project_data(
            name="advanced",
            csv_path="data/advanced.csv",
            year_column="year",
            name_column="name",
            value_column="value",
            title="Advanced",
            source_label="Source: Test",
            output_file="output/advanced.mp4",
            frames_dir="output/advanced_frames",
            layout_preset="youtube_1080p",
            theme="clean_report",
            typography_preset="editorial",
            value_format="decimal",
            fps=24,
            steps_per_transition=24,
            top_n=8,
            max_visible_bars=8,
            bar_style=bar_style,
        )
        values = project_form_values(project_data)

        for key, value in bar_style.items():
            self.assertEqual(project_data["chart"][key], value)
            self.assertEqual(values[key], value)

        self.assertIn("bar_shine_width", project_data["chart"])
        self.assertIn("bar_value_shadow_color", project_data["chart"])

    def test_extracts_all_category_values_without_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "many_categories.csv"
            rows = ["year,country,value"]
            rows.extend(f"2020,Team {index:03d},{index}" for index in range(85))
            csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

            limited_values = category_values(csv_path, "country")
            all_values = category_values(csv_path, "country", limit=None)

        self.assertEqual(len(limited_values), 80)
        self.assertEqual(len(all_values), 85)
        self.assertEqual(all_values[-1], "Team 084")

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

    def test_matches_category_logos_by_file_name(self):
        matches = match_category_logos(
            ("Argentina", "United States", "México", "No Match"),
            (
                "logos/argentina.png",
                "logos/united_states.webp",
                "logos/Mexico.jpg",
                "logos/extra.png",
            ),
        )

        self.assertEqual(matches["Argentina"], "logos/argentina.png")
        self.assertEqual(matches["United States"], "logos/united_states.webp")
        self.assertEqual(matches["México"], "logos/Mexico.jpg")
        self.assertNotIn("No Match", matches)

    def test_normalizes_logo_match_keys(self):
        self.assertEqual(logo_match_key("México / USA"), "mexico_usa")
        self.assertEqual(logo_match_key("National-Team Goals"), "national_team_goals")

    def test_applies_category_logo_matches_to_all_styles(self):
        styles = apply_category_logo_matches(
            {
                "Team 001": {
                    "label": "First Team",
                    "color": "#111111",
                },
            },
            {
                "Team 001": "logos/team_001.png",
                "Team 318": "logos/team_318.png",
            },
        )

        self.assertEqual(styles["Team 001"]["label"], "First Team")
        self.assertEqual(styles["Team 001"]["color"], "#111111")
        self.assertEqual(styles["Team 001"]["logo"], "logos/team_001.png")
        self.assertEqual(styles["Team 318"]["logo"], "logos/team_318.png")

    def test_applies_matches_to_secondary_logo_without_replacing_primary(self):
        styles = apply_category_logo_matches(
            {"Team 001": {"logo": "portraits/team_001.png"}},
            {"Team 001": "flags/team_001.png"},
            logo_field="secondary_logo",
        )

        self.assertEqual(styles["Team 001"]["logo"], "portraits/team_001.png")
        self.assertEqual(
            styles["Team 001"]["secondary_logo"],
            "flags/team_001.png",
        )

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
                    "png_compress_level": 3,
                    "title_font_family": "DejaVu Serif",
                    "label_font_family": "DejaVu Sans Mono",
                    "time_label_font_family": "DejaVu Serif",
                    "source_font_family": "DejaVu Sans",
                    "rank_label_font_family": "DejaVu Sans Mono",
                    "title_text_color": "#101112",
                    "subtitle_text_color": "#202122",
                    "label_text_color": "#303132",
                    "value_text_color": "#404142",
                    "time_label_text_color": "#505152",
                    "source_text_color": "#606162",
                    "rank_label_text_color": "#707172",
                    "title_font_size": 42,
                    "rank_label_font_size": 17,
                    "title_x": 300,
                    "title_y": 90,
                    "subtitle_x": 310,
                    "subtitle_y": 160,
                    "time_label_x": 1500,
                    "time_label_y": 900,
                    "source_x": 300,
                    "source_y": 1000,
                },
                "selection": {
                    "top_n": 5,
                    "aggregate_other": True,
                },
                "animation": {
                    "motion_mode": "continuous",
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
                        "logo": "logos/coal.png",
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
        self.assertEqual(values["png_compress_level"], 3)
        self.assertEqual(values["title_font_family"], "DejaVu Serif")
        self.assertEqual(values["label_font_family"], "DejaVu Sans Mono")
        self.assertEqual(values["time_label_font_family"], "DejaVu Serif")
        self.assertEqual(values["source_font_family"], "DejaVu Sans")
        self.assertEqual(values["rank_label_font_family"], "DejaVu Sans Mono")
        self.assertEqual(values["title_text_color"], "#101112")
        self.assertEqual(values["subtitle_text_color"], "#202122")
        self.assertEqual(values["label_text_color"], "#303132")
        self.assertEqual(values["value_text_color"], "#404142")
        self.assertEqual(values["time_label_text_color"], "#505152")
        self.assertEqual(values["source_text_color"], "#606162")
        self.assertEqual(values["rank_label_text_color"], "#707172")
        self.assertEqual(values["title_font_size"], 42)
        self.assertEqual(values["rank_label_font_size"], 17)
        self.assertEqual(values["title_x"], 300)
        self.assertEqual(values["title_y"], 90)
        self.assertEqual(values["subtitle_x"], 310)
        self.assertEqual(values["subtitle_y"], 160)
        self.assertEqual(values["time_label_x"], 1500)
        self.assertEqual(values["time_label_y"], 900)
        self.assertEqual(values["source_x"], 300)
        self.assertEqual(values["source_y"], 1000)
        self.assertEqual(values["motion_mode"], "continuous")
        self.assertTrue(values["aggregate_other"])
        self.assertEqual(values["output_file"], "output/custom.mp4")
        self.assertEqual(values["frames_dir"], "output/custom_frames")
        self.assertEqual(values["categories"]["Coal"]["label"], "Carbon")
        self.assertEqual(values["categories"]["Coal"]["color"], "#333333")
        self.assertEqual(values["categories"]["Coal"]["logo"], "logos/coal.png")

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
                "motion_mode": "continuous",
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
                    "logo": "logos/coal.png",
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
        self.assertEqual(project_data["animation"]["motion_mode"], "continuous")
        self.assertEqual(project_data["selection"]["top_n"], 8)
        self.assertEqual(project_data["selection"]["other_label"], "Rest")
        self.assertEqual(project_data["data_source"]["csv_path"], "data/new.csv")
        self.assertEqual(project_data["dataset"]["name_column"], "country")
        self.assertEqual(project_data["categories"]["Coal"]["label"], "Carbon")
        self.assertEqual(project_data["categories"]["Coal"]["logo"], "logos/coal.png")

    def test_replaces_category_styles_when_rebuilding_project(self):
        base_project = {
            "name": "electricity",
            "categories": {
                "Coal": {
                    "label": "Carbon",
                    "color": "#333333",
                    "logo": "logos/coal.png",
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
            png_compress_level=0,
            category_styles={
                "Coal": {"label": "Coal"},
                "Solar": {"color": "#F2C94C", "logo": "logos/solar.png"},
            },
            base_project_data=base_project,
        )

        self.assertNotIn("Coal", project_data["categories"])
        self.assertEqual(project_data["categories"]["Solar"]["color"], "#F2C94C")
        self.assertEqual(project_data["categories"]["Solar"]["logo"], "logos/solar.png")

    def test_cleans_category_styles(self):
        styles = clean_category_styles(
            {
                "Coal": {"label": " Carbon ", "color": " #333333 "},
                "Solar": {"label": "Solar", "color": "", "logo": ""},
                "Hydro": {
                    "logo": " logos/hydro.png ",
                    "secondary_logo": " flags/hydro.png ",
                },
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
                "Hydro": {
                    "logo": "logos/hydro.png",
                    "secondary_logo": "flags/hydro.png",
                },
            },
        )

    def test_builds_project_name_and_default_paths(self):
        name = project_name_from_title("Electricity by Source!")
        paths = default_project_paths(name)

        self.assertEqual(name, "electricity_by_source")
        self.assertEqual(paths["project_file"], "projects/electricity_by_source.json")
        self.assertEqual(paths["output_file"], "output/electricity_by_source.mp4")

    def test_builds_project_defaults_from_csv_path(self):
        defaults = project_defaults_from_csv_path(
            "data/datasets/national_team_goals_2005_2024.csv"
        )

        self.assertEqual(defaults["name"], "national_team_goals_2005_2024")
        self.assertEqual(defaults["title"], "National Team Goals 2005 2024")
        self.assertEqual(
            defaults["project_file"],
            "projects/national_team_goals_2005_2024.json",
        )
        self.assertEqual(
            defaults["output_file"],
            "output/national_team_goals_2005_2024.mp4",
        )
        self.assertEqual(
            defaults["frames_dir"],
            "output/national_team_goals_2005_2024_frames",
        )

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
