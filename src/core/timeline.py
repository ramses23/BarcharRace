from config.dataset_config import DatasetConfig
from models.bar_data import BarData


class Timeline:

    def __init__(self, dataframe, config=None):
        self.config = config or DatasetConfig()
        self.df = dataframe
        self.years = sorted(int(y) for y in dataframe[self.config.year_column].unique())
        self._time_labels = self._build_time_labels(dataframe)
        self._period_indexes = {
            period: index for index, period in enumerate(self.years)
        }
        self._periods_by_label = self._build_periods_by_label()

    def get_years(self):
        return self.years

    def get_frame(self, year):
        frame = self.df[self.df[self.config.year_column] == year]
        frame = frame.sort_values(by=self.config.value_column, ascending=False)

        return [
            self._bar_data_from_row(row)
            for _, row in frame.iterrows()
        ]

    def get_time_label(self, period):
        # Return the display label nearest to a numeric timeline position.
        try:
            numeric_period = float(period)
        except (TypeError, ValueError):
            return str(period)

        if not self._time_labels:
            return f"{numeric_period:.0f}"

        nearest_period = min(
            self.years,
            key=lambda candidate: abs(candidate - numeric_period),
        )
        return self._time_labels.get(nearest_period, str(nearest_period))

    def resolve_time_label(self, label):
        normalized = str(label).strip()
        if normalized not in self._periods_by_label:
            raise ValueError(f"Timeline label not found: {normalized!r}.")
        return self._periods_by_label[normalized]

    def get_period_index(self, period):
        try:
            return self._period_indexes[int(period)]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Timeline period not found: {period!r}.") from exc

    def get_timeline_position(self, period_a, *, period_b=None, progress=0.0):
        start = float(self.get_period_index(period_a))
        if period_b is None:
            return start
        end = float(self.get_period_index(period_b))
        try:
            progress = float(progress)
        except (TypeError, ValueError):
            progress = 0.0
        progress = max(0.0, min(1.0, progress))
        return start + ((end - start) * progress)

    def get_period_labels(self):
        return tuple((period, self.get_time_label(period)) for period in self.years)

    def _build_periods_by_label(self):
        periods = {}
        for period in self.years:
            label = self._time_labels.get(period, str(period))
            if label in periods:
                raise ValueError(
                    f"Timeline label {label!r} is shared by periods "
                    f"{periods[label]!r} and {period!r}."
                )
            periods[label] = period
        return periods

    def _build_time_labels(self, dataframe):
        label_column = self.config.time_label_column

        if not label_column:
            return {}

        if label_column not in dataframe.columns:
            raise ValueError(
                f"Configured time label column '{label_column}' was not found."
            )

        labels = {}
        for raw_period, frame in dataframe.groupby(self.config.year_column):
            values = {
                str(value).strip()
                for value in frame[label_column].dropna().tolist()
                if str(value).strip()
            }
            if len(values) > 1:
                raise ValueError(
                    f"Time period {raw_period!r} has multiple labels in "
                    f"column '{label_column}': {sorted(values)}"
                )
            if values:
                labels[int(raw_period)] = next(iter(values))

        return labels

    def _bar_data_from_row(self, row):
        raw_name = row[self.config.name_column]

        return BarData(
            name=self.config.display_name_for(raw_name),
            value=row[self.config.value_column],
            color=self.config.color_for(raw_name),
            logo_path=self.config.logo_for(raw_name),
            secondary_logo_path=self.config.secondary_logo_for(raw_name),
        )
