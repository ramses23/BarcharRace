import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


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
    typography_preset,
    value_format,
    fps,
    steps_per_transition,
    top_n,
    max_visible_bars,
    aggregate_other=False,
):
    return {
        "name": name,
        "chart": {
            "title": title,
            "output_file": output_file,
            "frames_dir": frames_dir,
            "layout_preset": layout_preset,
            "theme": theme,
            "value_format": value_format,
            "typography_preset": typography_preset,
            "fps": fps,
            "steps_per_transition": steps_per_transition,
            "rank_labels_enabled": True,
            "rank_label_prefix": "#",
            "label_min_x": 40,
            "value_label_gap": 16,
            "value_label_min_x": None,
            "auto_fit_bar_count": True,
            "max_visible_bars": max_visible_bars,
            "bar_shadow_enabled": True,
            "bar_shadow_alpha": 0.12,
            "bar_shadow_offset_x": 5,
            "bar_shadow_offset_y": 4,
            "bar_gradient_enabled": True,
            "bar_gradient_lighten": 0.22,
        },
        "animation": {
            "easing": "ease_out_cubic",
            "enter_exit": True,
            "value_smoothing": True,
        },
        "selection": {
            "top_n": top_n,
            "aggregate_other": aggregate_other,
            "other_label": "Other",
            "other_color": "#A0A0A0",
        },
        "data_source": {
            "source_type": "csv",
            "csv_path": csv_path,
            "source_label_override": source_label,
        },
        "dataset": {
            "year_column": year_column,
            "name_column": name_column,
            "value_column": value_column,
        },
    }


def save_project_data(project_data, project_path):
    path = Path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(project_data, indent=2) + "\n",
        encoding="utf-8",
    )

    return path


def project_name_from_title(title):
    slug = re.sub(r"[^a-z0-9]+", "_", str(title).lower())
    slug = slug.strip("_")
    return slug or "bar_chart_project"


def default_project_paths(project_name):
    return {
        "project_file": f"projects/{project_name}.json",
        "output_file": f"output/{project_name}.mp4",
        "frames_dir": f"output/{project_name}_frames",
    }


def preferred_column(candidates, fallback_columns, default=None):
    if candidates:
        return candidates[0]

    if default in fallback_columns:
        return default

    if fallback_columns:
        return fallback_columns[0]

    return ""


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
