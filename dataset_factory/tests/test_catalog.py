import unittest

import _test_path
from barchart_dataset_factory.catalog import get_dataset_idea, list_dataset_ideas


class CatalogTest(unittest.TestCase):
    def test_lists_dataset_ideas(self):
        keys = {idea.key for idea in list_dataset_ideas()}

        self.assertIn("fifa_mens_world_ranking", keys)
        self.assertIn("google_trends_football_players", keys)

    def test_classifies_subjective_popularity_as_not_recommended(self):
        idea = get_dataset_idea("subjective_player_popularity")

        self.assertEqual(idea.classification, "C")


if __name__ == "__main__":
    unittest.main()
