from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pandas as pd

from automation.logo_resolver import (
    LOGO_RESOLUTION_MANIFEST_SCHEMA_VERSION,
    LogoAsset,
    LogoResolutionResult,
)
from automation.orchestrator import (
    DATASET_BUILD_MANIFEST_SCHEMA_VERSION,
    DatasetProductionResult,
)
from automation.workspace import ProductionWorkspace
from config.dataset_config import DatasetConfig
from config.project_file_loader import load_project_file
from config.project_schema import CURRENT_PROJECT_SCHEMA_VERSION, migrate_project_data
from config.value_format_config import get_value_format, list_value_formats
from studio import project_builder
from validators.dataset_validator import DatasetValidator


PROJECT_ASSEMBLY_MANIFEST_SCHEMA_VERSION = 1
_MAX_PROJECT_NAME_LENGTH = 128
_MAX_TITLE_LENGTH = 500
_MAX_SOURCE_LABEL_LENGTH = 1000
_STYLE_FIELDS = ("label", "color")
_DATASET_STYLE_MAPS = {
    "category_labels": "label",
    "category_colors": "color",
}
_DATASET_CATEGORY_MAP_FIELDS = (
    "category_labels",
    "category_colors",
    "category_logos",
    "category_secondary_logos",
)


class ProjectAssemblyError(RuntimeError):
    """Raised when a production project cannot be assembled safely."""


@dataclass(frozen=True)
class ProjectAssemblyOptions:
    """Basic text fields replaced while assembling a production project."""

    project_name: str
    title: str
    source_label: str

    def __post_init__(self) -> None:
        self._validate_text(
            self.project_name,
            field_name="project_name",
            maximum_length=_MAX_PROJECT_NAME_LENGTH,
        )
        self._validate_text(
            self.title,
            field_name="title",
            maximum_length=_MAX_TITLE_LENGTH,
        )
        self._validate_text(
            self.source_label,
            field_name="source_label",
            maximum_length=_MAX_SOURCE_LABEL_LENGTH,
        )

    @staticmethod
    def _validate_text(value: object, *, field_name: str, maximum_length: int) -> None:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string.")
        if not value.strip():
            raise ValueError(f"{field_name} must not be empty or whitespace only.")
        if len(value) > maximum_length:
            raise ValueError(
                f"{field_name} must not exceed {maximum_length} characters."
            )
        if any(
            unicodedata.category(character) in ("Cc", "Cf", "Cs")
            for character in value
        ):
            raise ValueError(f"{field_name} must not contain control characters.")


@dataclass(frozen=True)
class ProjectAssemblyResult:
    """Deeply immutable record of one published production project."""

    workspace: ProductionWorkspace
    project_path: Path
    manifest_path: Path
    template_path: Path
    dataset_path: Path
    output_path: Path
    project_sha256: str
    project_size_bytes: int
    category_count: int
    primary_logo_count: int
    secondary_logo_count: int
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, ProductionWorkspace):
            raise TypeError("workspace must be a ProductionWorkspace.")
        expected_paths = {
            "project_path": self.workspace.project_json_path,
            "manifest_path": self.workspace.project_assembly_manifest_path,
            "dataset_path": self.workspace.dataset_csv_path,
            "output_path": self.workspace.video_path,
        }
        for field_name, expected_path in expected_paths.items():
            path = Path(getattr(self, field_name)).resolve(strict=False)
            if path != expected_path:
                raise ValueError(f"{field_name} must use its canonical workspace path.")
            object.__setattr__(self, field_name, path)

        template_path = Path(self.template_path)
        if not template_path.is_absolute():
            raise ValueError("template_path must be absolute.")
        object.__setattr__(
            self,
            "template_path",
            template_path.resolve(strict=True),
        )

        if (
            not isinstance(self.project_sha256, str)
            or len(self.project_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.project_sha256
            )
        ):
            raise ValueError("project_sha256 must be a lowercase SHA-256 digest.")

        integer_fields = (
            "project_size_bytes",
            "category_count",
            "primary_logo_count",
            "secondary_logo_count",
        )
        for field_name in integer_fields:
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer.")

        warnings = tuple(self.warnings)
        if any(not isinstance(warning, str) for warning in warnings):
            raise TypeError("warnings must contain only strings.")
        object.__setattr__(self, "warnings", warnings)


