from dataclasses import dataclass


@dataclass(frozen=True)
class ExportConfig:
    mode: str = "standard"
    short_width: int = 1080
    short_height: int = 1920
    short_from_period: int | None = None
    short_to_period: int | None = None
    short_intro_enabled: bool = True
    short_intro_text: str = "WATCH CHINA CLIMB"
    short_intro_duration: float = 2.0
    short_context_enabled: bool = True
    short_context_title: str = "World’s Largest Economies"
    short_context_subtitle: str = "2001 → 2005"
    short_outro_enabled: bool = True
    short_outro_text: str = "Watch the full 1970–2026 ranking →"
    short_outro_duration: float = 2.0
    short_include_fun_facts: bool = False

    @property
    def is_short(self):
        return self.mode == "short"
