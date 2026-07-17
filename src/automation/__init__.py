"""Automation contracts for BarChartStudio."""

from automation.brief_loader import (
    ProductionBriefError,
    load_production_brief,
    validate_builder_id,
)
from automation.builder_parameters import (
    DatasetBuilderParameterParser,
    DatasetBuilderParametersError,
    NationalTeamGoalsBuildParameters,
    parse_national_team_goals_parameters,
)
from automation.models import (
    DatasetBrief,
    DatasetBuildResult,
    FrozenParameters,
    ProductionBrief,
)
from automation.registry import (
    DatasetBuilderDefinition,
    DatasetBuilderRegistry,
    DatasetBuilderRegistryError,
    UnknownDatasetBuilderError,
    create_default_dataset_builder_registry,
)
from automation.workspace import ProductionWorkspace, validate_job_id

__all__ = [
    "DatasetBrief",
    "DatasetBuilderDefinition",
    "DatasetBuilderParameterParser",
    "DatasetBuilderParametersError",
    "DatasetBuilderRegistry",
    "DatasetBuilderRegistryError",
    "DatasetBuildResult",
    "FrozenParameters",
    "NationalTeamGoalsBuildParameters",
    "ProductionBrief",
    "ProductionBriefError",
    "ProductionWorkspace",
    "UnknownDatasetBuilderError",
    "create_default_dataset_builder_registry",
    "load_production_brief",
    "parse_national_team_goals_parameters",
    "validate_builder_id",
    "validate_job_id",
]
