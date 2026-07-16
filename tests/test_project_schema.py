import unittest

import _test_path
from config.project_schema import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    ProjectSchemaError,
    migrate_project_data,
)


class ProjectSchemaTest(unittest.TestCase):
    def test_migrates_unversioned_project_without_mutating_input(self):
        original = {
            "name": "legacy",
            "chart": {
                "title": "Legacy",
                "bar_logo_position": "inside",
                "animation": {"motion_mode": "continuous", "easing": "linear"},
                "selection": {"top_n": 5},
            },
            "animation": {"easing": "ease_out_cubic"},
        }

        migration = migrate_project_data(original)

        self.assertTrue(migration.migrated)
        self.assertEqual(migration.original_version, 0)
        self.assertEqual(migration.applied_migrations, ("0_to_1",))
        self.assertEqual(
            migration.data["schema_version"],
            CURRENT_PROJECT_SCHEMA_VERSION,
        )
        self.assertEqual(
            migration.data["chart"]["bar_logo_position"],
            "inside_left",
        )
        self.assertNotIn("animation", migration.data["chart"])
        self.assertEqual(
            migration.data["animation"],
            {
                "motion_mode": "continuous",
                "easing": "ease_out_cubic",
            },
        )
        self.assertNotIn("schema_version", original)
        self.assertIn("animation", original["chart"])

    def test_current_project_is_copied_without_migration(self):
        project = {"schema_version": 1, "name": "current"}

        migration = migrate_project_data(project)

        self.assertFalse(migration.migrated)
        self.assertEqual(migration.data, project)
        self.assertIsNot(migration.data, project)

    def test_rejects_future_schema(self):
        with self.assertRaisesRegex(ProjectSchemaError, "newer than supported"):
            migrate_project_data({"schema_version": 99})

    def test_rejects_invalid_schema_version(self):
        for value in (True, -1, 1.5, "1"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ProjectSchemaError,
                    "non-negative integer",
                ):
                    migrate_project_data({"schema_version": value})

    def test_rejects_invalid_legacy_nested_section(self):
        with self.assertRaisesRegex(ProjectSchemaError, "chart.animation"):
            migrate_project_data({"chart": {"animation": "linear"}})


if __name__ == "__main__":
    unittest.main()
