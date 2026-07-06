import unittest

import _test_path
from config.bar_selection_config import BarSelectionConfig
from core.bar_selector import BarSelector
from models.bar_data import BarData


class BarSelectorTest(unittest.TestCase):
    def test_returns_sorted_bars_when_top_n_is_not_configured(self):
        bars = [
            BarData(name="B", value=20),
            BarData(name="A", value=30),
            BarData(name="C", value=10),
        ]

        result = BarSelector().select(bars)

        self.assertEqual([bar.name for bar in result], ["A", "B", "C"])

    def test_limits_to_top_n_bars(self):
        bars = [
            BarData(name="A", value=30),
            BarData(name="B", value=20),
            BarData(name="C", value=10),
        ]

        result = BarSelector(BarSelectionConfig(top_n=2)).select(bars)

        self.assertEqual([bar.name for bar in result], ["A", "B"])

    def test_aggregates_hidden_bars_as_other(self):
        bars = [
            BarData(name="A", value=30),
            BarData(name="B", value=20),
            BarData(name="C", value=10),
            BarData(name="D", value=5),
        ]

        result = BarSelector(
            BarSelectionConfig(
                top_n=2,
                aggregate_other=True,
                other_label="Rest",
                other_color="#999999",
            )
        ).select(bars)

        self.assertEqual([bar.name for bar in result], ["A", "B", "Rest"])
        self.assertEqual(result[-1].value, 15)
        self.assertEqual(result[-1].color, "#999999")

    def test_does_not_add_other_when_no_bars_are_hidden(self):
        bars = [
            BarData(name="A", value=30),
            BarData(name="B", value=20),
        ]

        result = BarSelector(
            BarSelectionConfig(top_n=2, aggregate_other=True)
        ).select(bars)

        self.assertEqual([bar.name for bar in result], ["A", "B"])

    def test_rejects_invalid_top_n(self):
        with self.assertRaises(ValueError):
            BarSelector(BarSelectionConfig(top_n=0)).select(
                [
                    BarData(name="A", value=30),
                ]
            )


if __name__ == "__main__":
    unittest.main()
