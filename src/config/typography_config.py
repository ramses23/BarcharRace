from dataclasses import dataclass, replace


@dataclass(frozen=True)
class TypographyPreset:
    name: str = "studio"
    title_font_size: int = 34
    subtitle_font_size: int = 20
    time_label_font_size: int = 120
    source_font_size: int = 16
    label_font_size: int = 20
    value_font_size: int = 20
    title_font_weight: str = "bold"
    subtitle_font_weight: str = "normal"
    time_label_font_weight: str = "bold"
    source_font_weight: str = "normal"
    title_max_width: int = 1280
    subtitle_max_width: int = 1280
    source_max_width: int = 980

    def to_chart_updates(self):
        return {
            "title_font_size": self.title_font_size,
            "subtitle_font_size": self.subtitle_font_size,
            "time_label_font_size": self.time_label_font_size,
            "source_font_size": self.source_font_size,
            "label_font_size": self.label_font_size,
            "value_font_size": self.value_font_size,
            "title_font_weight": self.title_font_weight,
            "subtitle_font_weight": self.subtitle_font_weight,
            "time_label_font_weight": self.time_label_font_weight,
            "source_font_weight": self.source_font_weight,
            "title_max_width": self.title_max_width,
            "subtitle_max_width": self.subtitle_max_width,
            "source_max_width": self.source_max_width,
        }


TYPOGRAPHY_PRESETS = {
    "studio": TypographyPreset(),
    "editorial": TypographyPreset(
        name="editorial",
        title_font_size=40,
        subtitle_font_size=23,
        time_label_font_size=120,
        source_font_size=16,
        label_font_size=20,
        value_font_size=20,
        title_max_width=1240,
        subtitle_max_width=1040,
        source_max_width=860,
    ),
    "compact": TypographyPreset(
        name="compact",
        title_font_size=30,
        subtitle_font_size=18,
        time_label_font_size=104,
        source_font_size=14,
        label_font_size=18,
        value_font_size=18,
        title_max_width=1120,
        subtitle_max_width=900,
        source_max_width=760,
    ),
}


def get_typography_preset(name):
    try:
        return TYPOGRAPHY_PRESETS[name]
    except KeyError as exc:
        available = ", ".join(list_typography_presets())
        raise ValueError(
            f"Unknown typography preset '{name}'. "
            f"Available typography presets: {available}"
        ) from exc


def apply_typography_preset(chart_config, name):
    preset = get_typography_preset(name)

    return replace(
        chart_config,
        typography_preset=name,
        **preset.to_chart_updates(),
    )


def list_typography_presets():
    return tuple(sorted(TYPOGRAPHY_PRESETS))