@dataclass(frozen=True)
class _AssemblyPlan:
    project_root: Path
    workspace: ProductionWorkspace
    template_path: Path
    template_data: dict
    template_preset: object
    dataset_path: Path
    dataset_reference: str
    period_column: str
    category_column: str
    value_column: str
    output_reference: str
    frames_reference: str
    categories: tuple[str, ...]
    category_styles: dict
    primary_logo_map: dict[str, str]
    secondary_logo_map: dict[str, str]
    warnings: tuple[str, ...]
    template_sha256: str
    template_size_bytes: int
    logo_manifest_reference: str | None


@dataclass(frozen=True)
class ProductionProjectAssembler:
    """Assemble one loadable project without orchestrating later stages."""

    def assemble(
        self,
        *,
        dataset_result: DatasetProductionResult,
        template_project_path: Path,
        project_root_dir: Path,
        options: ProjectAssemblyOptions,
        logo_result: LogoResolutionResult | None = None,
    ) -> ProjectAssemblyResult:
        try:
            plan = self._validate_and_plan(
                dataset_result=dataset_result,
                template_project_path=template_project_path,
                project_root_dir=project_root_dir,
                options=options,
                logo_result=logo_result,
            )
        except Exception as exc:
            raise self._error("validation", "validating project assembly inputs") from exc

        try:
            project_data = self._build_project_data(plan, options)
        except Exception as exc:
            raise self._error("build", "building project data in memory") from exc

        project_created = False
        stage = "save"
        try:
            self._reserve_project_path(plan.workspace.project_json_path)
            project_created = True
            project_builder.save_project_data(
                project_data,
                plan.workspace.project_json_path,
            )

            stage = "reload"
            loaded_preset = load_project_file(plan.workspace.project_json_path)
            self._verify_saved_project(
                project_data,
                loaded_preset=loaded_preset,
                plan=plan,
                options=options,
                dataset_result=dataset_result,
            )

            project_sha256 = self._sha256(plan.workspace.project_json_path)
            project_size_bytes = plan.workspace.project_json_path.stat().st_size
            result = ProjectAssemblyResult(
                workspace=plan.workspace,
                project_path=plan.workspace.project_json_path,
                manifest_path=plan.workspace.project_assembly_manifest_path,
                template_path=plan.template_path,
                dataset_path=plan.dataset_path,
                output_path=plan.workspace.video_path,
                project_sha256=project_sha256,
                project_size_bytes=project_size_bytes,
                category_count=len(plan.categories),
                primary_logo_count=len(plan.primary_logo_map),
                secondary_logo_count=len(plan.secondary_logo_map),
                warnings=plan.warnings,
            )

            stage = "manifest"
            plan.workspace.publish_project_assembly_manifest(
                self._manifest_data(
                    result,
                    plan=plan,
                    dataset_result=dataset_result,
                    options=options,
                )
            )
            return result
        except Exception as exc:
            if project_created:
                self._rollback_project(
                    plan.workspace.project_json_path,
                    original_error=exc,
                )
            operation = {
                "save": "saving project/project.json",
                "reload": "reloading and verifying project/project.json",
                "manifest": "publishing manifests/project_assembly.json",
            }[stage]
            raise self._error(stage, operation) from exc

    def _validate_and_plan(
        self,
        *,
        dataset_result: DatasetProductionResult,
        template_project_path: Path,
        project_root_dir: Path,
        options: ProjectAssemblyOptions,
        logo_result: LogoResolutionResult | None,
    ) -> _AssemblyPlan:
        if not isinstance(options, ProjectAssemblyOptions):
            raise TypeError("options must be ProjectAssemblyOptions.")
        if not isinstance(dataset_result, DatasetProductionResult):
            raise TypeError("dataset_result must be DatasetProductionResult.")

        project_root = self._resolved_directory(
            project_root_dir,
            field_name="project_root_dir",
        )
        workspace = dataset_result.workspace
        if not isinstance(workspace, ProductionWorkspace):
            raise TypeError("dataset_result.workspace must be ProductionWorkspace.")
        if not workspace.root_path.is_dir() or not workspace.root_path.is_relative_to(
            project_root
        ):
            raise ValueError("The production workspace must remain inside project_root_dir.")
        if dataset_result.brief.job_id != workspace.job_id:
            raise ValueError("Dataset result brief and workspace use different job IDs.")

        template_path = self._resolved_file(
            template_project_path,
            field_name="template_project_path",
        )
        if not template_path.is_relative_to(project_root):
            raise ValueError("The project template must remain inside project_root_dir.")

        if workspace.project_json_path.exists():
            raise FileExistsError("The workspace project already exists.")
        if workspace.project_assembly_manifest_path.exists():
            raise FileExistsError("The project assembly manifest already exists.")
        if workspace.video_path.exists():
            raise FileExistsError("The configured workspace video already exists.")

        template_preset = load_project_file(template_path)
        template_data = self._read_project_data(template_path)
        template_data = migrate_project_data(template_data).data
        self._normalize_template_asset_paths(
            template_data,
            project_root=project_root,
        )

        dataframe, categories = self._validate_dataset_result(
            dataset_result,
            project_root=project_root,
        )
        del dataframe

        primary_logo_map, secondary_logo_map, warnings, logo_manifest_reference = (
            self._validate_logo_result(
                logo_result,
                workspace=workspace,
                project_root=project_root,
                category_column=dataset_result.build_result.category_column,
                categories=categories,
            )
        )
        category_styles = self._current_category_styles(
            template_data,
            categories=categories,
        )
        category_styles = project_builder.apply_category_logo_matches(
            category_styles,
            primary_logo_map,
            logo_field="logo",
        )
        category_styles = project_builder.apply_category_logo_matches(
            category_styles,
            secondary_logo_map,
            logo_field="secondary_logo",
        )

        dataset_reference = self._relative_reference(
            workspace.dataset_csv_path,
            project_root,
        )
        output_reference = self._relative_reference(
            workspace.video_path,
            project_root,
        )
        frames_reference = self._relative_reference(
            workspace.render_dir / "frames",
            project_root,
        )
        return _AssemblyPlan(
            project_root=project_root,
            workspace=workspace,
            template_path=template_path,
            template_data=template_data,
            template_preset=template_preset,
            dataset_path=workspace.dataset_csv_path,
            dataset_reference=dataset_reference,
            period_column=dataset_result.build_result.period_column,
            category_column=dataset_result.build_result.category_column,
            value_column=dataset_result.build_result.value_column,
            output_reference=output_reference,
            frames_reference=frames_reference,
            categories=categories,
            category_styles=category_styles,
            primary_logo_map=primary_logo_map,
            secondary_logo_map=secondary_logo_map,
            warnings=warnings,
            template_sha256=self._sha256(template_path),
            template_size_bytes=template_path.stat().st_size,
            logo_manifest_reference=logo_manifest_reference,
        )

    def _validate_dataset_result(
        self,
        dataset_result: DatasetProductionResult,
        *,
        project_root: Path,
    ) -> tuple[pd.DataFrame, tuple[str, ...]]:
        workspace = dataset_result.workspace
        build_result = dataset_result.build_result
        dataset_path = workspace.dataset_csv_path
        if dataset_result.dataset_manifest_path != workspace.dataset_build_manifest_path:
            raise ValueError("Dataset result declares a noncanonical manifest path.")
        if dataset_result.status_path != workspace.status_path:
            raise ValueError("Dataset result declares a noncanonical status path.")
        if build_result.csv_path != dataset_path:
            raise ValueError("Dataset result declares a noncanonical dataset path.")
        if not dataset_path.is_file() or not dataset_path.is_relative_to(project_root):
            raise ValueError("The production dataset must exist inside project_root_dir.")

        status = self._read_json_object(workspace.status_path, "workspace status")
        if (
            status.get("state") != "dataset_ready"
            or status.get("stage") != "dataset"
            or status.get("job_id") != workspace.job_id
        ):
            raise ValueError("Workspace status must be dataset_ready for this job.")

        dataset_size = dataset_path.stat().st_size
        dataset_sha256 = self._sha256(dataset_path)
        if dataset_size != build_result.output_size_bytes:
            raise ValueError("Dataset size does not match DatasetBuildResult.")
        if dataset_sha256 != build_result.output_sha256:
            raise ValueError("Dataset SHA-256 does not match DatasetBuildResult.")

        columns = (
            build_result.period_column,
            build_result.category_column,
            build_result.value_column,
        )
        if any(not isinstance(column, str) or not column.strip() for column in columns):
            raise ValueError("Dataset columns must be non-empty strings.")
        if len(set(columns)) != len(columns):
            raise ValueError("Dataset columns must be distinct.")

        dataframe = pd.read_csv(dataset_path, encoding="utf-8")
        validated = DatasetValidator(
            DatasetConfig(
                year_column=build_result.period_column,
                name_column=build_result.category_column,
                value_column=build_result.value_column,
            )
        ).validate(dataframe)
        if len(dataframe) != build_result.row_count:
            raise ValueError("Dataset row count does not match DatasetBuildResult.")

        raw_categories = dataframe[build_result.category_column]
        if any(not isinstance(value, str) for value in raw_categories):
            raise ValueError("Dataset categories must be strings.")
        categories = tuple(
            sorted(
                set(raw_categories),
                key=lambda value: (value.casefold(), value),
            )
        )
        if len(categories) != build_result.category_count:
            raise ValueError("Dataset category count does not match DatasetBuildResult.")
        if validated[build_result.period_column].nunique() != build_result.period_count:
            raise ValueError("Dataset period count does not match DatasetBuildResult.")

        manifest = self._read_json_object(
            workspace.dataset_build_manifest_path,
            "dataset build manifest",
        )
        dataset_manifest = manifest.get("dataset")
        builder_manifest = manifest.get("builder")
        if (
            manifest.get("dataset_build_manifest_schema_version")
            != DATASET_BUILD_MANIFEST_SCHEMA_VERSION
            or not isinstance(dataset_manifest, dict)
            or not isinstance(builder_manifest, dict)
            or builder_manifest.get("id") != build_result.builder_id
            or builder_manifest.get("version") != build_result.builder_version
            or dataset_manifest.get("path")
            != dataset_path.relative_to(workspace.root_path).as_posix()
            or dataset_manifest.get("sha256") != dataset_sha256
            or dataset_manifest.get("size_bytes") != dataset_size
            or dataset_manifest.get("row_count") != build_result.row_count
            or dataset_manifest.get("period_count") != build_result.period_count
            or dataset_manifest.get("category_count") != build_result.category_count
            or dataset_manifest.get("columns")
            != {
                "period": build_result.period_column,
                "category": build_result.category_column,
                "value": build_result.value_column,
            }
        ):
            raise ValueError("Dataset build manifest does not match DatasetBuildResult.")
        return dataframe, categories

    def _validate_logo_result(
        self,
        logo_result: LogoResolutionResult | None,
        *,
        workspace: ProductionWorkspace,
        project_root: Path,
        category_column: str,
        categories: tuple[str, ...],
    ) -> tuple[dict[str, str], dict[str, str], tuple[str, ...], str | None]:
        if logo_result is None:
            return {}, {}, (), None
        if not isinstance(logo_result, LogoResolutionResult):
            raise TypeError("logo_result must be LogoResolutionResult or None.")
        if logo_result.workspace != workspace:
            raise ValueError("Logo resolution must belong to the dataset workspace.")
        if logo_result.category_column != category_column:
            raise ValueError("Logo resolution uses a different category column.")
        if logo_result.total_categories != len(categories):
            raise ValueError("Logo resolution category count does not match the dataset.")
        if logo_result.manifest_path != workspace.logo_resolution_manifest_path:
            raise ValueError("Logo resolution declares a noncanonical manifest path.")
        if not logo_result.manifest_path.is_file():
            raise ValueError("Logo resolution manifest does not exist.")

        category_set = set(categories)
        primary_map = self._validate_logo_assets(
            logo_result.primary_assets,
            slot="primary",
            workspace=workspace,
            project_root=project_root,
            categories=category_set,
        )
        secondary_map = self._validate_logo_assets(
            logo_result.secondary_assets,
            slot="secondary",
            workspace=workspace,
            project_root=project_root,
            categories=category_set,
        )
        expected_missing_primary = tuple(
            category for category in categories if category not in primary_map
        )
        expected_missing_secondary = tuple(
            category for category in categories if category not in secondary_map
        )
        if logo_result.missing_primary != expected_missing_primary:
            raise ValueError("Logo result has inconsistent missing primary categories.")
        if logo_result.missing_secondary != expected_missing_secondary:
            raise ValueError("Logo result has inconsistent missing secondary categories.")
        for ambiguous, matches, slot in (
            (logo_result.ambiguous_primary, primary_map, "primary"),
            (logo_result.ambiguous_secondary, secondary_map, "secondary"),
        ):
            if (
                len(ambiguous) != len(set(ambiguous))
                or any(category not in matches for category in ambiguous)
            ):
                raise ValueError(f"Logo result has invalid ambiguous {slot} categories.")
        if any(not isinstance(warning, str) for warning in logo_result.warnings):
            raise ValueError("Logo result warnings must be strings.")
        expected_manifest = self._logo_manifest_data(logo_result)
        actual_manifest = self._read_json_object(
            logo_result.manifest_path,
            "logo resolution manifest",
        )
        if actual_manifest != expected_manifest:
            raise ValueError("Logo resolution manifest does not match LogoResolutionResult.")
        return (
            primary_map,
            secondary_map,
            tuple(logo_result.warnings),
            self._relative_reference(logo_result.manifest_path, project_root),
        )

    def _validate_logo_assets(
        self,
        assets: tuple[LogoAsset, ...],
        *,
        slot: str,
        workspace: ProductionWorkspace,
        project_root: Path,
        categories: set[str],
    ) -> dict[str, str]:
        expected_directory = (
            workspace.primary_logos_dir
            if slot == "primary"
            else workspace.secondary_logos_dir
        )
        result: dict[str, str] = {}
        for asset in assets:
            if not isinstance(asset, LogoAsset) or asset.slot != slot:
                raise ValueError(f"Logo result contains an invalid {slot} asset.")
            if asset.category not in categories:
                raise ValueError(f"{slot.capitalize()} logo category is not in the dataset.")
            if asset.category in result:
                raise ValueError(f"Duplicate {slot} logo category.")
            if (
                not asset.workspace_path.is_file()
                or asset.workspace_path.parent != expected_directory
                or not asset.workspace_path.is_relative_to(workspace.root_path)
                or not asset.workspace_path.is_relative_to(project_root)
                or asset.workspace_path
                != (workspace.root_path / PurePosixPath(asset.relative_path)).resolve(
                    strict=True
                )
            ):
                raise ValueError(f"{slot.capitalize()} logo path is not canonical.")
            if asset.workspace_path.stat().st_size != asset.size_bytes:
                raise ValueError(f"{slot.capitalize()} logo size does not match.")
            if self._sha256(asset.workspace_path) != asset.sha256:
                raise ValueError(f"{slot.capitalize()} logo SHA-256 does not match.")
            result[asset.category] = self._relative_reference(
                asset.workspace_path,
                project_root,
            )
        return {category: result[category] for category in sorted(result)}

    @staticmethod
    def _current_category_styles(
        template_data: dict,
        *,
        categories: tuple[str, ...],
    ) -> dict:
        category_set = set(categories)
        styles: dict[str, dict] = {}
        raw_styles = template_data.get("categories", {})
        if isinstance(raw_styles, dict):
            for category in categories:
                style = raw_styles.get(category)
                if isinstance(style, dict):
                    kept = {
                        field: style[field]
                        for field in _STYLE_FIELDS
                        if field in style
                    }
                    if kept:
                        styles[category] = kept

        dataset_section = template_data.get("dataset", {})
        if isinstance(dataset_section, dict):
            for map_name, style_name in _DATASET_STYLE_MAPS.items():
                values = dataset_section.get(map_name, {})
                if not isinstance(values, dict):
                    continue
                for category, value in values.items():
                    if category in category_set:
                        styles.setdefault(category, {})[style_name] = value
            for field_name in _DATASET_CATEGORY_MAP_FIELDS:
                dataset_section.pop(field_name, None)

        data_source = template_data.get("data_source")
        if isinstance(data_source, dict):
            data_source.pop("sqlite_database_path", None)
            data_source.pop("sqlite_table_name", None)
        return styles

    @staticmethod
    def _normalize_template_asset_paths(
        template_data: dict,
        *,
        project_root: Path,
    ) -> None:
        chart = template_data.get("chart", {})
        if not isinstance(chart, dict):
            return
        for field_name in ("background_image_path", "bar_texture_custom_image"):
            value = chart.get(field_name)
            if value is None:
                continue
            if not isinstance(value, str) or not value:
                raise ValueError(f"chart.{field_name} must be a non-empty path.")
            path = Path(value)
            if path.is_absolute():
                resolved = path.resolve(strict=False)
                if not resolved.is_relative_to(project_root):
                    raise ValueError(
                        f"chart.{field_name} must remain inside project_root_dir."
                    )
                value = resolved.relative_to(project_root).as_posix()
                chart[field_name] = value
            ProductionProjectAssembler._validate_relative_posix_reference(
                value,
                field_name=f"chart.{field_name}",
            )

    def _build_project_data(
        self,
        plan: _AssemblyPlan,
        options: ProjectAssemblyOptions,
    ) -> dict:
        chart = plan.template_preset.chart_config
        selection = chart.selection
        return project_builder.build_project_data(
            name=options.project_name,
            csv_path=plan.dataset_reference,
            year_column=plan.period_column,
            name_column=plan.category_column,
            value_column=plan.value_column,
            title=options.title,
            source_label=options.source_label,
            output_file=plan.output_reference,
            frames_dir=plan.frames_reference,
            layout_preset=chart.layout_preset,
            theme=chart.theme.name,
            background_mode=chart.background_mode,
            background_color_override=chart.background_color_override,
            background_image_path=plan.template_data.get("chart", {}).get(
                "background_image_path",
                chart.background_image_path,
            ),
            background_image_fit=chart.background_image_fit,
            typography_preset=chart.typography_preset,
            value_format=self._value_format_name(chart.value_format),
            fps=chart.fps,
            steps_per_transition=chart.steps_per_transition,
            top_n=selection.top_n,
            max_visible_bars=chart.max_visible_bars,
            png_compress_level=chart.png_compress_level,
            frame_output_mode=chart.frame_output_mode,
            motion_mode=chart.animation.motion_mode,
            aggregate_other=selection.aggregate_other,
            category_styles=plan.category_styles,
            base_project_data=plan.template_data,
        )

    @staticmethod
    def _value_format_name(value_format: object) -> str:
        for name in list_value_formats():
            if get_value_format(name) == value_format:
                return name
        raise ValueError("Template value format is not a named compatible preset.")

    @staticmethod
    def _reserve_project_path(project_path: Path) -> None:
        with project_path.open("xb"):
            pass

    @staticmethod
    def _verify_saved_project(
        project_data: dict,
        *,
        loaded_preset: object,
        plan: _AssemblyPlan,
        options: ProjectAssemblyOptions,
        dataset_result: DatasetProductionResult,
    ) -> None:
        saved_data = ProductionProjectAssembler._read_project_data(
            plan.workspace.project_json_path
        )
        if saved_data != migrate_project_data(project_data).data:
            raise ValueError("Saved project data differs from assembled project data.")
        chart = loaded_preset.chart_config
        dataset = loaded_preset.dataset_config
        source = loaded_preset.data_source_config
        if (
            loaded_preset.name != options.project_name
            or chart.title != options.title
            or chart.output_file != plan.output_reference
            or source.source_type != "csv"
            or source.csv_path != plan.dataset_reference
            or source.source_label_override != options.source_label
            or dataset.year_column != dataset_result.build_result.period_column
            or dataset.name_column != dataset_result.build_result.category_column
            or dataset.value_column != dataset_result.build_result.value_column
            or dataset.category_logos != plan.primary_logo_map
            or dataset.category_secondary_logos != plan.secondary_logo_map
        ):
            raise ValueError("Reloaded project does not match the assembly plan.")
        if plan.workspace.video_path.exists():
            raise ValueError("Project assembly unexpectedly created the configured video.")

    @staticmethod
    def _manifest_data(
        result: ProjectAssemblyResult,
        *,
        plan: _AssemblyPlan,
        dataset_result: DatasetProductionResult,
        options: ProjectAssemblyOptions,
    ) -> dict:
        build_result = dataset_result.build_result
        return {
            "project_assembly_manifest_schema_version": (
                PROJECT_ASSEMBLY_MANIFEST_SCHEMA_VERSION
            ),
            "project": {
                "path": result.project_path.relative_to(plan.project_root).as_posix(),
                "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
                "name": options.project_name,
                "sha256": result.project_sha256,
                "size_bytes": result.project_size_bytes,
            },
            "template": {
                "path": plan.template_path.relative_to(plan.project_root).as_posix(),
                "sha256": plan.template_sha256,
                "size_bytes": plan.template_size_bytes,
            },
            "dataset": {
                "path": plan.dataset_reference,
                "sha256": build_result.output_sha256,
                "size_bytes": build_result.output_size_bytes,
                "columns": {
                    "period": build_result.period_column,
                    "category": build_result.category_column,
                    "value": build_result.value_column,
                },
            },
            "logos": {
                "manifest": plan.logo_manifest_reference,
                "primary_count": result.primary_logo_count,
                "secondary_count": result.secondary_logo_count,
            },
            "output": {"path": plan.output_reference},
            "category_count": result.category_count,
            "warnings": list(result.warnings),
        }

    @staticmethod
    def _logo_manifest_data(result: LogoResolutionResult) -> dict:
        def assets(values: tuple[LogoAsset, ...]) -> list[dict]:
            return [
                {
                    "category": asset.category,
                    "path": asset.relative_path,
                    "sha256": asset.sha256,
                    "size_bytes": asset.size_bytes,
                }
                for asset in values
            ]

        return {
            "logo_resolution_manifest_schema_version": (
                LOGO_RESOLUTION_MANIFEST_SCHEMA_VERSION
            ),
            "category_column": result.category_column,
            "category_count": result.total_categories,
            "primary": {
                "assets": assets(result.primary_assets),
                "missing": list(result.missing_primary),
                "ambiguous": list(result.ambiguous_primary),
            },
            "secondary": {
                "assets": assets(result.secondary_assets),
                "missing": list(result.missing_secondary),
                "ambiguous": list(result.ambiguous_secondary),
            },
            "warnings": list(result.warnings),
        }

    @staticmethod
    def _rollback_project(project_path: Path, *, original_error: Exception) -> None:
        try:
            project_path.unlink(missing_ok=True)
        except Exception as rollback_error:
            original_error.add_note(
                "Project rollback also failed: "
                f"{type(rollback_error).__name__}."
            )

    @staticmethod
    def _resolved_directory(path: Path, *, field_name: str) -> Path:
        if not isinstance(path, Path):
            raise TypeError(f"{field_name} must be a pathlib.Path.")
        if not path.is_absolute():
            raise ValueError(f"{field_name} must be absolute and resolved.")
        resolved = path.resolve(strict=True)
        if resolved != path or not resolved.is_dir():
            raise ValueError(f"{field_name} must be an existing resolved directory.")
        return resolved

    @staticmethod
    def _resolved_file(path: Path, *, field_name: str) -> Path:
        if not isinstance(path, Path):
            raise TypeError(f"{field_name} must be a pathlib.Path.")
        if not path.is_absolute():
            raise ValueError(f"{field_name} must be absolute and resolved.")
        resolved = path.resolve(strict=True)
        if resolved != path or not resolved.is_file():
            raise ValueError(f"{field_name} must be an existing resolved file.")
        return resolved

    @staticmethod
    def _read_project_data(path: Path) -> dict:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Project JSON must contain an object.")
        return data

    @staticmethod
    def _read_json_object(path: Path, label: str) -> dict:
        if not path.is_file():
            raise ValueError(f"{label.capitalize()} does not exist.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{label.capitalize()} must contain a JSON object.")
        return data

    @staticmethod
    def _validate_relative_posix_reference(value: object, *, field_name: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} must be a non-empty relative path.")
        pure_path = PurePosixPath(value)
        if (
            "\\" in value
            or ":" in value
            or pure_path.is_absolute()
            or pure_path.as_posix() != value
            or any(part in ("", ".", "..") for part in pure_path.parts)
        ):
            raise ValueError(f"{field_name} must be a portable relative POSIX path.")
        return value

    @staticmethod
    def _relative_reference(path: Path, project_root: Path) -> str:
        resolved = Path(path).resolve(strict=False)
        if not resolved.is_relative_to(project_root):
            raise ValueError("Artifact path escapes project_root_dir.")
        reference = resolved.relative_to(project_root).as_posix()
        return ProductionProjectAssembler._validate_relative_posix_reference(
            reference,
            field_name="artifact reference",
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _error(stage: str, operation: str) -> ProjectAssemblyError:
        return ProjectAssemblyError(
            f"Production project assembly failed during {stage!r} while {operation}."
        )
