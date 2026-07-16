import unittest

import _test_path
from studio.project_draft import ProjectDraft, project_fingerprint


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


if __name__ == "__main__":
    unittest.main()
