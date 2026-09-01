import copy
import json
import re
import unicodedata
from dataclasses import dataclass, fields
from pathlib import Path

import pandas as pd

from config.chart_config import ChartConfig
from config.export_config import ExportConfig
from config.fun_fact_config import FunFactConfig
from config.layout_config import get_layout_preset
from config.project_schema import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    migrate_project_data,
)
from studio.project_storage import atomic_write_json


_DEFAULT_CHART_CONFIG = ChartConfig()
_DEFAULT_FUN_FACT_CONFIG = FunFactConfig()
_DEFAULT_EXPORT_CONFIG = ExportConfig()
BAR_STYLE_FIELDS = tuple(
    field.name
    for field in fields(ChartConfig)
    if field.name.startswith("bar_")
    and field.name not in (
        "bar_height", "bar_gap", "bar_vertical_layout_mode",
        "bar_vertical_top_padding", "bar_vertical_bottom_padding",
        "bar_color_source",
    )
) + ("logo_size",)


@dataclass(frozen=True)
class CsvInspection:
    path: str
    columns: tuple[str, ...]
    row_count: int
    numeric_columns: tuple[str, ...]
    year_candidates: tuple[str, ...]
    name_candidates: tuple[str, ...]
    value_candidates: tuple[str, ...]


def inspect_csv(csv_path):
    path = Path(csv_path)
    dataframe = pd.read_csv(path)
    return inspect_dataframe(dataframe, path=path)


def inspect_dataframe(dataframe, path=""):
    columns = tuple(str(column) for column in dataframe.columns)
    numeric_columns = tuple(
        column
        for column in columns
        if pd.api.types.is_numeric_dtype(dataframe[column])
    )

    return CsvInspection(
        path=str(path),
        columns=columns,
        row_count=len(dataframe),
        numeric_columns=numeric_columns,
        year_candidates=_matching_columns(columns, ("year", "date", "period")),
        name_candidates=_matching_columns(
            columns,
            ("name", "country", "source", "category", "entity"),
        ),
        value_candidates=_value_candidates(columns, numeric_columns),
    )


def category_values(csv_path, name_column, limit=80):
    dataframe = pd.read_csv(csv_path, usecols=[name_column])
    return category_values_from_dataframe(dataframe, name_column, limit=limit)


def category_values_from_dataframe(dataframe, name_column, limit=80):
    if name_column not in dataframe.columns:
        raise ValueError(f"Column not found: {name_column}")

    values = (
        dataframe[name_column]
        .dropna()
        .astype(str)
        .str.strip()
    )
    values = sorted(value for value in values.unique() if value)

    if limit is None:
        return tuple(values)

    return tuple(values[:limit])


def year_values(csv_path, year_column):
    dataframe = pd.read_csv(csv_path, usecols=[year_column])
    return year_values_from_dataframe(dataframe, year_column)


def year_values_from_dataframe(dataframe, year_column):
    if year_column not in dataframe.columns:
        raise ValueError(f"Column not found: {year_column}")

    years = pd.to_numeric(dataframe[year_column], errors="coerce").dropna()
    years = sorted({int(year) for year in years if float(year).is_integer()})

    return tuple(years)


def match_category_logos(category_names, logo_paths):
    exact_logos = {}
    normalized_logos = {}

    for logo_path in sorted((str(path) for path in logo_paths), key=str.casefold):
        stem = _path_stem(logo_path)
        exact_key = stem.strip().casefold()
        normalized_key = logo_match_key(stem)

        if exact_key:
            exact_logos.setdefault(exact_key, logo_path)

        if normalized_key:
            normalized_logos.setdefault(normalized_key, logo_path)

    matches = {}

    for category_name in category_names:
        category_name = str(category_name)
        exact_key = category_name.strip().casefold()
        normalized_key = logo_match_key(category_name)
        logo_path = exact_logos.get(exact_key) or normalized_logos.get(normalized_key)

        if logo_path:
            matches[category_name] = logo_path

    return matches


