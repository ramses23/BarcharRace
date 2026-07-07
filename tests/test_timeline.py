import unittest

import pandas as pd

import _test_path
from config.dataset_config import DatasetConfig
from core.timeline import Timeline


class TimelineTest(unittest.TestCase):
    def test_applies_category_labels_and_colors_to_bar_data(self):
        dataframe = pd.DataFrame(
            {
                "year": [2000, 2000],
                "country": ["Coal", "Solar"],
                "value": [100, 50],
            }
        )
        timeline = Timeline(
            dataframe,
            config=DatasetConfig(
                category_labels={"Coal": "Carbon"},
                category_colors={"Coal": "#333333"},
            ),
        )

        bars = timeline.get_frame(2000)

        self.assertEqual(bars[0].name, "Carbon")
        self.assertEqual(bars[0].color, "#333333")
        self.assertEqual(bars[1].name, "Solar")
        self.assertIsNone(bars[1].color)


if __name__ == "__main__":
    unittest.main()
