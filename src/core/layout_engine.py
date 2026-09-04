from config.chart_config import ChartConfig
from config.fun_fact_config import FunFactConfig
from core.bar_appearance import uses_configurable_bar_content
from models.bar_sprite import BarSprite
from utils.asset_resolver import AssetResolver
from utils.color_palette import ColorPalette
from utils.text_fit import measure_text_width, measurement_font
from utils.logo_color import representative_logo_color
from utils.value_formatter import format_value
from studio.fun_fact_layout import editorial_geometry


def structural_race_vertical_bounds(config):
    """Return the fixed vertical viewport occupied by the bar race."""
    if config.bar_vertical_layout_mode == "fill_available":
        top = max(0.0, float(config.bar_vertical_top_padding))
        bottom = float(config.height - max(0, config.bar_vertical_bottom_padding))
        if config.title_enabled:
            top = max(
                top,
                config.title_y + _text_half_height(config, config.title_font_size) + 12,
            )
        if config.subtitle_enabled:
            top = max(
                top,
                config.subtitle_y
                + _text_half_height(config, config.subtitle_font_size)
                + 12,
            )
        if _reserves_value_axis_lane(config):
            top = max(top, _value_axis_min_row_top(config))
        if config.source_label_enabled:
            bottom = min(
                bottom,
                config.source_y
                - _text_half_height(config, config.source_font_size)
                - 12,
            )
        return top, max(top, bottom)

    first_y = float(config.top_margin)
    if _reserves_value_axis_lane(config):
        first_y = max(
            first_y,
            _value_axis_min_row_top(config) + (config.bar_height / 2),
        )
    top = first_y - (config.bar_height / 2)
    bottom = float(config.height - config.bottom_margin)
    return top, max(top, bottom)


def _text_half_height(config, point_size):
    return max(1.0, float(point_size) * config.dpi / 144.0)


def _reserves_value_axis_lane(config):
    return config.value_grid_enabled and config.value_grid_tick_labels_enabled


def _value_axis_min_row_top(config):
    text_bottom = 0.0
    if config.title_enabled:
        text_bottom = max(
            text_bottom,
            config.title_y + _text_half_height(config, config.title_font_size),
        )
    if config.subtitle_enabled:
        text_bottom = max(
            text_bottom,
            config.subtitle_y + _text_half_height(config, config.subtitle_font_size),
        )
    tick_height = _text_half_height(config, config.value_grid_tick_font_size) * 2.0
    return text_bottom + tick_height + 18.0


