import copy
import tempfile
import unittest
from pathlib import Path

import _test_path
from config.animation_config import MIN_RANK_MOVEMENT_DURATION, AnimationConfig
from config.project_file_loader import load_project_data, load_project_file, ProjectFileError
from studio.project_builder import project_form_values, save_project_data
from studio.project_draft import ProjectDraft
from studio.short_export import apply_export_profile
from config.export_config import ExportConfig


class RankDurationDomainTest(unittest.TestCase):
    def test_domain_and_roundtrip_without_load_mutation(self):
        self.assertEqual(MIN_RANK_MOVEMENT_DURATION, .1)
        self.assertEqual(AnimationConfig().rank_movement_duration, 1.)
        for value in (.1, .2, .25, .39, .4, .75, 1.):
            data = {"animation": {"rank_movement_duration": value}}
            before = copy.deepcopy(data)
            loaded = load_project_data(data)
            self.assertEqual(data, before)
            self.assertEqual(loaded.chart_config.animation.rank_movement_duration, value)
            self.assertEqual(project_form_values(data)["rank_movement_duration"], value)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "project.json"
                draft = ProjectDraft.create(data, str(path))
                save_project_data(draft.project_data, path)
                self.assertEqual(load_project_file(path).chart_config.animation.rank_movement_duration, value)
            for mode in ("standard", "short", "standard"):
                config = apply_export_profile(loaded.chart_config, ExportConfig(mode=mode))
                self.assertEqual(config.animation.rank_movement_duration, value)
        for value in (.09, 1.01):
            with self.assertRaises(ProjectFileError):
                load_project_data({"animation": {"rank_movement_duration": value}})
