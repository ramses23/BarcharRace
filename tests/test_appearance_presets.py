import copy
import json
import tempfile
import unittest
from pathlib import Path

import _test_path
from studio.appearance_presets import (
    APPEARANCE_PRESET_SCHEMA_VERSION,
    BAR_APPEARANCE_FIELDS,
    CANVAS_APPEARANCE_FIELDS,
    FUN_FACT_APPEARANCE_FIELDS,
    AppearancePresetError,
    apply_appearance_preset,
    build_appearance_preset,
    delete_appearance_preset,
    load_appearance_preset,
    load_appearance_preset_catalog,
    save_appearance_preset,
)


class AppearancePresetsTest(unittest.TestCase):
    def project_data(self):
        return {
            "name": "source-project",
            "chart": {
                "title": "Project-specific title",
                "output_file": "output/source.mp4",
                "fps": 60,
                "layout_preset": "vertical_shorts",
                "theme": "midnight_contrast",
                "typography_preset": "compact",
                "background_mode": "image",
                "background_image_path": "backgrounds/documentary.png",
                "background_image_fit": "cover",
                "background_motion": "horizontal_speed_lines",
                "background_motion_speed": 1.4,
                "background_motion_intensity": 0.45,
                "background_motion_line_spacing": 144,
                "background_motion_line_thickness": 5,
                "background_motion_line_color": "#12AB34",
                "background_motion_response": "leader_acceleration",
                "background_motion_response_strength": 1.7,
                "background_motion_exit_compression": True,
                "background_motion_exit_compression_strength": 0.7,
                "max_visible_bars": 7,
                "title_font_size": 44,
                "title_text_color": "#ABCDEF",
                "title_text_opacity": 0.84,
                "subtitle_text_opacity": 0.73,
                "label_text_opacity": 0.62,
                "value_text_opacity": 0.51,
                "time_label_opacity": 0.47,
                "source_text_opacity": 0.4,
                "rank_label_text_opacity": 0.35,
                "left_margin": 240,
                "bar_appearance_mode": "advanced",
                "bar_shape": "capsule",
                "bar_fill_type": "texture",
                "bar_texture_enabled": True,
                "bar_texture_preset": "custom_image",
                "bar_texture_custom_image": "textures/brushed.png",
                "bar_secondary_logo_size": 19,
                "logo_size": 42,
                "value_format": "compact",
            },
            "selection": {
                "top_n": 5,
                "aggregate_other": True,
            },
            "dataset": {
                "year_column": "year",
                "name_column": "company",
                "value_column": "sales",
            },
            "categories": {
                "Toyota": {
                    "color": "#FF0000",
                    "logo": "logos/toyota.png",
                },
            },
            "fun_facts": {
                "enabled": True,
                "source": "fun_facts/source-project.json",
                "layout": "editorial_right",
                "panel_width": 480,
                "panel_margin": 24,
                "panel_padding": 20,
                "fade_in": 0.3,
                "fade_out": 0.4,
                "editorial_background_mode": "transparent",
                "editorial_background_color": "#102030",
                "editorial_background_texture": "paper",
                "editorial_background_texture_intensity": 0.33,
                "editorial_headline_size": 36,
                "editorial_headline_color": "#F0F0F0",
                "editorial_headline_opacity": 0.9,
                "editorial_body_size": 22,
                "editorial_body_color": "#D0D0D0",
                "editorial_body_opacity": 0.8,
                "editorial_credit_size": 13,
                "editorial_credit_color": "#B0B0B0",
                "editorial_credit_opacity": 0.7,
                "editorial_image_area_ratio": 0.5,
                "editorial_image_fit": "cover",
                "editorial_text_image_gap": 21,
                "editorial_top_offset": 17,
                "editorial_reposition_time_label": False,
            },
        }

    def test_builds_complete_visual_only_preset(self):
        preset = build_appearance_preset("Documentary dark", self.project_data())

        self.assertEqual(preset.name, "Documentary dark")
        self.assertEqual(set(preset.canvas), set(CANVAS_APPEARANCE_FIELDS))
        self.assertEqual(set(preset.bars), set(BAR_APPEARANCE_FIELDS))
        self.assertEqual(
            set(preset.fun_facts),
            set(FUN_FACT_APPEARANCE_FIELDS),
        )
        self.assertEqual(preset.canvas["layout_preset"], "vertical_shorts")
        self.assertEqual(preset.canvas["title_font_size"], 44)
        self.assertEqual(preset.canvas["time_label_opacity"], 0.47)
        self.assertEqual(preset.canvas["title_text_opacity"], 0.84)
        self.assertEqual(
            preset.canvas["background_motion"],
            "horizontal_speed_lines",
        )
        self.assertEqual(
            preset.canvas["background_motion_line_color"],
            "#12AB34",
        )
        self.assertEqual(
            preset.canvas["background_motion_response"],
            "leader_acceleration",
        )
        self.assertTrue(
            preset.canvas["background_motion_exit_compression"]
        )
        self.assertEqual(
            preset.canvas["background_motion_exit_compression_strength"],
            0.7,
        )
        self.assertEqual(preset.bars["bar_shape"], "capsule")
        self.assertEqual(preset.bars["logo_size"], 42)
        self.assertEqual(preset.bars["bar_secondary_logo_size"], 19)
        self.assertEqual(preset.fun_facts["layout"], "editorial_right")
        self.assertEqual(
            preset.fun_facts["editorial_background_mode"],
            "transparent",
        )
        self.assertEqual(preset.fun_facts["editorial_background_texture"], "paper")
        self.assertEqual(preset.fun_facts["editorial_body_opacity"], 0.8)
        self.assertNotIn("enabled", preset.fun_facts)
        self.assertNotIn("source", preset.fun_facts)
        self.assertNotIn("title", preset.chart_values)
        self.assertNotIn("output_file", preset.chart_values)
        self.assertNotIn("fps", preset.chart_values)
        self.assertNotIn("top_n", preset.chart_values)

    def test_saves_loads_and_updates_preset_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir) / "appearance"
            original = build_appearance_preset("Documentary dark", self.project_data())
            stored = save_appearance_preset(original, directory)
            loaded = load_appearance_preset(stored.path)

            self.assertEqual(stored.path.name, "documentary_dark.json")
            self.assertEqual(loaded.to_dict(), original.to_dict())
            self.assertEqual(
                json.loads(stored.path.read_text(encoding="utf-8"))[
                    "schema_version"
                ],
                APPEARANCE_PRESET_SCHEMA_VERSION,
            )

            with self.assertRaisesRegex(AppearancePresetError, "already exists"):
                save_appearance_preset(original, directory)

            updated_project = self.project_data()
            updated_project["chart"]["title_font_size"] = 58
            updated = build_appearance_preset("Documentary dark", updated_project)
            save_appearance_preset(updated, directory, overwrite=True)

            self.assertEqual(
                load_appearance_preset(stored.path).canvas["title_font_size"],
                58,
            )

    def test_schema_six_defaults_new_speed_line_fields(self):
        current = build_appearance_preset(
            "Legacy motion",
            self.project_data(),
        ).to_dict()
        current["schema_version"] = 6
        for field in (
            "background_motion_line_spacing",
            "background_motion_line_thickness",
            "background_motion_line_color",
            "background_motion_response",
            "background_motion_response_strength",
            "background_motion_exit_compression",
            "background_motion_exit_compression_strength",
        ):
            current["canvas"].pop(field)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy_motion.json"
            path.write_text(json.dumps(current), encoding="utf-8")
            loaded = load_appearance_preset(path)

        self.assertEqual(loaded.schema_version, 6)
        self.assertEqual(loaded.canvas["background_motion_line_spacing"], 160.0)
        self.assertEqual(loaded.canvas["background_motion_line_thickness"], 2.0)
        self.assertEqual(loaded.canvas["background_motion_line_color"], "#FFFFFF")
        self.assertEqual(loaded.canvas["background_motion_response"], "constant")
        self.assertFalse(
            loaded.canvas["background_motion_exit_compression"]
        )
        self.assertEqual(
            loaded.canvas["background_motion_exit_compression_strength"],
            0.5,
        )

    def test_applies_visual_fields_without_mutating_or_copying_project_content(self):
        source = self.project_data()
        preset = build_appearance_preset("Documentary dark", source)
        target = {
            "name": "target-project",
            "chart": {
                "title": "Keep this title",
                "output_file": "output/target.mp4",
                "fps": 24,
                "bar_shape": "rectangle",
            },
            "selection": {"top_n": 12, "aggregate_other": False},
            "dataset": {"name_column": "country"},
            "categories": {"Mexico": {"color": "#00FF00"}},
            "fun_facts": {
                "enabled": True,
                "source": "fun_facts/target-project.json",
                "layout": "right_panel",
                "editorial_headline_size": 20,
            },
        }
        original = copy.deepcopy(target)

        applied = apply_appearance_preset(target, preset)

        self.assertEqual(target, original)
        self.assertEqual(applied["name"], "target-project")
        self.assertEqual(applied["chart"]["title"], "Keep this title")
        self.assertEqual(applied["chart"]["output_file"], "output/target.mp4")
        self.assertEqual(applied["chart"]["fps"], 24)
        self.assertEqual(applied["chart"]["bar_shape"], "capsule")
        self.assertEqual(applied["chart"]["title_font_size"], 44)
        self.assertEqual(applied["selection"], original["selection"])
        self.assertEqual(applied["dataset"], original["dataset"])
        self.assertEqual(applied["categories"], original["categories"])
        self.assertTrue(applied["fun_facts"]["enabled"])
        self.assertEqual(
            applied["fun_facts"]["source"],
            "fun_facts/target-project.json",
        )
        self.assertEqual(applied["fun_facts"]["layout"], "editorial_right")
        self.assertEqual(applied["fun_facts"]["editorial_headline_size"], 36)

    def test_loads_v1_preset_without_overwriting_target_fun_facts(self):
        current = build_appearance_preset("Legacy preset", self.project_data())
        legacy_data = current.to_dict()
        legacy_data["schema_version"] = 1
        del legacy_data["fun_facts"]
        del legacy_data["bars"]["bar_label_offset_x"]
        del legacy_data["bars"]["bar_label_offset_y"]

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.json"
            path.write_text(json.dumps(legacy_data), encoding="utf-8")
            legacy = load_appearance_preset(path)

        target = {
            "name": "target-project",
            "chart": {},
            "fun_facts": {
                "enabled": True,
                "source": "fun_facts/target.json",
                "layout": "right_panel",
            },
        }
        applied = apply_appearance_preset(target, legacy)

        self.assertEqual(legacy.schema_version, 1)
        self.assertIsNone(legacy.fun_facts)
        self.assertEqual(legacy.bars["bar_label_offset_x"], 0)
        self.assertEqual(legacy.bars["bar_label_offset_y"], 0)
        self.assertEqual(applied["fun_facts"], target["fun_facts"])

    def test_loads_v2_preset_with_floating_editorial_defaults(self):
        current = build_appearance_preset("V2 preset", self.project_data())
        legacy_data = current.to_dict()
        legacy_data["schema_version"] = 2
        for field in (
            "editorial_orientation",
            "editorial_card_x",
            "editorial_card_y",
            "editorial_card_width",
            "editorial_card_height",
            "editorial_image_position",
            "editorial_collision_gap",
        ):
            del legacy_data["fun_facts"][field]

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "v2.json"
            path.write_text(json.dumps(legacy_data), encoding="utf-8")
            loaded = load_appearance_preset(path)

        self.assertEqual(loaded.schema_version, 2)
        self.assertEqual(loaded.fun_facts["editorial_orientation"], "vertical")
        self.assertIsNone(loaded.fun_facts["editorial_card_x"])
        self.assertEqual(loaded.fun_facts["editorial_image_position"], "right")
        self.assertEqual(loaded.fun_facts["editorial_collision_gap"], 24)

    def test_loads_v1_to_v3_presets_with_legacy_date_opacity(self):
        current = build_appearance_preset("Legacy opacity", self.project_data())

        for schema_version in (1, 2, 3):
            legacy_data = current.to_dict()
            legacy_data["schema_version"] = schema_version
            del legacy_data["canvas"]["time_label_opacity"]
            if schema_version == 1:
                del legacy_data["fun_facts"]
                del legacy_data["bars"]["bar_label_offset_x"]
                del legacy_data["bars"]["bar_label_offset_y"]
            if schema_version == 2:
                for field in (
                    "editorial_orientation",
                    "editorial_card_x",
                    "editorial_card_y",
                    "editorial_card_width",
                    "editorial_card_height",
                    "editorial_image_position",
                    "editorial_collision_gap",
                ):
                    del legacy_data["fun_facts"][field]

            with self.subTest(schema_version=schema_version):
                with tempfile.TemporaryDirectory() as temp_dir:
                    path = Path(temp_dir) / "legacy.json"
                    path.write_text(json.dumps(legacy_data), encoding="utf-8")
                    loaded = load_appearance_preset(path)

                self.assertEqual(loaded.canvas["time_label_opacity"], 0.22)

    def test_loads_v1_to_v4_presets_with_new_visual_defaults(self):
        current = build_appearance_preset("Legacy full opacity", self.project_data())
        new_canvas_fields = (
            "title_text_opacity",
            "subtitle_text_opacity",
            "label_text_opacity",
            "value_text_opacity",
            "source_text_opacity",
            "rank_label_text_opacity",
        )
        new_fun_fact_fields = (
            "editorial_background_texture",
            "editorial_background_texture_intensity",
            "editorial_headline_color",
            "editorial_headline_opacity",
            "editorial_body_color",
            "editorial_body_opacity",
            "editorial_credit_color",
            "editorial_credit_opacity",
        )

        for schema_version in (1, 2, 3, 4):
            data = current.to_dict()
            data["schema_version"] = schema_version
            for field in new_canvas_fields:
                del data["canvas"][field]
            if schema_version == 1:
                del data["fun_facts"]
                del data["bars"]["bar_label_offset_x"]
                del data["bars"]["bar_label_offset_y"]
            else:
                for field in new_fun_fact_fields:
                    del data["fun_facts"][field]
                if schema_version == 2:
                    for field in (
                        "editorial_orientation",
                        "editorial_card_x",
                        "editorial_card_y",
                        "editorial_card_width",
                        "editorial_card_height",
                        "editorial_image_position",
                        "editorial_collision_gap",
                    ):
                        del data["fun_facts"][field]

            with self.subTest(schema_version=schema_version), tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "legacy.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                loaded = load_appearance_preset(path)

                for field in new_canvas_fields:
                    self.assertEqual(loaded.canvas[field], 1.0)
                if schema_version >= 2:
                    self.assertEqual(loaded.fun_facts["editorial_background_texture"], "none")
                    self.assertEqual(loaded.fun_facts["editorial_headline_opacity"], 1.0)
                    self.assertEqual(loaded.fun_facts["editorial_body_opacity"], 1.0)
                    self.assertEqual(loaded.fun_facts["editorial_credit_opacity"], 1.0)

    def test_catalog_keeps_valid_presets_and_reports_invalid_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            preset = build_appearance_preset("Valid preset", self.project_data())
            save_appearance_preset(preset, directory)
            (directory / "broken.json").write_text("{broken", encoding="utf-8")

            catalog = load_appearance_preset_catalog(directory)

            self.assertEqual(
                tuple(item.name for item in catalog.presets),
                ("Valid preset",),
            )
            self.assertEqual(len(catalog.errors), 1)
            self.assertIn("Invalid JSON", catalog.errors[0])

    def test_rejects_unknown_missing_and_invalid_visual_fields(self):
        preset = build_appearance_preset("Strict preset", self.project_data())
        cases = []

        unknown = preset.to_dict()
        unknown["bars"]["top_n"] = 8
        cases.append(unknown)

        missing = preset.to_dict()
        del missing["canvas"]["layout_preset"]
        cases.append(missing)

        missing_fun_fact = preset.to_dict()
        del missing_fun_fact["fun_facts"]["layout"]
        cases.append(missing_fun_fact)

        invalid = preset.to_dict()
        invalid["bars"]["bar_shape"] = "triangle"
        cases.append(invalid)

        future = preset.to_dict()
        future["schema_version"] = 999
        cases.append(future)

        with tempfile.TemporaryDirectory() as temp_dir:
            for index, data in enumerate(cases):
                with self.subTest(index=index):
                    path = Path(temp_dir) / f"invalid_{index}.json"
                    path.write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaises(AppearancePresetError):
                        load_appearance_preset(path)

    def test_deletes_only_stored_preset_from_its_library(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir) / "appearance"
            preset = build_appearance_preset("Disposable", self.project_data())
            stored = save_appearance_preset(preset, directory)

            delete_appearance_preset(stored, directory)

            self.assertFalse(stored.path.exists())
            with self.assertRaises(AppearancePresetError):
                delete_appearance_preset(stored, directory)


if __name__ == "__main__":
    unittest.main()
