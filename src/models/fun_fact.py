from dataclasses import dataclass


@dataclass(frozen=True)
class FunFact:
    id: str
    start: str
    end: str
    headline: str
    body: str = ""
    image_path: str | None = None
    layout: str = "right_panel"
    accent_color: str | None = None
    image_fit: str = "cover"
    credit: str = ""


@dataclass(frozen=True)
class FunFactCollection:
    version: int
    facts: tuple[FunFact, ...]
    source_path: str


@dataclass(frozen=True)
class ResolvedFunFact:
    fact: FunFact
    start_period: int
    end_period: int
    start_index: int
    end_index: int


@dataclass(frozen=True)
class ActiveFunFact:
    fact: FunFact
    opacity: float
    forced: bool = False
    resolved_x: int | None = None
    resolved_y: int | None = None
