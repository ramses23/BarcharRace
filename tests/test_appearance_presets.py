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
                "max_visible_bars": 7,
                "title_font_size": 44,
                "title_text_color": "#ABCDEF",
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
                "editorial_headline_size": 36,
                "editorial_body_size": 22,
                "editorial_credit_size": 13,
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
        self.assertEqual(preset.bars["bar_shape"], "capsule")
        self.assertEqual(preset.bars["logo_size"], 42)
        self.assertEqual(preset.bars["bar_secondary_logo_size"], 19)
        self.assertEqual(preset.fun_facts["layout"], "editorial_right")
        self.assertEqual(
            preset.fun_facts["editorial_background_mode"],
            "transparent",
        )
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
