from dataclasses import asdict, dataclass
from pathlib import Path

from core.logo_geometry import (
    final_visual_bar_sprite,
    normalized_primary_logo_position,
    primary_logo_is_inside,
    primary_logo_horizontal_bounds,
    resolved_bar_visual_sprite,
    resolved_primary_logo_size,
)
from core.bar_text_geometry import resolve_value_text_geometry
from core.display_calendar import flip_calendar_dimensions
from core.source_text_geometry import resolve_source_text_layout
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


@dataclass(frozen=True)
class SmartBarObstacle:
    rank: float | None
    opacity: float
    components: tuple[SceneRect, ...]


@dataclass(frozen=True)
class SmartFrameGeometry:
    bar_obstacles: tuple[SmartBarObstacle, ...]
    text_bounds: tuple[SceneRect, ...]


def build_scene_geometry(chart_config, fun_fact_config, scene):
    """Describe a rendered scene in final-canvas pixels for Studio editors."""
    sprites = tuple(scene.bars or ())
    primary_logo_available = tuple(
        _primary_logo_file_available(sprite)
        for sprite in sprites
    )
    visual_sprites = tuple(
        final_visual_bar_sprite(
            chart_config,
            sprite,
            primary_logo_available=available,
        )
        for sprite, available in zip(sprites, primary_logo_available)
    )
    logo_sprites = visual_sprites
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
        for sprite in visual_sprites
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

    source_layout = resolve_source_text_layout(
        chart_config,
        fun_fact_config,
        scene.source_label,
        time_label=scene.time_label,
        display_calendar=scene.display_calendar,
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
        "date": _date_rect(chart_config, scene),
        "source": _text_rect(
            source_layout.fitted_text,
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
        if scene.fun_fact is not None:
            resolved_x = getattr(scene.fun_fact, "resolved_x", None)
            resolved_y = getattr(scene.fun_fact, "resolved_y", None)
            if resolved_x is not None:
                left = resolved_x
            if resolved_y is not None:
                top = resolved_y
        editorial_rect = SceneRect(left, top, width, height)
        if fun_fact_config.editorial_layout_mode == "reserved":
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

    primary_logos, secondary_logos, logo_groups = _logo_rects(
        chart_config,
        logo_sprites,
    )
    value_text_geometries = []
    category_text_rects = []
    bar_obstacles = []
    for sprite, logo_group in zip(visual_sprites, logo_groups):
        value_geometry = None
        if (
            chart_config.value_labels_enabled
            and chart_config.value_text_opacity > 0
            and sprite.opacity > 0
        ):
            value_geometry = resolve_value_text_geometry(
                chart_config,
                sprite,
                format_value(sprite.value, chart_config.value_format),
                inside_left_logo_extent=_rect_extent(
                    logo_group["inside_left"]
                ),
                inside_right_logo_extent=_rect_extent(
                    logo_group["inside_right"]
                ),
            )
        value_rect = value_geometry.rect_dict() if value_geometry else None
        category_rect = (
            _category_text_rect(chart_config, sprite).to_dict()
            if (
                chart_config.category_labels_enabled
                and chart_config.label_text_opacity > 0
                and sprite.opacity > 0
            )
            else None
        )
        value_text_geometries.append(
            {
                "text": value_geometry.text,
                "x": round(float(value_geometry.x), 3),
                "y": round(float(value_geometry.y), 3),
                "ha": value_geometry.horizontal_alignment,
                "va": value_geometry.vertical_alignment,
                "rect": value_rect,
            }
            if value_geometry
            else None
        )
        category_text_rects.append(category_rect)
        bar_obstacles.append({
            "name": sprite.name,
            "rank": sprite.rank,
            "opacity": round(float(sprite.opacity), 6),
            "bar": SceneRect(
                sprite.x,
                sprite.y - (sprite.height / 2),
                max(0, sprite.width),
                sprite.height,
            ).to_dict(),
            "category_text": category_rect,
            "value_text": value_rect,
            "primary_logos": [
                rect.to_dict() for rect in logo_group["primary"]
            ],
            "secondary_logos": [
                rect.to_dict() for rect in logo_group["secondary"]
            ],
        })
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
        "category_text_rects": category_text_rects,
        "value_text_geometries": value_text_geometries,
        "bar_obstacles": bar_obstacles,
        "text_bounds": {
            name: rect.to_dict()
            for name, rect in text_bounds.items()
        },
        "source_layout": source_layout.to_dict(),
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


def build_smart_scene_geometry(
    chart_config,
    fun_fact_config,
    scene,
    *,
    logo_availability=None,
    text_bounds=None,
):
    """Build only the obstacles consumed by Smart Editorial Placement.

    Unlike ``build_scene_geometry`` this deliberately omits editor-only lanes,
    examples, axes, and serialized scene metadata.  Its output uses the same
    geometry helpers as the full path so placement scoring stays pixel-exact.
    """
    sprites = tuple(scene.bars or ())
    availability = tuple(
        _resolved_logo_availability(sprite, logo_availability)
        for sprite in sprites
    )
    visual_sprites = tuple(
        resolved_bar_visual_sprite(
            chart_config,
            sprite,
            primary_logo_available=available,
        )
        for sprite, available in zip(sprites, availability)
    )
    logo_sprites = visual_sprites
    _, _, logo_groups = _logo_rects(chart_config, logo_sprites)
    obstacles = []
    for sprite, logo_group in zip(visual_sprites, logo_groups):
        value_geometry = None
        if (
            chart_config.value_labels_enabled
            and chart_config.value_text_opacity > 0
            and sprite.opacity > 0
        ):
            value_geometry = resolve_value_text_geometry(
                chart_config,
                sprite,
                format_value(sprite.value, chart_config.value_format),
                inside_left_logo_extent=_rect_extent(
                    logo_group["inside_left"]
                ),
                inside_right_logo_extent=_rect_extent(
                    logo_group["inside_right"]
                ),
            )
        category_rect = (
            _rounded_scene_rect(_category_text_rect(chart_config, sprite))
            if (
                chart_config.category_labels_enabled
                and chart_config.label_text_opacity > 0
                and sprite.opacity > 0
            )
            else None
        )
        components = [_rounded_scene_rect(SceneRect(
                sprite.x,
                sprite.y - (sprite.height / 2),
                max(0, sprite.width),
                sprite.height,
            ))]
        if category_rect is not None:
            components.append(category_rect)
        if value_geometry is not None:
            components.append(_rounded_scene_rect(SceneRect(
                value_geometry.left,
                value_geometry.top,
                value_geometry.width,
                value_geometry.height,
            )))
        components.extend(
            _rounded_scene_rect(rect) for rect in logo_group["primary"]
        )
        components.extend(
            _rounded_scene_rect(rect) for rect in logo_group["secondary"]
        )
        obstacles.append(SmartBarObstacle(
            rank=sprite.rank,
            opacity=round(float(sprite.opacity), 6),
            components=tuple(components),
        ))
    if text_bounds is None:
        text_bounds = build_smart_text_bounds(
            chart_config, fun_fact_config, scene,
        )
    return SmartFrameGeometry(
        bar_obstacles=tuple(obstacles),
        text_bounds=tuple(text_bounds),
    )


def build_smart_text_bounds(chart_config, fun_fact_config, scene):
    """Resolve the small static/dynamic text obstacle set used by Smart."""
    source_layout = resolve_source_text_layout(
        chart_config,
        fun_fact_config,
        scene.source_label,
        time_label=scene.time_label,
        display_calendar=scene.display_calendar,
    )
    return (
        _rounded_scene_rect(_text_rect(
            scene.title,
            _title_x(chart_config),
            chart_config.title_y,
            chart_config.title_font_size,
            chart_config.title_font_family,
            chart_config.dpi,
            chart_config.title_font_weight,
            chart_config.title_font_style,
        )),
        _rounded_scene_rect(_text_rect(
            scene.subtitle,
            _subtitle_x(chart_config),
            chart_config.subtitle_y,
            chart_config.subtitle_font_size,
            chart_config.subtitle_font_family,
            chart_config.dpi,
            chart_config.subtitle_font_weight,
            chart_config.subtitle_font_style,
        )),
        _rounded_scene_rect(_date_rect(chart_config, scene)),
        _rounded_scene_rect(_text_rect(
            source_layout.fitted_text,
            chart_config.source_x,
            chart_config.source_y,
            chart_config.source_font_size,
            chart_config.source_font_family,
            chart_config.dpi,
            chart_config.source_font_weight,
            chart_config.source_font_style,
        )),
    )


def _rounded_scene_rect(rect):
    return SceneRect(
        round(float(rect.x), 3),
        round(float(rect.y), 3),
        max(0.0, round(float(rect.width), 3)),
        max(0.0, round(float(rect.height), 3)),
    )


def _resolved_logo_availability(sprite, availability):
    path = getattr(sprite, "logo_path", None)
    normalized = str(path) if path else path
    if availability is not None and normalized in availability:
        return availability[normalized]
    return _primary_logo_file_available(sprite)


def _date_rect(chart_config, scene):
    if (
        chart_config.date_style == "flip_calendar"
        and scene.display_calendar is not None
    ):
        width, height = flip_calendar_dimensions(
            chart_config.flip_calendar_scale
        )
        return SceneRect(
            chart_config.time_label_x - width,
            chart_config.time_label_y - (height / 2.0),
            width,
            height,
        )
    return _text_rect(
        scene.time_label,
        chart_config.time_label_x,
        chart_config.time_label_y,
        chart_config.time_label_font_size,
        chart_config.time_label_font_family,
        chart_config.dpi,
        chart_config.time_label_font_weight,
        chart_config.time_label_font_style,
        anchor="right",
    )


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
        "leader_occupancy": round(float(scale.leader_occupancy), 6),
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
        return (), (), tuple(_empty_logo_group() for _ in sprites)
    primary = []
    secondary = []
    groups = []
    for sprite in sprites:
        group = _empty_logo_group()
        primary_rect = None
        primary_position = normalized_primary_logo_position(
            config.bar_logo_position
        )
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
                group["primary"].append(primary_rect)
                group.setdefault(primary_position, []).append(primary_rect)
        if not config.bar_secondary_logo_enabled or not sprite.secondary_logo_path:
            groups.append(group)
            continue
        if config.bar_secondary_logo_layout == "badge" and primary_rect is not None:
            size = min(config.bar_secondary_logo_size, primary_rect.width)
            rect = SceneRect(
                primary_rect.right - size,
                primary_rect.bottom - size,
                size,
                size,
            )
            secondary.append(rect)
            group["secondary"].append(rect)
            group.setdefault(primary_position, []).append(rect)
            groups.append(group)
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
            group["secondary"].append(rect)
            normalized = normalized_primary_logo_position(position)
            group.setdefault(normalized, []).append(rect)
        groups.append(group)
    return tuple(primary), tuple(secondary), tuple(groups)


def _empty_logo_group():
    return {
        "primary": [],
        "secondary": [],
        "inside_left": [],
        "inside_right": [],
        "outside_left": [],
    }


def _rect_extent(rects):
    if not rects:
        return None
    return min(rect.x for rect in rects), max(rect.right for rect in rects)


def _category_text_rect(config, sprite):
    font_height = max(
        1.0,
        float(config.label_font_size) * float(config.dpi) / 72.0,
    )
    border = (
        max(0.0, float(config.bar_label_border_width))
        if config.bar_label_border_enabled
        else 0.0
    )
    shadow_x = (
        float(config.bar_label_shadow_offset_x)
        if config.bar_label_shadow_enabled
        else 0.0
    )
    shadow_y = (
        float(config.bar_label_shadow_offset_y)
        if config.bar_label_shadow_enabled
        else 0.0
    )
    left_padding = border + max(0.0, -shadow_x)
    right_padding = border + max(0.0, shadow_x)
    top_padding = border + max(0.0, -shadow_y)
    bottom_padding = border + max(0.0, shadow_y)
    position = {
        "left": "outside_left",
        "inside": "inside_left",
        "outside": "outside_right",
    }.get(config.bar_label_position, config.bar_label_position)
    if position == "outside_right":
        left = sprite.x + sprite.width
        right = config.width - config.value_label_edge_padding
    elif position in ("inside_left", "inside_center", "inside_right", "above"):
        left = sprite.x
        right = sprite.x + sprite.width
    else:
        left = config.label_min_x
        right = sprite.x
    center_y = sprite.y + config.bar_label_offset_y
    if position == "above":
        bottom = sprite.y - (sprite.height / 2) - 7 + config.bar_label_offset_y
        top = bottom - font_height
    else:
        top = center_y - (font_height / 2.0)
        bottom = center_y + (font_height / 2.0)
    return SceneRect(
        left - left_padding,
        top - top_padding,
        max(0.0, right - left) + left_padding + right_padding,
        max(1.0, bottom - top) + top_padding + bottom_padding,
    )


def _primary_logo_file_available(sprite):
    logo_path = getattr(sprite, "logo_path", None)
    if not logo_path:
        return False
    try:
        return Path(logo_path).is_file()
    except (OSError, TypeError, ValueError):
        return False


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
