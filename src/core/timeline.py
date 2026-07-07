from config.dataset_config import DatasetConfig
from models.bar_data import BarData


class Timeline:

    def __init__(self, dataframe, config=None):
        self.config = config or DatasetConfig()
        self.df = dataframe
        self.years = sorted(int(y) for y in dataframe[self.config.year_column].unique())

    def get_years(self):
        return self.years

    def get_frame(self, year):
        frame = self.df[self.df[self.config.year_column] == year]
        frame = frame.sort_values(by=self.config.value_column, ascending=False)

        return [
            self._bar_data_from_row(row)
            for _, row in frame.iterrows()
        ]

    def _bar_data_from_row(self, row):
        raw_name = row[self.config.name_column]

        return BarData(
            name=self.config.display_name_for(raw_name),
            value=row[self.config.value_column],
            color=self.config.color_for(raw_name),
        )