class LayoutEngine:

    def __init__(self, config=None, fun_fact_config=None):
        self.config = config or ChartConfig()
        self.fun_fact_config = fun_fact_config or FunFactConfig()
        self.palette = ColorPalette(self.config.color_palette)
        self.logo_resolver = AssetResolver(
            self.config.logos_dir,
            self.config.logo_file_extensions,
        )

    def build(self, bars):

        if not bars:
            return []

        # ordenar SOLO para asignar ranking
        sorted_bars = sorted(bars, key=self._sort_key)
        visible_bars = self._visible_bars(sorted_bars)

        if not visible_bars:
            return []

        bar_height, bar_gap, first_y = self._vertical_geometry(len(visible_bars))
        row_centers = [
            first_y + i * (bar_height + bar_gap)
            for i in range(len(visible_bars))
        ]
        max_value = max(b.value for b in visible_bars)
        max_bar_width = self._max_bar_width(
            visible_bars,
            row_centers=row_centers,
            bar_height=bar_height,
            max_value=max_value,
        )

        sprites = []

        for i, bar in enumerate(visible_bars):

            y_position = row_centers[i]
            width = self._bar_width(bar.value, max_value, max_bar_width)
            logo_path = self._resolve_logo(bar)
            manual_color = bar.color or self.palette.get(bar.name)
            color = manual_color
            if self.config.bar_color_source == "primary_logo":
                color = representative_logo_color(logo_path) or manual_color

            sprites.append(
                BarSprite(
                    name=bar.name,
                    value=bar.value,
                    color=color,

                    x=self.config.left_margin,
                    y=y_position,
                    width=width,
                    height=bar_height,
                    rank=i + 1,
                    logo_path=logo_path,
                    secondary_logo_path=(
                        bar.secondary_logo_path
                        if self.config.logos_enabled
                        else None
                    ),
                    bar_available_width=max_bar_width,
                )
            )

        return sprites

    def _visible_bars(self, sorted_bars):
        nonzero_bars = [bar for bar in sorted_bars if bar.value != 0]
        limit = len(nonzero_bars)

        if self.config.max_visible_bars is not None:
            limit = min(limit, max(0, self.config.max_visible_bars))

        if (
            self.config.auto_fit_bar_count
            and self.config.bar_vertical_layout_mode != "fill_available"
        ):
            limit = min(limit, self.config.bar_capacity)

        return nonzero_bars[:limit]

    def _vertical_geometry(self, count):
        if self.config.bar_vertical_layout_mode != "fill_available" or count <= 0:
            first_y = self.config.top_margin
            if self._reserves_value_axis_lane():
                first_y = max(
                    first_y,
                    self._value_axis_min_row_top()
                    + (self.config.bar_height / 2),
                )
            return self.config.bar_height, self.config.bar_gap, first_y
        top, bottom_edge = structural_race_vertical_bounds(self.config)
        available = max(count, bottom_edge - top)
        if count == 1:
            height = min(self.config.bar_height, available)
            return height, 0, top + (available / 2)
        ratio = max(0.0, self.config.bar_gap / max(1, self.config.bar_height))
        height = max(1.0, available / (count + ratio * (count - 1)))
        gap = max(0.0, height * ratio)
        used = height * count + gap * (count - 1)
        return height, gap, top + ((available - used) / 2) + (height / 2)

    def _text_half_height(self, point_size):
        return _text_half_height(self.config, point_size)

    def _reserves_value_axis_lane(self):
        return _reserves_value_axis_lane(self.config)

    def _value_axis_min_row_top(self):
        return _value_axis_min_row_top(self.config)

    def _bar_width(self, value, max_value, max_bar_width):
        if max_value <= 0:
            return 0

        return (value / max_value) * max_bar_width

    def _max_bar_width(self, bars, *, row_centers=(), bar_height=0, max_value=None):
        max_bar_width = max(0.0, float(self.config.max_bar_width))

        required_lane = self._required_value_lane(bars)
        max_right = self.config.width - self.config.value_label_edge_padding
        configured_bar_right = self.config.left_margin + max_bar_width
        existing_lane = max(0.0, max_right - configured_bar_right)
        additional_lane = max(0.0, required_lane - existing_lane)
        max_bar_width = max(0.0, max_bar_width - additional_lane)

        if not self._uses_floating_editorial_obstacle() or not row_centers:
            return max_bar_width

        left, top, _, height = editorial_geometry(
            self.config,
            self.fun_fact_config,
        )
        obstacle_bottom = top + height
        obstacle_right_limit = left - self.fun_fact_config.editorial_collision_gap
        max_value = max_value if max_value is not None else max(bar.value for bar in bars)
        if max_value <= 0:
            return 0.0

        scale = max_bar_width / max_value
        for bar, center in zip(bars, row_centers):
            row_top = center - (bar_height / 2)
            row_bottom = center + (bar_height / 2)
            if row_bottom <= top or row_top >= obstacle_bottom or bar.value <= 0:
                continue
            available = max(
                0.0,
                obstacle_right_limit - self.config.left_margin - required_lane,
            )
            scale = min(scale, available / bar.value)
        return max(0.0, scale * max_value)

    def _required_value_lane(self, bars):
        if not self._reserves_outside_value_lane() and not (
            self._uses_floating_editorial_obstacle()
            and self.config.value_labels_enabled
            and uses_configurable_bar_content(self.config)
            and self.config.bar_value_position == "auto"
        ):
            return 0.0
        value_font = measurement_font(
            self.config.value_font_size,
            self.config.dpi,
            self.config.value_font_family or self.config.font_family,
            self.config.value_font_weight,
            self.config.value_font_style,
        )
        widest_value = max(
            measure_text_width(
                format_value(bar.value, value_format=self.config.value_format),
                value_font,
            )
            for bar in bars
        )
        transition_safety = max(2.0, float(value_font.size))
        return self.config.value_label_gap + widest_value + transition_safety

    def _uses_floating_editorial_obstacle(self):
        return (
            self.fun_fact_config.enabled
            and self.fun_fact_config.layout == "editorial_floating"
            and self.fun_fact_config.editorial_layout_mode == "reserved"
        )

    def _reserves_outside_value_lane(self):
        return (
            self.config.value_labels_enabled
            and uses_configurable_bar_content(self.config)
            and self.config.bar_value_position == "outside"
        )

    def _resolve_logo(self, bar):
        if not self.config.logos_enabled:
            return None

        return bar.logo_path or self.logo_resolver.resolve(bar.name)

    def _sort_key(self, bar):
        if (
            self.config.selection.aggregate_other
            and bar.name == self.config.selection.other_label
        ):
            return (1, 0)

        return (0, -bar.value)
