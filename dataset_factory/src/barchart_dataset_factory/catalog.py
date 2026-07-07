from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetIdea:
    key: str
    title: str
    classification: str
    metric: str
    likely_source: str
    notes: str


DATASET_IDEAS = {
    "fifa_mens_world_ranking": DatasetIdea(
        key="fifa_mens_world_ranking",
        title="FIFA Men's World Ranking Race",
        classification="B",
        metric="FIFA ranking points by team and ranking date/year",
        likely_source="FIFA official rankings or a documented historical export",
        notes=(
            "Strong first football dataset, but it requires extraction or a "
            "verifiable historical CSV before production."
        ),
    ),
    "world_bank_population": DatasetIdea(
        key="world_bank_population",
        title="Countries by Population",
        classification="A",
        metric="Total population by country and year",
        likely_source="World Bank indicator SP.POP.TOTL",
        notes="Good production candidate because the metric and source are stable.",
    ),
    "world_bank_gdp_current_usd": DatasetIdea(
        key="world_bank_gdp_current_usd",
        title="Countries by GDP",
        classification="A",
        metric="GDP current US dollars by country and year",
        likely_source="World Bank indicator NY.GDP.MKTP.CD",
        notes="Good production candidate with a clear source and metric.",
    ),
    "google_trends_football_players": DatasetIdea(
        key="google_trends_football_players",
        title="Most Searched Football Players on Google",
        classification="B",
        metric="Google Trends search interest index",
        likely_source="Google Trends",
        notes=(
            "Do not call this popularity. Values are normalized search interest "
            "indexes and require careful anchor methodology."
        ),
    ),
    "football_players_career_goals": DatasetIdea(
        key="football_players_career_goals",
        title="Football Players by Career Goals",
        classification="B",
        metric="Official goals by player and year",
        likely_source="Official competition records or vetted football datasets",
        notes="Defensible if the goal source and competition scope are explicit.",
    ),
    "football_players_market_value": DatasetIdea(
        key="football_players_market_value",
        title="Football Players by Market Value",
        classification="B",
        metric="Market value by player and date/year",
        likely_source="Transfermarkt or licensed/exported market-value dataset",
        notes="Attractive visually, but source permissions must be checked.",
    ),
    "subjective_player_popularity": DatasetIdea(
        key="subjective_player_popularity",
        title="Most Popular Football Players",
        classification="C",
        metric="Undefined popularity",
        likely_source="None",
        notes="Not recommended unless converted into a verifiable metric.",
    ),
}


def list_dataset_ideas():
    return tuple(DATASET_IDEAS[key] for key in sorted(DATASET_IDEAS))


def get_dataset_idea(key):
    try:
        return DATASET_IDEAS[key]
    except KeyError as exc:
        available = ", ".join(sorted(DATASET_IDEAS))
        raise ValueError(f"Unknown dataset idea '{key}'. Available: {available}") from exc
