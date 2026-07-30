import unittest

import _test_path
from studio.project_draft import (
    ProjectDraft,
    auto_preview_fingerprint,
    preview_fingerprint,
    project_fingerprint,
)


class ProjectDraftTest(unittest.TestCase):
    def test_fingerprint_is_stable_for_equivalent_mapping_order(self):
        first = {"name": "demo", "chart": {"title": "Demo", "fps": 30}}
        second = {"chart": {"fps": 30, "title": "Demo"}, "name": "demo"}

        self.assertEqual(
            project_fingerprint(first, "projects/demo.json"),
            project_fingerprint(second, "projects/demo.json"),
        )

    def test_project_path_participates_in_fingerprint(self):
        project_data = {"name": "demo"}

        self.assertNotEqual(
            project_fingerprint(project_data, "projects/first.json"),
            project_fingerprint(project_data, "projects/second.json"),
        )

    def test_create_takes_an_isolated_snapshot(self):
        project_data = {"chart": {"title": "Original"}}
        preview_settings = {"year": 2020}
        draft = ProjectDraft.create(
            project_data,
            " projects/demo.json ",
            preview_settings,
        )

        project_data["chart"]["title"] = "Changed"
        preview_settings["year"] = 2021

        self.assertEqual(draft.project_file, "projects/demo.json")
        self.assertEqual(draft.project_data["chart"]["title"], "Original")
        self.assertEqual(draft.preview_settings["year"], 2020)

    def test_reports_unsaved_changes_against_saved_fingerprint(self):
        original = ProjectDraft.create(
            {"chart": {"title": "Original"}},
            "projects/demo.json",
        )
        changed = ProjectDraft.create(
            {"chart": {"title": "Changed"}},
            "projects/demo.json",
        )

        self.assertFalse(original.is_dirty(original.fingerprint))
        self.assertTrue(changed.is_dirty(original.fingerprint))

    def test_auto_preview_fingerprint_tracks_visual_settings(self):
        project_data = {
            "chart": {
                "title": "Demo",
                "label_font_size": 32,
                "output_file": "output/demo.mp4",
            },
            "selection": {"top_n": 10},
            "categories": {"Coal": {"color": "#123456"}},
            "data_source": {"csv_path": "data/demo.csv"},
        }

        changed_size = {
            **project_data,
            "chart": {
                **project_data["chart"],
                "label_font_size": 36,
            },
        }
        changed_category = {
            **project_data,
            "categories": {"Coal": {"color": "#654321"}},
        }

        self.assertNotEqual(
            auto_preview_fingerprint(project_data),
            auto_preview_fingerprint(changed_size),
        )
        self.assertNotEqual(
            auto_preview_fingerprint(project_data),
            auto_preview_fingerprint(changed_category),
        )

    def test_auto_preview_fingerprint_ignores_data_and_export_changes(self):
        project_data = {
            "chart": {
                "title": "Demo",
                "label_font_size": 32,
                "fps": 24,
                "output_file": "output/demo.mp4",
            },
            "data_source": {
                "csv_path": "data/demo.csv",
                "source_label_override": "Source A",
            },
            "dataset": {"value_column": "value"},
        }
        changed = {
            **project_data,
            "chart": {
                **project_data["chart"],
                "title": "Changed",
                "fps": 60,
                "output_file": "output/changed.mp4",
            },
            "data_source": {
                "csv_path": "data/changed.csv",
                "source_label_override": "Source B",
            },
            "dataset": {"value_column": "total"},
        }

        self.assertEqual(
            auto_preview_fingerprint(project_data),
            auto_preview_fingerprint(changed),
        )
        self.assertNotEqual(
            preview_fingerprint(project_data),
            preview_fingerprint(changed),
        )

    def test_preview_frame_selection_triggers_auto_preview(self):
        project_data = {"chart": {"label_font_size": 32}}

        self.assertNotEqual(
            auto_preview_fingerprint(
                project_data,
                {"year": 2020, "preview_mode": "year"},
            ),
            auto_preview_fingerprint(
                project_data,
                {"year": 2021, "preview_mode": "year"},
            ),
        )

    def test_preview_fingerprint_ignores_video_only_settings(self):
        original = {
            "chart": {
                "label_font_size": 32,
                "fps": 24,
                "steps_per_transition": 45,
                "frame_output_mode": "ffmpeg_stream",
            }
        }
        changed = {
            "chart": {
                "label_font_size": 32,
                "fps": 60,
                "steps_per_transition": 120,
                "frame_output_mode": "png_sequence",
            }
        }

        self.assertEqual(
            preview_fingerprint(original),
            preview_fingerprint(changed),
        )


if __name__ == "__main__":
    unittest.main()
