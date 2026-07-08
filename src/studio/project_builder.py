import copy
import json
import re
import unicodedata
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


def category_values(csv_path, name_column, limit=80):
    dataframe = pd.read_csv(csv_path, usecols=[name_column])
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


def apply_category_logo_matches(category_styles, matched_logos):
    styles = copy.deepcopy(category_styles) if isinstance(category_styles, dict) else {}

    for raw_name, logo_path in matched_logos.items():
        if not raw_name or not logo_path:
            continue

        styles.setdefault(raw_name, {})["logo"] = logo_path

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
    typography_preset,
    value_format,
    fps,
    steps_per_transition,
    top_n,
    max_visible_bars,
    png_compress_level=1,
    aggregate_other=False,
    category_styles=None,
    base_project_data=None,
):
    project_data = copy.deepcopy(base_project_data) if base_project_data else {}
    project_data["name"] = name

    chart = project_data.setdefault("chart", {})
    data_source = project_data.setdefault("data_source", {})
    dataset = project_data.setdefault("dataset", {})
    selection = project_data.setdefault("selection", {})

    if not base_project_data:
        chart.update(
            {
                "rank_labels_enabled": True,
                "rank_label_prefix": "#",
                "label_min_x": 40,
                "value_label_gap": 16,
                "value_label_min_x": None,
                "auto_fit_bar_count": True,
                "bar_shadow_enabled": True,
                "bar_shadow_alpha": 0.12,
                "bar_shadow_offset_x": 5,
                "bar_shadow_offset_y": 4,
                "bar_gradient_enabled": True,
                "bar_gradient_lighten": 0.22,
            }
        )
        project_data["animation"] = {
            "easing": "ease_out_cubic",
            "enter_exit": True,
            "value_smoothing": True,
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
            "value_format": value_format,
            "typography_preset": typography_preset,
            "fps": fps,
            "steps_per_transition": steps_per_transition,
            "max_visible_bars": max_visible_bars,
            "png_compress_level": _bounded_int_or_default(
                png_compress_level,
                default=1,
                minimum=0,
                maximum=9,
            ),
        }
    )
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

    if category_styles is not None:
        category_styles = clean_category_styles(category_styles)

        if category_styles:
            project_data["categories"] = category_styles
        else:
            project_data.pop("categories", None)

    return project_data


def save_project_data(project_data, project_path):
    path = Path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(project_data, indent=2) + "\n",
        encoding="utf-8",
    )

    return path


def load_project_data(project_path):
    path = Path(project_path)
    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Project JSON must contain an object.")

    return data


def project_form_values(project_data=None):
    project_data = project_data or {}
    chart = _section(project_data, "chart")
    data_source = _section(project_data, "data_source")
    dataset = _section(project_data, "dataset")
    selection = _section(project_data, "selection")

    title = chart.get("title", "Electricity by Source")
    project_name = project_data.get("name") or project_name_from_title(title)
    paths = default_project_paths(project_name)

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
        "layout_preset": chart.get("layout_preset", "youtube_1080p"),
        "theme": chart.get("theme", "clean_report"),
        "typography_preset": chart.get("typography_preset", "editorial"),
        "value_format": chart.get("value_format", "decimal"),
        "fps": chart.get("fps", 24),
        "steps_per_transition": chart.get("steps_per_transition", 24),
        "top_n": selection.get("top_n", 8),
        "max_visible_bars": chart.get("max_visible_bars", 8),
        "png_compress_level": chart.get("png_compress_level", 1),
        "aggregate_other": selection.get("aggregate_other", False),
        "output_file": chart.get("output_file", paths["output_file"]),
        "frames_dir": chart.get("frames_dir", paths["frames_dir"]),
        "project_file": paths["project_file"],
        "categories": clean_category_styles(project_data.get("categories", {})),
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

        if isinstance(label, str):
            label = label.strip()

            if label and label != raw_name:
                cleaned_style["label"] = label

        if isinstance(color, str) and color.strip():
            cleaned_style["color"] = color.strip()

        if isinstance(logo, str) and logo.strip():
            cleaned_style["logo"] = logo.strip()

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
