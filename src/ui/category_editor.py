from dataclasses import dataclass
from math import ceil


CATEGORY_FILTERS = (
    "All categories",
    "Customized",
    "Missing primary logo",
    "Missing second logo",
)
CATEGORY_PAGE_SIZES = (10, 20, 40)


@dataclass(frozen=True)
class CategoryPage:
    items: tuple[str, ...]
    page: int
    page_count: int
    page_size: int
    total: int
    start: int
    end: int


def filter_categories(categories, styles, query="", category_filter="All categories"):
    if category_filter not in CATEGORY_FILTERS:
        raise ValueError(f"Unknown category filter: {category_filter}")

    normalized_query = str(query).strip().casefold()
    matches = []

    for raw_name in categories:
        style = styles.get(raw_name, {})
        label = str(style.get("label", ""))

        searchable_text = f"{raw_name} {label}".casefold()
        if normalized_query and normalized_query not in searchable_text:
            continue

        if category_filter == "Customized" and not style:
            continue

        if category_filter == "Missing primary logo" and style.get("logo"):
            continue

        if category_filter == "Missing second logo" and style.get(
            "secondary_logo"
        ):
            continue

        matches.append(raw_name)

    return tuple(matches)


def paginate_categories(categories, page=1, page_size=10):
    if page_size <= 0:
        raise ValueError("page_size must be greater than zero")

    categories = tuple(categories)
    total = len(categories)
    page_count = max(1, ceil(total / page_size))
    page = min(max(int(page), 1), page_count)
    offset = (page - 1) * page_size
    items = categories[offset : offset + page_size]
    start = offset + 1 if items else 0
    end = offset + len(items)

    return CategoryPage(
        items=items,
        page=page,
        page_count=page_count,
        page_size=page_size,
        total=total,
        start=start,
        end=end,
    )


def update_category_style(
    styles,
    raw_name,
    *,
    label="",
    use_color=False,
    color="",
    logo="",
    secondary_logo="",
):
    updated_styles = {
        name: dict(style)
        for name, style in styles.items()
        if isinstance(style, dict)
    }
    next_style = dict(updated_styles.get(raw_name, {}))

    for field in ("label", "color", "logo", "secondary_logo"):
        next_style.pop(field, None)

    label = str(label).strip()
    color = str(color).strip()
    logo = str(logo).strip()
    secondary_logo = str(secondary_logo).strip()

    if label and label != raw_name:
        next_style["label"] = label

    if use_color and color:
        next_style["color"] = color

    if logo:
        next_style["logo"] = logo

    if secondary_logo:
        next_style["secondary_logo"] = secondary_logo

    if next_style:
        updated_styles[raw_name] = next_style
    else:
        updated_styles.pop(raw_name, None)

    return updated_styles
