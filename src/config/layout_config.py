from dataclasses import dataclass, replace


@dataclass(frozen=True)
class LayoutPreset:
    name: str = "youtube_1080p"
    width: int = 1920
    height: int = 1080
    left_margin: int = 320
    right_margin: int = 220
    top_margin: int = 260
    bottom_margin: int = 140
    bar_height: int = 54
    bar_gap: int = 18
    title_y: int = 95
    subtitle_y: int = 165
    time_label_x: int = 1580
    time_label_y: int = 910
    source_x: int = 320
    source_y: int = 1005
    rank_label_gap: int = 320
    rank_label_min_x: int = 96
    rank_label_label_gap: int = 18
    label_min_x: int = 40
    value_label_edge_padding: int = 24

    def to_chart_updates(self):
        return {
            "width": self.width,
            "height": self.height,
            "left_margin": self.left_margin,
            "right_margin": self.right_margin,
            "top_margin": self.top_margin,
            "bottom_margin": self.bottom_margin,
            "bar_height": self.bar_height,
            "bar_gap": self.bar_gap,
            "title_y": self.title_y,
            "subtitle_y": self.subtitle_y,
            "time_label_x": self.time_label_x,
            "time_label_y": self.time_label_y,
            "source_x": self.source_x,
            "source_y": self.source_y,
            "rank_label_gap": self.rank_label_gap,
            "rank_label_min_x": self.rank_label_min_x,
            "rank_label_label_gap": self.rank_label_label_gap,
            "label_min_x": self.label_min_x,
            "value_label_edge_padding": self.value_label_edge_padding,
        }


LAYOUT_PRESETS = {
    "youtube_1080p": LayoutPreset(),
    "youtube_4k": LayoutPreset(
        name="youtube_4k",
        width=3840,
        height=2160,
        left_margin=640,
        right_margin=440,
        top_margin=520,
        bottom_margin=280,
        bar_height=108,
        bar_gap=36,
        title_y=190,
        subtitle_y=330,
        time_label_x=3160,
        time_label_y=1820,
        source_x=640,
        source_y=2010,
        rank_label_gap=640,
        rank_label_min_x=192,
        rank_label_label_gap=36,
        label_min_x=80,
        value_label_edge_padding=48,
    ),
    "square_social": LayoutPreset(
        name="square_social",
        width=1080,
        height=1080,
        left_margin=260,
        right_margin=120,
        top_margin=260,
        bottom_margin=160,
        bar_height=48,
        bar_gap=18,
        title_y=100,
        subtitle_y=155,
        time_label_x=930,
        time_label_y=910,
        source_x=260,
        source_y=1010,
        rank_label_gap=250,
        rank_label_min_x=84,
        rank_label_label_gap=16,
        label_min_x=36,
        value_label_edge_padding=20,
    ),
    "vertical_shorts": LayoutPreset(
        name="vertical_shorts",
        width=1080,
        height=1920,
        left_margin=260,
        right_margin=100,
        top_margin=420,
        bottom_margin=260,
        bar_height=56,
        bar_gap=22,
        title_y=160,
        subtitle_y=235,
        time_label_x=930,
        time_label_y=1660,
        source_x=260,
        source_y=1800,
        rank_label_gap=250,
        rank_label_min_x=84,
        rank_label_label_gap=16,
        label_min_x=36,
        value_label_edge_padding=20,
    ),
    "compact_dashboard": LayoutPreset(
        name="compact_dashboard",
        width=1280,
        height=720,
        left_margin=240,
        right_margin=140,
        top_margin=165,
        bottom_margin=90,
        bar_height=36,
        bar_gap=12,
        title_y=62,
        subtitle_y=106,
        time_label_x=1120,
        time_label_y=620,
        source_x=240,
        source_y=675,
        rank_label_gap=240,
        rank_label_min_x=72,
        rank_label_label_gap=14,
        label_min_x=30,
        value_label_edge_padding=18,
    ),
}


def get_layout_preset(name):
    try:
        return LAYOUT_PRESETS[name]
    except KeyError as exc:
        available = ", ".join(list_layout_presets())
        raise ValueError(
            f"Unknown layout preset '{name}'. Available layout presets: {available}"
        ) from exc


def apply_layout_preset(chart_config, name):
    preset = get_layout_preset(name)

    return replace(
        chart_config,
        layout_preset=name,
        **preset.to_chart_updates(),
    )


def list_layout_presets():
    return tuple(sorted(LAYOUT_PRESETS))
