from dataclasses import dataclass, field


@dataclass(frozen=True)
class DatasetConfig:
    year_column: str = "year"
    name_column: str = "country"
    value_column: str = "value"
    category_labels: dict[str, str] = field(default_factory=dict)
    category_colors: dict[str, str] = field(default_factory=dict)
    category_logos: dict[str, str] = field(default_factory=dict)

    allow_negative_values: bool = False
    require_unique_names_per_year: bool = True

    @property
    def required_columns(self):
        return (
            self.year_column,
            self.name_column,
            self.value_column,
        )

    def display_name_for(self, raw_name):
        name = str(raw_name)
        label = self.category_labels.get(name)
        return label if isinstance(label, str) and label.strip() else name

    def color_for(self, raw_name):
        color = self.category_colors.get(str(raw_name))
        return color if isinstance(color, str) and color.strip() else None

    def logo_for(self, raw_name):
        logo = self.category_logos.get(str(raw_name))
        return logo if isinstance(logo, str) and logo.strip() else None
