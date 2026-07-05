from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeConfig:
    name: str = "studio_light"
    background_color: str = "#F7F7F4"
    text_color: str = "#222222"
    muted_text_color: str = "#666666"
    font_family: str = "DejaVu Sans"
    bar_palette: tuple[str, ...] = (
        "#4E79A7",
        "#F28E2B",
        "#E15759",
        "#76B7B2",
        "#59A14F",
        "#EDC948",
        "#B07AA1",
        "#FF9DA7",
        "#9C755F",
        "#BAB0AC",
    )


THEME_PRESETS = {
    "studio_light": ThemeConfig(),
    "clean_report": ThemeConfig(
        name="clean_report",
        background_color="#FFFFFF",
        text_color="#1F2933",
        muted_text_color="#6B7280",
        bar_palette=(
            "#2563EB",
            "#16A34A",
            "#DC2626",
            "#9333EA",
            "#EA580C",
            "#0891B2",
            "#CA8A04",
            "#DB2777",
            "#475569",
            "#65A30D",
        ),
    ),
    "midnight_contrast": ThemeConfig(
        name="midnight_contrast",
        background_color="#171717",
        text_color="#F5F5F5",
        muted_text_color="#A3A3A3",
        bar_palette=(
            "#60A5FA",
            "#F97316",
            "#34D399",
            "#F43F5E",
            "#A78BFA",
            "#FACC15",
            "#22D3EE",
            "#FB7185",
            "#C084FC",
            "#4ADE80",
        ),
    ),
}


def get_theme(name):
    try:
        return THEME_PRESETS[name]
    except KeyError as exc:
        available = ", ".join(list_themes())
        raise ValueError(f"Unknown theme '{name}'. Available themes: {available}") from exc


def list_themes():
    return tuple(sorted(THEME_PRESETS))
