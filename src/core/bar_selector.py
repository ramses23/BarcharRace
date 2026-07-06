from config.bar_selection_config import BarSelectionConfig
from models.bar_data import BarData


class BarSelector:
    def __init__(self, config=None):
        self.config = config or BarSelectionConfig()

    def select(self, bars):
        sorted_bars = sorted(bars, key=lambda bar: bar.value, reverse=True)

        if self.config.top_n is None:
            return sorted_bars

        if self.config.top_n < 1:
            raise ValueError("BarSelectionConfig.top_n must be at least 1.")

        if len(sorted_bars) <= self.config.top_n:
            return sorted_bars

        selected = sorted_bars[: self.config.top_n]
        hidden = sorted_bars[self.config.top_n :]

        if not self.config.aggregate_other:
            return selected

        return selected + [
            BarData(
                name=self.config.other_label,
                value=sum(bar.value for bar in hidden),
                color=self.config.other_color,
            )
        ]
