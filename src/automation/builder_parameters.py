from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from automation.models import FrozenParameters


NATIONAL_TEAM_GOALS_BUILDER_ID = "national_team_goals"
NATIONAL_TEAM_GOALS_MODES = frozenset(("annual", "cumulative"))
NATIONAL_TEAM_GOALS_DUPLICATE_POLICIES = frozenset(("error", "warn", "allow"))

NationalTeamGoalsMode = Literal["annual", "cumulative"]
NationalTeamGoalsDuplicatePolicy = Literal["error", "warn", "allow"]

_EXPECTED_PARAMETER_KEYS = frozenset(
    ("start_year", "end_year", "mode", "duplicate_policy")
)


class DatasetBuilderParametersError(ValueError):
    """Raised when builder-specific parameters are invalid."""


class DatasetBuilderParameterParser(Protocol):
    """Contract for a pure builder-specific parameter parser."""

    def __call__(self, parameters: FrozenParameters) -> object: ...


@dataclass(frozen=True)
class NationalTeamGoalsBuildParameters:
    """Validated, immutable arguments specific to national-team goals builds."""

    start_year: int
    end_year: int
    mode: NationalTeamGoalsMode
    duplicate_policy: NationalTeamGoalsDuplicatePolicy

    def __post_init__(self) -> None:
        start_year = _parse_year("start_year", self.start_year)
        end_year = _parse_year("end_year", self.end_year)
        if start_year > end_year:
            raise DatasetBuilderParametersError(
                f"Builder {NATIONAL_TEAM_GOALS_BUILDER_ID!r} parameters "
                "'start_year' and 'end_year' must satisfy start_year <= end_year; "
                f"received start_year={start_year!r}, end_year={end_year!r}."
            )
        _parse_choice("mode", self.mode, NATIONAL_TEAM_GOALS_MODES)
        _parse_choice(
            "duplicate_policy",
            self.duplicate_policy,
            NATIONAL_TEAM_GOALS_DUPLICATE_POLICIES,
        )

    def to_build_kwargs(self) -> dict[str, int | str]:
        """Return a new dictionary containing only builder-specific arguments."""
        return {
            "start_year": self.start_year,
            "end_year": self.end_year,
            "mode": self.mode,
            "duplicate_policy": self.duplicate_policy,
        }


def parse_national_team_goals_parameters(
    parameters: FrozenParameters,
) -> NationalTeamGoalsBuildParameters:
    """Parse canonical brief parameters without I/O or builder execution."""
    if not isinstance(parameters, FrozenParameters):
        raise DatasetBuilderParametersError(
            f"Builder {NATIONAL_TEAM_GOALS_BUILDER_ID!r} parameters must be "
            "FrozenParameters; received type "
            f"{type(parameters).__name__!r}."
        )

    received_keys = frozenset(parameters)
    missing_keys = sorted(_EXPECTED_PARAMETER_KEYS - received_keys)
    unknown_keys = sorted(received_keys - _EXPECTED_PARAMETER_KEYS)
    if missing_keys or unknown_keys:
        details = []
        if missing_keys:
            details.append("Missing keys: " + ", ".join(missing_keys) + ".")
        if unknown_keys:
            details.append("Unknown keys: " + ", ".join(unknown_keys) + ".")
        raise DatasetBuilderParametersError(
            f"Builder {NATIONAL_TEAM_GOALS_BUILDER_ID!r} parameters are invalid. "
            + " ".join(details)
        )

    return NationalTeamGoalsBuildParameters(
        start_year=parameters["start_year"],
        end_year=parameters["end_year"],
        mode=parameters["mode"],
        duplicate_policy=parameters["duplicate_policy"],
    )


def _parse_year(field: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DatasetBuilderParametersError(
            f"Builder {NATIONAL_TEAM_GOALS_BUILDER_ID!r} parameter {field!r} "
            "must be a Python int and bool is not allowed; received "
            f"{value!r} ({type(value).__name__})."
        )
    return value


def _parse_choice(
    field: str,
    value: object,
    allowed: frozenset[str],
) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise DatasetBuilderParametersError(
            f"Builder {NATIONAL_TEAM_GOALS_BUILDER_ID!r} parameter {field!r} "
            f"must be exactly one of: {', '.join(sorted(allowed))}; received "
            f"{value!r} ({type(value).__name__})."
        )
    return value