def apply_category_logo_matches(
    category_styles,
    matched_logos,
    *,
    logo_field="logo",
):
    styles = copy.deepcopy(category_styles) if isinstance(category_styles, dict) else {}

    if logo_field not in ("logo", "secondary_logo"):
        raise ValueError("logo_field must be 'logo' or 'secondary_logo'.")

    for raw_name, logo_path in matched_logos.items():
        if not raw_name or not logo_path:
            continue

        styles.setdefault(raw_name, {})[logo_field] = logo_path

    return styles


def logo_match_key(value):
    normalized = unicodedata.normalize("NFKD", str(value))
    without_accents = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    key = re.sub(r"[^a-z0-9]+", "_", without_accents.casefold())

    return key.strip("_")


def build_project_data(
    *,
    name,
    csv_path,
    year_column,
    name_column,
    value_column,
    title,
    source_label,
    output_file,
    frames_dir,
    layout_preset,
    theme,
    background_mode="color",
    background_color_override=None,
    background_image_path=None,
    background_image_fit="cover",
    background_motion="off",
    background_motion_speed=1.0,
    background_motion_intensity=0.35,
    value_grid_enabled=False,
    value_grid_mode="dynamic",
    value_grid_tick_labels_enabled=True,
    value_grid_tick_value_format="same",
    value_grid_line_color="#FFFFFF",
    value_grid_line_opacity=0.18,
    value_grid_line_thickness=1.0,
    value_grid_tick_text_color=None,
    value_grid_tick_text_opacity=0.72,
    value_grid_tick_font_size=16,
    value_grid_tick_font_weight="normal",
    value_grid_tick_font_style="normal",
    value_grid_target_tick_count=5,
    typography_preset,
    value_format,
    fps,
    steps_per_transition,
    top_n,
    max_visible_bars,
    bar_vertical_layout_mode="manual",
    bar_vertical_top_padding=24,
    bar_vertical_bottom_padding=24,
    bar_gap=None,
    bar_color_source="manual",
    primary_logo_min_size=0,
    start_bars_at_zero=False,
    leader_full_width_point=1.0,
    png_compress_level=1,
    frame_output_mode="ffmpeg_stream",
    bar_shape=None,
    bar_gradient_enabled=None,
    bar_gradient_lighten=None,
    bar_border_enabled=None,
    bar_border_color=None,
    bar_border_width=None,
    bar_shadow_enabled=None,
    bar_shadow_color=None,
    bar_shadow_alpha=None,
    bar_shadow_offset_x=None,
    bar_shadow_offset_y=None,
    bar_style=None,
    title_font_family=None,
    subtitle_font_family=None,
    label_font_family=None,
    value_font_family=None,
    time_label_font_family=None,
    source_font_family=None,
    rank_label_font_family=None,
    title_text_color=None,
    title_text_opacity=None,
    subtitle_text_color=None,
    subtitle_text_opacity=None,
    label_text_color=None,
    label_text_opacity=None,
    value_text_color=None,
    value_text_opacity=None,
    time_label_text_color=None,
    time_label_opacity=None,
    date_style="standard",
    flip_calendar_scale=1.0,
    flip_calendar_card_background="#20252B",
    flip_calendar_card_opacity=1.0,
    flip_calendar_text_color="#F5F4EF",
    flip_calendar_border_color="#4B5159",
    flip_calendar_shadow_opacity=0.32,
    flip_calendar_corner_radius=12.0,
    flip_calendar_flip_duration_frames=4,
    source_text_color=None,
    source_text_opacity=None,
    rank_label_text_color=None,
    rank_label_text_opacity=None,
    title_font_size=None,
    subtitle_font_size=None,
    label_font_size=None,
    value_font_size=None,
    time_label_font_size=None,
    source_font_size=None,
    rank_label_font_size=None,
    text_styles=None,
    title_enabled=None,
    subtitle_enabled=None,
    time_label_enabled=None,
    source_label_enabled=None,
    rank_labels_enabled=None,
    category_labels_enabled=None,
    value_labels_enabled=None,
    title_x=None,
    title_y=None,
    subtitle_x=None,
    subtitle_y=None,
    time_label_x=None,
    time_label_y=None,
    source_x=None,
    source_y=None,
    label_min_x=None,
    left_margin=None,
    rank_label_gap=None,
    motion_mode=None,
    rank_movement_duration=1.0,
    aggregate_other=False,
    category_styles=None,
    fun_facts=None,
    export_settings=None,
    time_label_column=None,
    base_project_data=None,
):
    project_data = (
        migrate_project_data(base_project_data).data
        if base_project_data
        else {"schema_version": CURRENT_PROJECT_SCHEMA_VERSION}
    )
    project_data["schema_version"] = CURRENT_PROJECT_SCHEMA_VERSION
    project_data["name"] = name

    chart = project_data.setdefault("chart", {})
    data_source = project_data.setdefault("data_source", {})
    dataset = project_data.setdefault("dataset", {})
    selection = project_data.setdefault("selection", {})

    if not base_project_data:
        chart.update(
            {
                "title_enabled": True,
                "subtitle_enabled": True,
                "time_label_enabled": True,
                "date_style": "standard",
                "source_label_enabled": True,
                "rank_labels_enabled": True,
                "category_labels_enabled": True,
                "value_labels_enabled": True,
                "rank_label_prefix": "#",
                "label_min_x": 40,
                "value_label_gap": 16,
                "value_label_min_x": None,
                "auto_fit_bar_count": True,
                "bar_shape": "rectangle",
                "bar_border_enabled": False,
                "bar_border_color": "#FFFFFF",
                "bar_border_width": 1.5,
                "bar_shadow_enabled": True,
                "bar_shadow_color": "#000000",
                "bar_shadow_alpha": 0.12,
                "bar_shadow_offset_x": 5,
                "bar_shadow_offset_y": 4,
                "bar_gradient_enabled": True,
                "bar_gradient_lighten": 0.22,
            }
        )
        chart.update({
            field: getattr(_DEFAULT_CHART_CONFIG, field)
            for field in BAR_STYLE_FIELDS
        })
        project_data["animation"] = {
            "easing": "ease_out_cubic",
            "enter_exit": True,
            "value_smoothing": True,
            "motion_mode": "transition_easing",
            "rank_movement_duration": 1.0,
        }
        selection.update(
            {
                "other_label": "Other",
                "other_color": "#A0A0A0",
            }
        )

    chart.update(
        {
            "title": title,
            "output_file": output_file,
            "frames_dir": frames_dir,
            "layout_preset": layout_preset,
            "theme": theme,
            "background_mode": background_mode,
            "background_color_override": background_color_override,
            "background_image_path": background_image_path,
            "background_image_fit": background_image_fit,
            "background_motion": background_motion,
            "background_motion_speed": background_motion_speed,
            "background_motion_intensity": background_motion_intensity,
            "value_grid_enabled": value_grid_enabled,
            "value_grid_mode": value_grid_mode,
            "value_grid_tick_labels_enabled": (
                value_grid_tick_labels_enabled
            ),
            "value_grid_tick_value_format": value_grid_tick_value_format,
            "value_grid_line_color": value_grid_line_color,
            "value_grid_line_opacity": value_grid_line_opacity,
            "value_grid_line_thickness": value_grid_line_thickness,
            "value_grid_tick_text_color": value_grid_tick_text_color,
            "value_grid_tick_text_opacity": value_grid_tick_text_opacity,
            "value_grid_tick_font_size": value_grid_tick_font_size,
            "value_grid_tick_font_weight": value_grid_tick_font_weight,
            "value_grid_tick_font_style": value_grid_tick_font_style,
            "value_grid_target_tick_count": value_grid_target_tick_count,
            "value_format": value_format,
            "typography_preset": typography_preset,
            "title_font_family": title_font_family,
            "subtitle_font_family": subtitle_font_family,
            "label_font_family": label_font_family,
            "value_font_family": value_font_family,
            "time_label_font_family": time_label_font_family,
            "date_style": date_style,
            "flip_calendar_scale": float(flip_calendar_scale),
            "flip_calendar_card_background": (
                flip_calendar_card_background
            ),
            "flip_calendar_card_opacity": float(
                flip_calendar_card_opacity
            ),
            "flip_calendar_text_color": flip_calendar_text_color,
            "flip_calendar_border_color": flip_calendar_border_color,
            "flip_calendar_shadow_opacity": float(
                flip_calendar_shadow_opacity
            ),
            "flip_calendar_corner_radius": float(
                flip_calendar_corner_radius
            ),
            "flip_calendar_flip_duration_frames": int(
                flip_calendar_flip_duration_frames
            ),
            "source_font_family": source_font_family,
            "rank_label_font_family": rank_label_font_family,
            "fps": fps,
            "steps_per_transition": steps_per_transition,
            "max_visible_bars": max_visible_bars,
            "bar_vertical_layout_mode": bar_vertical_layout_mode,
            "bar_vertical_top_padding": bar_vertical_top_padding,
            "bar_vertical_bottom_padding": bar_vertical_bottom_padding,
            "bar_color_source": bar_color_source,
            "primary_logo_min_size": primary_logo_min_size,
            "start_bars_at_zero": bool(start_bars_at_zero),
            "leader_full_width_point": float(leader_full_width_point),
            "frame_output_mode": frame_output_mode,
            "png_compress_level": _bounded_int_or_default(
                png_compress_level,
                default=1,
                minimum=0,
                maximum=9,
            ),
        }
    )
    chart.update({
        key: value
        for key, value in {
            "bar_shape": bar_shape,
            "bar_gradient_enabled": bar_gradient_enabled,
            "bar_gradient_lighten": bar_gradient_lighten,
            "bar_border_enabled": bar_border_enabled,
            "bar_border_color": bar_border_color,
            "bar_border_width": bar_border_width,
            "bar_shadow_enabled": bar_shadow_enabled,
            "bar_shadow_color": bar_shadow_color,
            "bar_shadow_alpha": bar_shadow_alpha,
            "bar_shadow_offset_x": bar_shadow_offset_x,
            "bar_shadow_offset_y": bar_shadow_offset_y,
            "title_text_color": title_text_color,
            "title_text_opacity": title_text_opacity,
            "subtitle_text_color": subtitle_text_color,
            "subtitle_text_opacity": subtitle_text_opacity,
            "label_text_color": label_text_color,
            "label_text_opacity": label_text_opacity,
            "value_text_color": value_text_color,
            "value_text_opacity": value_text_opacity,
            "time_label_text_color": time_label_text_color,
            "time_label_opacity": time_label_opacity,
            "source_text_color": source_text_color,
            "source_text_opacity": source_text_opacity,
            "rank_label_text_color": rank_label_text_color,
            "rank_label_text_opacity": rank_label_text_opacity,
            "title_font_size": title_font_size,
            "subtitle_font_size": subtitle_font_size,
            "label_font_size": label_font_size,
            "value_font_size": value_font_size,
            "time_label_font_size": time_label_font_size,
            "source_font_size": source_font_size,
            "rank_label_font_size": rank_label_font_size,
            "title_enabled": title_enabled,
            "subtitle_enabled": subtitle_enabled,
            "time_label_enabled": time_label_enabled,
            "source_label_enabled": source_label_enabled,
            "rank_labels_enabled": rank_labels_enabled,
            "category_labels_enabled": category_labels_enabled,
            "value_labels_enabled": value_labels_enabled,
            "title_x": title_x,
            "title_y": title_y,
            "subtitle_x": subtitle_x,
            "subtitle_y": subtitle_y,
            "time_label_x": time_label_x,
            "time_label_y": time_label_y,
            "source_x": source_x,
            "source_y": source_y,
            "label_min_x": label_min_x,
            "left_margin": left_margin,
            "rank_label_gap": rank_label_gap,
        }.items()
        if value is not None
    })

    if isinstance(bar_style, dict):
        chart.update({
            key: value
            for key, value in bar_style.items()
            if key in BAR_STYLE_FIELDS
        })
    if isinstance(text_styles, dict):
        chart.update({
            key: value
            for key, value in text_styles.items()
            if key in {field.name for field in fields(ChartConfig)}
            and (key.endswith("_font_weight") or key.endswith("_font_style"))
        })
    if bar_gap is not None:
        chart["bar_gap"] = int(bar_gap)
    animation = project_data.setdefault("animation", {})

    if motion_mode is not None:
        animation["motion_mode"] = motion_mode
    animation["rank_movement_duration"] = float(rank_movement_duration)
    selection.update(
        {
            "top_n": top_n,
            "aggregate_other": aggregate_other,
        }
    )
    data_source.update(
        {
            "source_type": "csv",
            "csv_path": csv_path,
            "source_label_override": source_label,
        }
    )
    dataset.update(
        {
            "year_column": year_column,
            "name_column": name_column,
            "value_column": value_column,
        }
    )
    if time_label_column is not None:
        dataset["time_label_column"] = time_label_column

    if category_styles is not None:
        category_styles = clean_category_styles(category_styles)

        if category_styles:
            project_data["categories"] = category_styles
        else:
            project_data.pop("categories", None)

    if fun_facts is not None:
        cleaned_fun_facts = {
            key: value
            for key, value in fun_facts.items()
            if value is not None
        }
        has_existing = isinstance(project_data.get("fun_facts"), dict)
        has_configuration = bool(cleaned_fun_facts or has_existing)
        if has_configuration:
            project_data["fun_facts"] = cleaned_fun_facts
        else:
            project_data.pop("fun_facts", None)

    if export_settings is not None:
        project_data["export"] = {
            field.name: export_settings.get(
                field.name,
                getattr(_DEFAULT_EXPORT_CONFIG, field.name),
            )
            for field in fields(ExportConfig)
        }

    return project_data


