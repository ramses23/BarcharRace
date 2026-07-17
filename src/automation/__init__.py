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
from automation.logo_resolver import (
    LOGO_RESOLUTION_MANIFEST_SCHEMA_VERSION,
    SUPPORTED_LOGO_EXTENSIONS,
    LocalLogoResolver,
    LogoAsset,
    LogoResolutionError,
    LogoResolutionResult,
)
from automation.models import (
    DatasetBrief,
    DatasetBuildResult,
    FrozenParameters,
    ProductionBrief,
)
from automation.orchestrator import (
    DATASET_BUILD_MANIFEST_SCHEMA_VERSION,
    DatasetBuildParameterArguments,
    DatasetProductionResult,
    ProductionOrchestrationError,
    ProductionOrchestrator,
)
from automation.project_assembler import (
    PROJECT_ASSEMBLY_MANIFEST_SCHEMA_VERSION,
    ProductionProjectAssembler,
    ProjectAssemblyError,
    ProjectAssemblyOptions,
    ProjectAssemblyResult,
)
from automation.production_preflight import (
    PRODUCTION_PREFLIGHT_MANIFEST_SCHEMA_VERSION,
    ProductionPreflightError,
    ProductionPreflightIssue,
    ProductionPreflightResult,
    ProductionPreflightRunner,
)
from automation.render_executor import (
    PRODUCTION_RENDER_MANIFEST_SCHEMA_VERSION,
    ProductionRenderError,
    ProductionRenderExecutor,
    ProductionRenderProgress,
    ProductionRenderResult,
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
    "DatasetBuildParameterArguments",
    "DatasetProductionResult",
    "DATASET_BUILD_MANIFEST_SCHEMA_VERSION",
    "FrozenParameters",
    "LOGO_RESOLUTION_MANIFEST_SCHEMA_VERSION",
    "LocalLogoResolver",
    "LogoAsset",
    "LogoResolutionError",
    "LogoResolutionResult",
    "NationalTeamGoalsBuildParameters",
    "ProductionBrief",
    "ProductionBriefError",
    "ProductionOrchestrationError",
    "ProductionOrchestrator",
    "ProductionPreflightError",
    "ProductionPreflightIssue",
    "ProductionPreflightResult",
    "ProductionPreflightRunner",
    "ProductionRenderError",
    "ProductionRenderExecutor",
    "ProductionRenderProgress",
    "ProductionRenderResult",
    "ProductionProjectAssembler",
    "ProductionWorkspace",
    "PROJECT_ASSEMBLY_MANIFEST_SCHEMA_VERSION",
    "PRODUCTION_PREFLIGHT_MANIFEST_SCHEMA_VERSION",
    "PRODUCTION_RENDER_MANIFEST_SCHEMA_VERSION",
    "ProjectAssemblyError",
    "ProjectAssemblyOptions",
    "ProjectAssemblyResult",
    "SUPPORTED_LOGO_EXTENSIONS",
    "UnknownDatasetBuilderError",
    "create_default_dataset_builder_registry",
    "load_production_brief",
    "parse_national_team_goals_parameters",
    "validate_builder_id",
    "validate_job_id",
]
