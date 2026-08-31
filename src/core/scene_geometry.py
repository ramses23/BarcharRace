from dataclasses import asdict, dataclass

from core.logo_geometry import (
    primary_logo_horizontal_bounds,
    resolved_primary_logo_size,
)
from studio.fun_fact_layout import editorial_geometry
from utils.text_fit import measure_text_width, measurement_font
from utils.value_formatter import format_value


@dataclass(frozen=True)
class SceneRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    def to_dict(self):
        return {
            key: round(float(value), 3)
            for key, value in asdict(self).items()
        }


def build_scene_geometry(chart_config, fun_fact_config, scene):
    """Describe a rendered scene in final-canvas pixels for Studio editors."""
    sprites = tuple(scene.bars or ())
    canvas = SceneRect(0, 0, chart_config.width, chart_config.height)
    rows = tuple(
        SceneRect(
            0,
            sprite.y - (sprite.height / 2),
            chart_config.width,
            sprite.height,
        )
        for sprite in sprites
    )
    bars = tuple(
        SceneRect(
            sprite.x,
            sprite.y - (sprite.height / 2),
            max(0, sprite.width),
            sprite.height,
        )
        for sprite in sprites
    )
    row_top = min((rect.y for rect in rows), default=chart_config.top_margin)
    row_bottom = max(
        (rect.bottom for rect in rows),
        default=chart_config.height - chart_config.bottom_margin,
    )
    data_right = max(
        chart_config.left_margin,
        chart_config.width - chart_config.right_margin,
    )
    data_area = SceneRect(
        chart_config.left_margin,
        row_top,
        max(0, data_right - chart_config.left_margin),
        max(0, row_bottom - row_top),
    )
    rank_x = max(
        chart_config.rank_label_min_x,
        chart_config.left_margin - chart_config.rank_label_gap,
    )
    ranking_lane = SceneRect(
        rank_x,
        row_top,
        max(0, chart_config.label_min_x - rank_x),
        max(0, row_bottom - row_top),
    )
    category_lane = SceneRect(
        chart_config.label_min_x,
        row_top,
        max(0, chart_config.left_margin - chart_config.label_min_x),
        max(0, row_bottom - row_top),
    )
    longest_bar_right = max(
        (rect.right for rect in bars),
        default=chart_config.left_margin,
    )
    value_right = chart_config.width - chart_config.value_label_edge_padding
    value_lane = SceneRect(
        min(longest_bar_right, value_right),
        row_top,
        max(0, value_right - longest_bar_right),
        max(0, row_bottom - row_top),
    )

    text_bounds = {
        "title": _text_rect(
            scene.title,
            _title_x(chart_config),
            chart_config.title_y,
            chart_config.title_font_size,
            chart_config.title_font_family,
            chart_config.dpi,
            chart_config.title_font_weight,
            chart_config.title_font_style,
        ),
        "subtitle": _text_rect(
            scene.subtitle,
            _subtitle_x(chart_config),
            chart_config.subtitle_y,
            chart_config.subtitle_font_size,
            chart_config.subtitle_font_family,
            chart_config.dpi,
            chart_config.subtitle_font_weight,
            chart_config.subtitle_font_style,
        ),
        "date": _text_rect(
            scene.time_label,
            chart_config.time_label_x,
            chart_config.time_label_y,
            chart_config.time_label_font_size,
            chart_config.time_label_font_family,
            chart_config.dpi,
            chart_config.time_label_font_weight,
            chart_config.time_label_font_style,
            anchor="right",
        ),
        "source": _text_rect(
            scene.source_label,
            chart_config.source_x,
            chart_config.source_y,
            chart_config.source_font_size,
            chart_config.source_font_family,
            chart_config.dpi,
            chart_config.source_font_weight,
            chart_config.source_font_style,
        ),
    }
    editorial_rect = None
    collision_rect = None
    if fun_fact_config.enabled:
        left, top, width, height = editorial_geometry(
            chart_config,
            fun_fact_config,
        )
        editorial_rect = SceneRect(left, top, width, height)
        collision_left = max(
            0,
            left - max(0, fun_fact_config.editorial_collision_gap),
        )
        collision_rect = SceneRect(
            collision_left,
            top,
            width + left - collision_left,
            height,
        )

    primary_logos, secondary_logos = _logo_rects(chart_config, sprites)
    return {
        "canvas": canvas.to_dict(),
        "safe_area": SceneRect(
            chart_config.left_margin,
            0,
            max(0, chart_config.width - chart_config.left_margin - chart_config.right_margin),
            chart_config.height,
        ).to_dict(),
        "data_area": data_area.to_dict(),
        "row_rects": [rect.to_dict() for rect in rows],
        "bar_rects": [rect.to_dict() for rect in bars],
        "ranking_lane": ranking_lane.to_dict(),
        "category_lane": category_lane.to_dict(),
        "value_lane": value_lane.to_dict(),
        "value_axis": _value_axis_geometry(scene.value_axis),
        "bar_value_scale": _bar_value_scale_geometry(scene.bar_value_scale),
        "primary_logo_rects": [rect.to_dict() for rect in primary_logos],
        "secondary_logo_rects": [rect.to_dict() for rect in secondary_logos],
        "text_bounds": {
            name: rect.to_dict()
            for name, rect in text_bounds.items()
        },
        "editorial_rect": (
            editorial_rect.to_dict() if editorial_rect is not None else None
        ),
        "collision_rect": (
            collision_rect.to_dict() if collision_rect is not None else None
        ),
        "effective_positions": {
            "date": {
                "x": int(chart_config.time_label_x),
                "y": int(chart_config.time_label_y),
            },
        },
        "value_examples": [
            format_value(sprite.value, chart_config.value_format)
            for sprite in sprites
        ],
    }