def save_project_data(
    project_data,
    project_path,
    *,
    app_root=None,
    workspace_root=None,
):
    migration = migrate_project_data(project_data)
    return atomic_write_json(
        migration.data,
        project_path,
        app_root=app_root,
        workspace_root=workspace_root,
        operation="Project save",
    )


def load_project_data(project_path):
    path = Path(project_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return migrate_project_data(data).data


def project_form_values(project_data=None):
    project_data = project_data or {}
    chart = _section(project_data, "chart")
    data_source = _section(project_data, "data_source")
    dataset = _section(project_data, "dataset")
    selection = _section(project_data, "selection")
    animation = _section(project_data, "animation")
    fun_facts = _section(project_data, "fun_facts")
    export = _section(project_data, "export")

    title = chart.get("title", "Electricity by Source")
    project_name = project_data.get("name") or project_name_from_title(title)
    paths = default_project_paths(project_name)
    layout_preset = chart.get("layout_preset", "youtube_1080p")

    try:
        layout_settings = get_layout_preset(layout_preset)
    except ValueError:
        layout_settings = _DEFAULT_CHART_CONFIG

    return {
        "name": project_name,
        "title": title,
        "csv_path": data_source.get(
            "csv_path",
            "data/datasets/global_electricity_sources.csv",
        ),
        "source_label": data_source.get(
            "source_label_override",
            "Source: User-provided dataset",
        ),
        "year_column": dataset.get("year_column", "year"),
        "name_column": dataset.get("name_column", "country"),
        "value_column": dataset.get("value_column", "value"),
        "time_label_column": dataset.get("time_label_column"),
        "layout_preset": layout_preset,
        "theme": chart.get("theme", "clean_report"),
        "background_mode": chart.get("background_mode", "color"),
        "background_color_override": chart.get("background_color_override"),
        "background_image_path": chart.get("background_image_path"),
        "background_image_fit": chart.get("background_image_fit", "cover"),
        "background_motion": chart.get("background_motion", "off"),
        "background_motion_speed": chart.get("background_motion_speed", 1.0),
        "background_motion_intensity": chart.get("background_motion_intensity", 0.35),
        "value_grid_enabled": chart.get("value_grid_enabled", False),
        "value_grid_mode": chart.get("value_grid_mode", "dynamic"),
        "value_grid_tick_labels_enabled": chart.get(
            "value_grid_tick_labels_enabled", True
        ),
        "value_grid_tick_value_format": chart.get(
            "value_grid_tick_value_format", "same"
        ),
        "value_grid_line_color": chart.get(
            "value_grid_line_color", "#FFFFFF"
        ),
        "value_grid_line_opacity": chart.get(
            "value_grid_line_opacity", 0.18
        ),
        "value_grid_line_thickness": chart.get(
            "value_grid_line_thickness", 1.0
        ),
        "value_grid_tick_text_color": chart.get(
            "value_grid_tick_text_color"
        ),
        "value_grid_tick_text_opacity": chart.get(
            "value_grid_tick_text_opacity", 0.72
        ),
        "value_grid_tick_font_size": chart.get(
            "value_grid_tick_font_size", 16
        ),
        "value_grid_tick_font_weight": chart.get(
            "value_grid_tick_font_weight", "normal"
        ),
        "value_grid_tick_font_style": chart.get(
            "value_grid_tick_font_style", "normal"
        ),
        "value_grid_target_tick_count": chart.get(
            "value_grid_target_tick_count", 5
        ),
        "typography_preset": chart.get("typography_preset", "editorial"),
        "title_font_family": chart.get("title_font_family"),
        "subtitle_font_family": chart.get("subtitle_font_family"),
        "label_font_family": chart.get("label_font_family"),
        "value_font_family": chart.get("value_font_family"),
        "time_label_font_family": chart.get("time_label_font_family"),
        "source_font_family": chart.get("source_font_family"),
        "rank_label_font_family": chart.get("rank_label_font_family"),
        **{
            field: chart.get(field, getattr(_DEFAULT_CHART_CONFIG, field))
            for field in (
                "title_font_weight", "title_font_style",
                "subtitle_font_weight", "subtitle_font_style",
                "time_label_font_weight", "time_label_font_style",
                "source_font_weight", "source_font_style",
                "label_font_weight", "label_font_style",
                "value_font_weight", "value_font_style",
                "rank_label_font_weight", "rank_label_font_style",
            )
        },
        "title_text_color": chart.get("title_text_color"),
        "title_text_opacity": chart.get("title_text_opacity", 1.0),
        "subtitle_text_color": chart.get("subtitle_text_color"),
        "subtitle_text_opacity": chart.get("subtitle_text_opacity", 1.0),
        "label_text_color": chart.get("label_text_color"),
        "label_text_opacity": chart.get("label_text_opacity", 1.0),
        "value_text_color": chart.get("value_text_color"),
        "value_text_opacity": chart.get("value_text_opacity", 1.0),
        "time_label_text_color": chart.get("time_label_text_color"),
        "time_label_opacity": chart.get("time_label_opacity", 0.22),
        "date_style": chart.get("date_style", "standard"),
        "flip_calendar_scale": chart.get("flip_calendar_scale", 1.0),
        "flip_calendar_card_background": chart.get(
            "flip_calendar_card_background", "#20252B"
        ),
        "flip_calendar_card_opacity": chart.get(
            "flip_calendar_card_opacity", 1.0
        ),
        "flip_calendar_text_color": chart.get(
            "flip_calendar_text_color", "#F5F4EF"
        ),
        "flip_calendar_border_color": chart.get(
            "flip_calendar_border_color", "#4B5159"
        ),
        "flip_calendar_shadow_opacity": chart.get(
            "flip_calendar_shadow_opacity", 0.32
        ),
        "flip_calendar_corner_radius": chart.get(
            "flip_calendar_corner_radius", 12.0
        ),
        "flip_calendar_flip_duration_frames": chart.get(
            "flip_calendar_flip_duration_frames", 4
        ),
        "source_text_color": chart.get("source_text_color"),
        "source_text_opacity": chart.get("source_text_opacity", 1.0),
        "rank_label_text_color": chart.get("rank_label_text_color"),
        "rank_label_text_opacity": chart.get("rank_label_text_opacity", 1.0),
        "title_font_size": chart.get("title_font_size"),
        "subtitle_font_size": chart.get("subtitle_font_size"),
        "label_font_size": chart.get("label_font_size"),
        "value_font_size": chart.get("value_font_size"),
        "time_label_font_size": chart.get("time_label_font_size"),
        "source_font_size": chart.get("source_font_size"),
        "rank_label_font_size": chart.get("rank_label_font_size"),
        "title_enabled": chart.get("title_enabled", True),
        "subtitle_enabled": chart.get("subtitle_enabled", True),
        "time_label_enabled": chart.get("time_label_enabled", True),
        "source_label_enabled": chart.get("source_label_enabled", True),
        "rank_labels_enabled": chart.get("rank_labels_enabled", True),
        "category_labels_enabled": chart.get("category_labels_enabled", True),
        "value_labels_enabled": chart.get("value_labels_enabled", True),
        "title_x": chart.get("title_x"),
        "title_y": chart.get("title_y"),
        "subtitle_x": chart.get("subtitle_x"),
        "subtitle_y": chart.get("subtitle_y"),
        "time_label_x": chart.get("time_label_x"),
        "time_label_y": chart.get("time_label_y"),
        "source_x": chart.get("source_x"),
        "source_y": chart.get("source_y"),
        "label_min_x": chart.get("label_min_x", layout_settings.label_min_x),
        "left_margin": chart.get("left_margin", layout_settings.left_margin),
        "right_margin": chart.get("right_margin", layout_settings.right_margin),
        "rank_label_gap": chart.get(
            "rank_label_gap",
            layout_settings.rank_label_gap,
        ),
        "rank_label_min_x": chart.get(
            "rank_label_min_x",
            layout_settings.rank_label_min_x,
        ),
        "rank_label_label_gap": chart.get(
            "rank_label_label_gap",
            layout_settings.rank_label_label_gap,
        ),
        "value_format": chart.get("value_format", "decimal"),
        "dpi": chart.get("dpi", 150),
        "fps": chart.get("fps", 24),
        "steps_per_transition": chart.get("steps_per_transition", 24),
        "top_n": selection.get("top_n", 8),
        "max_visible_bars": chart.get("max_visible_bars", 8),
        "bar_vertical_layout_mode": chart.get("bar_vertical_layout_mode", "manual"),
        "bar_vertical_top_padding": chart.get("bar_vertical_top_padding", 24),
        "bar_vertical_bottom_padding": chart.get("bar_vertical_bottom_padding", 24),
        "bar_gap": chart.get("bar_gap", layout_settings.bar_gap),
        "bar_color_source": chart.get("bar_color_source", "manual"),
        "primary_logo_min_size": chart.get("primary_logo_min_size", 0),
        "start_bars_at_zero": chart.get("start_bars_at_zero", False),
        "leader_full_width_point": chart.get(
            "leader_full_width_point", 1.0
        ),
        "png_compress_level": chart.get("png_compress_level", 1),
        "frame_output_mode": chart.get("frame_output_mode", "ffmpeg_stream"),
        **{
            field: chart.get(field, getattr(_DEFAULT_CHART_CONFIG, field))
            for field in BAR_STYLE_FIELDS
        },
        "motion_mode": animation.get("motion_mode", "transition_easing"),
        "rank_movement_duration": animation.get(
            "rank_movement_duration", 1.0
        ),
        "aggregate_other": selection.get("aggregate_other", False),
        "output_file": chart.get("output_file", paths["output_file"]),
        "frames_dir": chart.get("frames_dir", paths["frames_dir"]),
        "project_file": paths["project_file"],
        "categories": clean_category_styles(project_data.get("categories", {})),
        "fun_facts_enabled": fun_facts.get("enabled", False),
        "fun_facts_source": fun_facts.get("source"),
        "fun_facts_layout": fun_facts.get("layout", "right_panel"),
        "fun_facts_panel_width": fun_facts.get("panel_width"),
        "fun_facts_panel_margin": fun_facts.get("panel_margin", 32),
        "fun_facts_panel_padding": fun_facts.get("panel_padding", 28),
        "fun_facts_fade_in": fun_facts.get("fade_in", 0.20),
        "fun_facts_fade_out": fun_facts.get("fade_out", 0.20),
        **{
            field.name: export.get(
                field.name,
                getattr(_DEFAULT_EXPORT_CONFIG, field.name),
            )
            for field in fields(ExportConfig)
        },
        **{
            f"fun_facts_{field}": fun_facts.get(field, getattr(_DEFAULT_FUN_FACT_CONFIG, field))
            for field in (
                "editorial_background_mode", "editorial_background_color",
                "editorial_background_texture",
                "editorial_background_texture_intensity",
                "editorial_headline_size", "editorial_headline_font_weight",
                "editorial_headline_font_style", "editorial_body_size",
                "editorial_body_font_weight", "editorial_body_font_style",
                "editorial_credit_size", "editorial_credit_font_weight",
                "editorial_credit_font_style",
                "editorial_headline_color", "editorial_headline_opacity",
                "editorial_body_color", "editorial_body_opacity",
                "editorial_credit_color", "editorial_credit_opacity",
                "editorial_image_area_ratio", "editorial_image_fit",
                "editorial_text_image_gap", "editorial_top_offset",
                "editorial_reposition_time_label",
                "editorial_orientation", "editorial_card_x",
                "editorial_card_y", "editorial_card_width",
                "editorial_card_height", "editorial_image_position",
                "editorial_collision_gap",
            )
        },
    }


def project_defaults_from_csv_path(csv_path):
    title = project_title_from_csv_path(csv_path)
    name = project_name_from_title(_path_stem(csv_path))
    paths = default_project_paths(name)

    return {
        "name": name,
        "title": title,
        "project_file": paths["project_file"],
        "output_file": paths["output_file"],
        "frames_dir": paths["frames_dir"],
    }


def project_title_from_csv_path(csv_path):
    words = re.split(r"[_\-\s]+", _path_stem(csv_path).strip())
    title = " ".join(_title_word(word) for word in words if word)

    return title or "Bar Chart Project"


def project_name_from_title(title):
    slug = re.sub(r"[^a-z0-9]+", "_", str(title).lower())
    slug = slug.strip("_")
    return slug or "bar_chart_project"


def default_project_paths(project_name):
    return {
        "project_file": "project.json",
        "output_file": f"output/races/{project_name}.mp4",
        "frames_dir": f"output/frames/{project_name}",
    }


def preferred_column(candidates, fallback_columns, default=None):
    if candidates:
        return candidates[0]

    if default in fallback_columns:
        return default

    if fallback_columns:
        return fallback_columns[0]

    return ""


def clean_category_styles(category_styles):
    if not isinstance(category_styles, dict):
        return {}

    cleaned = {}

    for raw_name, style in category_styles.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue

        if not isinstance(style, dict):
            continue

        cleaned_style = {}
        label = style.get("label")
        color = style.get("color")
        logo = style.get("logo")
        secondary_logo = style.get("secondary_logo")

        if isinstance(label, str):
            label = label.strip()

            if label and label != raw_name:
                cleaned_style["label"] = label

        if isinstance(color, str) and color.strip():
            cleaned_style["color"] = color.strip()

        if isinstance(logo, str) and logo.strip():
            cleaned_style["logo"] = logo.strip()

        if isinstance(secondary_logo, str) and secondary_logo.strip():
            cleaned_style["secondary_logo"] = secondary_logo.strip()

        if cleaned_style:
            cleaned[raw_name] = cleaned_style

    return cleaned


def _bounded_int_or_default(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return min(maximum, max(minimum, parsed))


def _path_stem(path):
    normalized_path = str(path).replace("\\", "/")
    return Path(normalized_path).stem


def _title_word(word):
    if word.isupper() and len(word) > 1:
        return word

    return word.capitalize()


def _section(project_data, name):
    section = project_data.get(name, {})
    return section if isinstance(section, dict) else {}


def _matching_columns(columns, names):
    normalized_names = set(names)
    matches = []

    for column in columns:
        normalized = str(column).strip().lower()

        if normalized in normalized_names:
            matches.append(column)

    return tuple(matches)


def _value_candidates(columns, numeric_columns):
    preferred = _matching_columns(
        columns,
        ("value", "amount", "generation", "generation_twh", "score"),
    )

    if preferred:
        return preferred

    return tuple(
        column
        for column in numeric_columns
        if str(column).strip().lower() not in {"year", "date", "period"}
    )
