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
            BarData(
                name=row[self.config.name_column],
                value=row[self.config.value_column]
            )
            for _, row in frame.iterrows()
        ]
