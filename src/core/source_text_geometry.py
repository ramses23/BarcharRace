from dataclasses import asdict, dataclass

from core.display_calendar import flip_calendar_dimensions
from studio.fun_fact_layout import editorial_geometry
from utils.text_fit import (
    fit_text_to_width,
    measure_text_width,
    measurement_font,
)


SOURCE_OBSTACLE_GAP = 12.0


@dataclass(frozen=True)
class SourceRect:
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

    def intersects_vertically(self, other):
        return self.bottom > other.y and self.y < other.bottom

    def to_dict(self):
        return {
            key: round(float(value), 3)
            for key, value in asdict(self).items()
        }


@dataclass(frozen=True)
class SourceObstacle:
    name: str
    rect: SourceRect
    gap: float
    intersects_source_band: bool
    limits_width: bool

    def to_dict(self):
        return {
            "name": self.name,
            "rect": self.rect.to_dict(),
            "gap": round(float(self.gap), 3),
            "intersects_source_band": self.intersects_source_band,
            "limits_width": self.limits_width,
        }


@dataclass(frozen=True)
class SourceTextLayout:
    full_text: str
    fitted_text: str
    full_text_width: float
    fitted_text_width: float
    source_band: SourceRect
    available_rect: SourceRect
    safe_right: float
    right_limit: float
    obstacles: tuple[SourceObstacle, ...]

    @property
    def available_width(self):
        return self.available_rect.width

    def to_dict(self):
        return {
            "full_text": self.full_text,
            "fitted_text": self.fitted_text,
            "full_text_width": round(float(self.full_text_width), 3),
            "fitted_text_width": round(float(self.fitted_text_width), 3),
            "source_band": self.source_band.to_dict(),
            "available_rect": self.available_rect.to_dict(),
            "safe_right": round(float(self.safe_right), 3),
            "right_limit": round(float(self.right_limit), 3),
            "available_width": round(float(self.available_width), 3),
            "obstacles": [obstacle.to_dict() for obstacle in self.obstacles],
        }


def resolve_source_text_layout(
    chart_config,
    fun_fact_config,
    source_text,
    *,
    time_label="",
    display_calendar=None,
    font=None,
):
    """Fit Source against only stable geometry crossing its visual band."""
    source_text = str(source_text or "")
    font = font or measurement_font(
        chart_config.source_font_size,
        chart_config.dpi,
        chart_config.source_font_family or chart_config.font_family,
        chart_config.source_font_weight,
        chart_config.source_font_style,
    )
    source_x = float(chart_config.source_x)
    source_band = _anchored_text_rect(
        source_text or "Ag",
        font,
        x=source_x,
        y=float(chart_config.source_y),
        horizontal_anchor="left",
    )
    source_band = SourceRect(
        source_band.x,
        source_band.y,
        0.0,
        source_band.height,
    )
    safe_right = max(
        0.0,
        float(chart_config.width)
        - max(0.0, float(chart_config.value_label_edge_padding)),
    )
    right_limit = max(source_x, safe_right)
    candidates = _source_obstacle_candidates(
        chart_config,
        fun_fact_config,
        time_label=time_label,
        display_calendar=display_calendar,
    )
    obstacles = []
    for name, rect, gap in candidates:
        intersects = source_band.intersects_vertically(rect)
        lies_to_right = rect.right > source_x
        candidate_right = max(source_x, rect.x - gap)
        limits = (
            intersects
            and lies_to_right
            and candidate_right < right_limit
        )
        if limits:
            right_limit = candidate_right
        obstacles.append(SourceObstacle(
            name=name,
            rect=rect,
            gap=gap,
            intersects_source_band=intersects,
            limits_width=limits,
        ))

    available_width = max(0.0, right_limit - source_x)
    fitted_text = fit_text_to_width(
        source_text,
        max_width=available_width,
        font=font,
    )
    full_width = measure_text_width(source_text, font)
    fitted_width = measure_text_width(fitted_text, font) if fitted_text else 0.0
    return SourceTextLayout(
        full_text=source_text,
        fitted_text=fitted_text,
        full_text_width=full_width,
        fitted_text_width=fitted_width,
        source_band=source_band,
        available_rect=SourceRect(
            source_x,
            source_band.y,
            available_width,
            source_band.height,
        ),
        safe_right=safe_right,
        right_limit=right_limit,
        obstacles=tuple(obstacles),
    )


def _source_obstacle_candidates(
    chart_config,
    fun_fact_config,
    *,
    time_label,
    display_calendar,
):
    candidates = []
    if chart_config.time_label_enabled:
        date_rect = _date_rect(
            chart_config,
            time_label=time_label,
            display_calendar=display_calendar,
        )
        if date_rect is not None:
            candidates.append(("date", date_rect, SOURCE_OBSTACLE_GAP))

    if fun_fact_config.enabled:
        left, top, width, height = editorial_geometry(
            chart_config,
            fun_fact_config,
        )
        candidates.append((
            "editorial",
            SourceRect(float(left), float(top), float(width), float(height)),
            float(fun_fact_config.editorial_collision_gap),
        ))
    return tuple(candidates)


def _date_rect(chart_config, *, time_label, display_calendar):
    if chart_config.date_style == "flip_calendar":
        if display_calendar is None:
            return None
        width, height = flip_calendar_dimensions(
            chart_config.flip_calendar_scale
        )
        return SourceRect(
            float(chart_config.time_label_x) - width,
            float(chart_config.time_label_y) - (height / 2.0),
            float(width),
            float(height),
        )
    if not time_label:
        return None
    font = measurement_font(
        chart_config.time_label_font_size,
        chart_config.dpi,
        chart_config.time_label_font_family or chart_config.font_family,
        chart_config.time_label_font_weight,
        chart_config.time_label_font_style,
    )
    return _anchored_text_rect(
        str(time_label),
        font,
        x=float(chart_config.time_label_x),
        y=float(chart_config.time_label_y),
        horizontal_anchor="right",
    )


def _anchored_text_rect(text, font, *, x, y, horizontal_anchor):
    anchor = "lm" if horizontal_anchor == "left" else "rm"
    left, top, right, bottom = font.getbbox(str(text), anchor=anchor)
    return SourceRect(
        float(x) + float(left),
        float(y) + float(top),
        max(0.0, float(right - left)),
        max(1.0, float(bottom - top)),
    )