def _value_axis_geometry(value_axis):
    if value_axis is None:
        return None
    return {
        "origin_x": round(float(value_axis.scale.origin_x), 3),
        "right_x": round(float(value_axis.scale.right_x), 3),
        "width": round(float(value_axis.scale.width), 3),
        "domain_max": round(float(value_axis.scale.domain_max), 6),
        "line_top": round(float(value_axis.line_top), 3),
        "line_bottom": round(float(value_axis.line_bottom), 3),
        "label_y": round(float(value_axis.label_y), 3),
        "ticks": [
            {
                "value": round(float(tick.value), 12),
                "x": round(float(tick.x), 3),
                "label": tick.label,
                "opacity": round(float(tick.opacity), 3),
            }
            for tick in value_axis.ticks
        ],
    }


def _bar_value_scale_geometry(scale):
    if scale is None:
        return None
    return {
        "origin_x": round(float(scale.origin_x), 3),
        "right_x": round(float(scale.right_x), 3),
        "width": round(float(scale.width), 3),
        "domain_max": round(float(scale.domain_max), 6),
        "timeline_progress": round(float(scale.timeline_progress), 6),
        "growth_envelope": round(float(scale.growth_envelope), 6),
    }


def _text_rect(
    text, x, y, point_size, family, dpi, weight="normal", style="normal",
    *, anchor="left",
):
    font = measurement_font(point_size, dpi, family, weight, style)
    width = measure_text_width(str(text or ""), font)
    height = max(1.0, float(point_size) * float(dpi) / 72.0)
    left = float(x) - width if anchor == "right" else float(x)
    return SceneRect(left, float(y) - (height / 2), width, height)


def _title_x(config):
    return config.left_margin if config.title_x is None else config.title_x


def _subtitle_x(config):
    return config.left_margin if config.subtitle_x is None else config.subtitle_x


def _logo_rects(config, sprites):
    if not config.logos_enabled:
        return (), ()
    primary = []
    secondary = []
    for sprite in sprites:
        primary_rect = None
        if sprite.logo_path:
            primary_size = resolved_primary_logo_size(
                config, sprite, config.logo_size
            )
            if primary_size > 0:
                primary_rect = _base_logo_rect(
                    sprite,
                    config.bar_logo_position,
                    primary_size,
                    0,
                    config.logo_gap,
                    minimum_size=primary_size,
                    canvas_width=config.width,
                    canvas_height=config.height,
                )
            if primary_rect is not None:
                primary.append(primary_rect)
        if not config.bar_secondary_logo_enabled or not sprite.secondary_logo_path:
            continue
        if config.bar_secondary_logo_layout == "badge" and primary_rect is not None:
            size = min(config.bar_secondary_logo_size, primary_rect.width)
            secondary.append(
                SceneRect(
                    primary_rect.right - size,
                    primary_rect.bottom - size,
                    size,
                    size,
                )
            )
            continue
        position = (
            config.bar_secondary_logo_position
            if config.bar_secondary_logo_layout == "independent"
            else config.bar_logo_position
        )
        rect = _base_logo_rect(
            sprite,
            position,
            config.bar_secondary_logo_size,
            config.bar_secondary_logo_padding,
            config.logo_gap,
        )
        if rect is not None:
            secondary.append(rect)
    return tuple(primary), tuple(secondary)


def _base_logo_rect(
    sprite, position, size, padding, gap, *, minimum_size=0, canvas_width=None,
    canvas_height=None,
):
    position = {"outside": "outside_left", "inside": "inside_left"}.get(
        position,
        position,
    )
    if position == "hidden":
        return None
    protected = minimum_size > 0
    size = max(1.0, float(size), float(minimum_size))
    if position == "outside_left":
        right = sprite.x - max(0.0, float(gap))
        left = right - size
    elif protected:
        left, _ = primary_logo_horizontal_bounds(
            sprite,
            position,
            size,
        )
    else:
        padding = max(0.0, float(padding))
        if not protected:
            size = min(size, max(0.0, sprite.height - (padding * 2)), max(0.0, sprite.width - (padding * 2)))
        if size <= 0:
            return None
        if position == "inside_right":
            left = sprite.x + sprite.width - padding - size
        else:
            left = sprite.x + padding
    if protected and canvas_width is not None and canvas_height is not None:
        size = min(size, float(canvas_width), float(canvas_height))
        left = min(float(canvas_width) - size, max(0.0, left))
        top = min(float(canvas_height) - size, max(0.0, sprite.y - (size / 2)))
        return SceneRect(left, top, size, size)
    return SceneRect(left, sprite.y - (size / 2), size, size)
