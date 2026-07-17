from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pandas as pd

from automation.workspace import ProductionWorkspace
from studio import project_builder


LOGO_RESOLUTION_MANIFEST_SCHEMA_VERSION = 1
SUPPORTED_LOGO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
_MISSING_POLICIES = frozenset(("allow", "warn", "error"))
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)


class LogoResolutionError(RuntimeError):
    """Raised when local logo analysis or publication cannot complete."""


@dataclass(frozen=True)
class LogoAsset:
    """Immutable record of one logo copied into a production workspace."""

    category: str
    slot: str
    source_path: Path
    workspace_path: Path
    relative_path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.category, str) or not self.category.strip():
            raise ValueError("LogoAsset category must be a non-empty string.")
        if self.slot not in ("primary", "secondary"):
            raise ValueError("LogoAsset slot must be 'primary' or 'secondary'.")

        source_path = Path(self.source_path)
        workspace_path = Path(self.workspace_path)
        if not source_path.is_absolute() or not workspace_path.is_absolute():
            raise ValueError("LogoAsset paths must be absolute.")
        source_path = source_path.resolve(strict=True)
        workspace_path = workspace_path.resolve(strict=True)
        if not source_path.is_file() or not workspace_path.is_file():
            raise ValueError("LogoAsset paths must identify regular files.")

        relative = self.relative_path
        pure_relative = PurePosixPath(relative)
        if (
            not isinstance(relative, str)
            or not relative
            or "\\" in relative
            or pure_relative.is_absolute()
            or any(part in ("", ".", "..") for part in pure_relative.parts)
            or pure_relative.as_posix() != relative
        ):
            raise ValueError(
                "LogoAsset relative_path must be a portable relative POSIX path."
            )
        if (
            not isinstance(self.sha256, str)
            or len(self.sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.sha256)
        ):
            raise ValueError("LogoAsset sha256 must be a lowercase SHA-256 digest.")
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise ValueError("LogoAsset size_bytes must be a non-negative integer.")

        object.__setattr__(self, "source_path", source_path)
        object.__setattr__(self, "workspace_path", workspace_path)


@dataclass(frozen=True)
class LogoResolutionResult:
    """Immutable result of one local two-slot logo resolution."""

    workspace: ProductionWorkspace
    category_column: str
    primary_assets: tuple[LogoAsset, ...]
    secondary_assets: tuple[LogoAsset, ...]
    missing_primary: tuple[str, ...]
    missing_secondary: tuple[str, ...]
    ambiguous_primary: tuple[str, ...]
    ambiguous_secondary: tuple[str, ...]
    warnings: tuple[str, ...]
    manifest_path: Path
    total_categories: int

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, ProductionWorkspace):
            raise TypeError("workspace must be a ProductionWorkspace.")
        if not isinstance(self.category_column, str) or not self.category_column:
            raise ValueError("category_column must be a non-empty string.")

        tuple_fields = (
            "primary_assets",
            "secondary_assets",
            "missing_primary",
            "missing_secondary",
            "ambiguous_primary",
            "ambiguous_secondary",
            "warnings",
        )
        for field_name in tuple_fields:
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))

        if any(asset.slot != "primary" for asset in self.primary_assets):
            raise ValueError("primary_assets may contain only primary LogoAsset values.")
        if any(asset.slot != "secondary" for asset in self.secondary_assets):
            raise ValueError(
                "secondary_assets may contain only secondary LogoAsset values."
            )
        if (
            isinstance(self.total_categories, bool)
            or not isinstance(self.total_categories, int)
            or self.total_categories < 0
        ):
            raise ValueError("total_categories must be a non-negative integer.")

        manifest_path = Path(self.manifest_path).resolve(strict=False)
        if manifest_path != self.workspace.logo_resolution_manifest_path:
            raise ValueError(
                "manifest_path must be the workspace logo resolution manifest."
            )
        object.__setattr__(self, "manifest_path", manifest_path)

    def primary_logo_map(self) -> dict[str, str]:
        return {
            asset.category: asset.relative_path for asset in self.primary_assets
        }

    def secondary_logo_map(self) -> dict[str, str]:
        return {
            asset.category: asset.relative_path for asset in self.secondary_assets
        }


@dataclass(frozen=True)
class _PlannedLogo:
    category: str
    slot: str
    source_path: Path
    destination_path: Path
    relative_path: str


@dataclass(frozen=True)
class _ResolutionPlan:
    categories: tuple[str, ...]
    primary: tuple[_PlannedLogo, ...]
    secondary: tuple[_PlannedLogo, ...]
    missing_primary: tuple[str, ...]
    missing_secondary: tuple[str, ...]
    ambiguous_primary: tuple[str, ...]
    ambiguous_secondary: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class LocalLogoResolver:
    """Resolve matching local images and publish immutable workspace copies."""

    def resolve(
        self,
        *,
        dataset_csv: Path,
        category_column: str,
        workspace: ProductionWorkspace,
        primary_logo_dir: Path | None = None,
        secondary_logo_dir: Path | None = None,
        missing_policy: str = "warn",
    ) -> LogoResolutionResult:
        try:
            (
                categories,
                primary_paths,
                secondary_paths,
            ) = self._validate_inputs(
                dataset_csv=dataset_csv,
                category_column=category_column,
                workspace=workspace,
                primary_logo_dir=primary_logo_dir,
                secondary_logo_dir=secondary_logo_dir,
                missing_policy=missing_policy,
            )
        except Exception as exc:
            raise self._error("validation", "validating local logo inputs") from exc

        try:
            plan = self._build_plan(
                categories=categories,
                workspace=workspace,
                primary_paths=primary_paths,
                secondary_paths=secondary_paths,
                missing_policy=missing_policy,
            )
        except Exception as exc:
            raise self._error("matching", "matching categories to local logos") from exc

        return self._publish_plan(
            plan,
            category_column=category_column,
            workspace=workspace,
        )

    def _validate_inputs(
        self,
        *,
        dataset_csv: Path,
        category_column: str,
        workspace: ProductionWorkspace,
        primary_logo_dir: Path | None,
        secondary_logo_dir: Path | None,
        missing_policy: str,
    ) -> tuple[tuple[str, ...], tuple[Path, ...] | None, tuple[Path, ...] | None]:
        if not isinstance(workspace, ProductionWorkspace):
            raise TypeError("workspace must be a ProductionWorkspace.")
        if not workspace.root_path.is_dir():
            raise ValueError("workspace must already exist.")
        if not workspace.logos_dir.is_dir() or not workspace.manifests_dir.is_dir():
            raise ValueError("workspace logo and manifest directories must exist.")
        if workspace.logo_resolution_manifest_path.exists():
            raise FileExistsError("Logo resolution manifest already exists.")
        self._validate_empty_target(workspace.primary_logos_dir, "primary")
        self._validate_empty_target(workspace.secondary_logos_dir, "secondary")

        if not isinstance(missing_policy, str) or missing_policy not in _MISSING_POLICIES:
            raise ValueError(
                "missing_policy must be exactly one of: allow, error, warn."
            )
        if not isinstance(category_column, str) or not category_column:
            raise ValueError("category_column must be a non-empty string.")

        if not isinstance(dataset_csv, Path):
            raise TypeError("dataset_csv must be a pathlib.Path.")
        if not dataset_csv.is_absolute():
            raise ValueError("dataset_csv must be absolute.")
        dataset_path = dataset_csv.resolve(strict=True)
        if dataset_path != dataset_csv or not dataset_path.is_file():
            raise ValueError("dataset_csv must be a resolved regular file.")

        dataframe = pd.read_csv(
            dataset_path,
            usecols=[category_column],
            encoding="utf-8",
            keep_default_na=False,
        )
        categories = []
        for row_number, value in enumerate(dataframe[category_column], start=2):
            if pd.isna(value):
                raise ValueError(f"Category is null at CSV row {row_number}.")
            if not isinstance(value, str):
                raise ValueError(
                    f"Category at CSV row {row_number} must be text."
                )
            if not value.strip():
                raise ValueError(f"Category is blank at CSV row {row_number}.")
            categories.append(value)
        ordered_categories = tuple(
            sorted(set(categories), key=lambda value: (value.casefold(), value))
        )

        primary_paths = self._logo_paths(primary_logo_dir, "primary")
        secondary_paths = self._logo_paths(secondary_logo_dir, "secondary")
        return ordered_categories, primary_paths, secondary_paths

    @staticmethod
    def _validate_empty_target(path: Path, slot: str) -> None:
        if not path.exists():
            return
        if not path.is_dir():
            raise ValueError(f"Workspace {slot} logo target must be a directory.")
        if any(path.iterdir()):
            raise ValueError(
                f"Workspace {slot} logo target must be empty before resolution."
            )

    @staticmethod
    def _logo_paths(directory: Path | None, slot: str) -> tuple[Path, ...] | None:
        if directory is None:
            return None
        if not isinstance(directory, Path):
            raise TypeError(f"{slot}_logo_dir must be a pathlib.Path or None.")
        if not directory.is_absolute():
            raise ValueError(f"{slot}_logo_dir must be absolute.")
        resolved = directory.resolve(strict=True)
        if not resolved.is_dir():
            raise NotADirectoryError(f"{slot}_logo_dir must be a directory.")

        candidates = []
        for path in resolved.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_LOGO_EXTENSIONS:
                continue
            if LocalLogoResolver._is_temporary_file(path):
                continue
            if path.stat().st_size == 0:
                continue
            candidates.append(path.resolve(strict=True))
        return tuple(sorted(candidates, key=lambda path: (str(path).casefold(), str(path))))

    @staticmethod
    def _is_temporary_file(path: Path) -> bool:
        name = path.name.casefold()
        return (
            name.startswith(".")
            or name.startswith("~$")
            or ".tmp." in name
            or name.endswith("~")
        )

    def _build_plan(
        self,
        *,
        categories: tuple[str, ...],
        workspace: ProductionWorkspace,
        primary_paths: tuple[Path, ...] | None,
        secondary_paths: tuple[Path, ...] | None,
        missing_policy: str,
    ) -> _ResolutionPlan:
        primary_matches, ambiguous_primary = self._match_slot(
            categories,
            primary_paths,
        )
        secondary_matches, ambiguous_secondary = self._match_slot(
            categories,
            secondary_paths,
        )
        missing_primary = tuple(
            category for category in categories if category not in primary_matches
        )
        missing_secondary = tuple(
            category for category in categories if category not in secondary_matches
        )
        if missing_policy == "error" and missing_primary:
            raise ValueError(
                "Missing primary logos for categories: "
                + ", ".join(missing_primary)
                + "."
            )

        warnings = []
        if missing_policy == "warn":
            warnings.extend(
                f"Missing primary logo for category {category!r}."
                for category in missing_primary
            )
        warnings.extend(
            f"Ambiguous primary logo match for category {category!r}; "
            "the deterministic first match was selected."
            for category in ambiguous_primary
        )
        warnings.extend(
            f"Ambiguous secondary logo match for category {category!r}; "
            "the deterministic first match was selected."
            for category in ambiguous_secondary
        )

        primary = self._plan_slot(
            categories,
            matches=primary_matches,
            slot="primary",
            destination_dir=workspace.primary_logos_dir,
            workspace=workspace,
        )
        secondary = self._plan_slot(
            categories,
            matches=secondary_matches,
            slot="secondary",
            destination_dir=workspace.secondary_logos_dir,
            workspace=workspace,
        )
        return _ResolutionPlan(
            categories=categories,
            primary=primary,
            secondary=secondary,
            missing_primary=missing_primary,
            missing_secondary=missing_secondary,
            ambiguous_primary=ambiguous_primary,
            ambiguous_secondary=ambiguous_secondary,
            warnings=tuple(sorted(warnings, key=lambda value: (value.casefold(), value))),
        )

    @staticmethod
    def _match_slot(
        categories: tuple[str, ...],
        paths: tuple[Path, ...] | None,
    ) -> tuple[dict[str, Path], tuple[str, ...]]:
        if paths is None:
            return {}, ()
        raw_matches = project_builder.match_category_logos(categories, paths)
        matches = {
            category: Path(raw_matches[category]).resolve(strict=True)
            for category in categories
            if category in raw_matches
        }
        ambiguous = []
        for category in categories:
            if category not in matches:
                continue
            exact_key = category.strip().casefold()
            exact_candidates = tuple(
                path
                for path in paths
                if path.stem.strip().casefold() == exact_key
            )
            if exact_candidates:
                candidates = exact_candidates
            else:
                normalized_key = project_builder.logo_match_key(category)
                candidates = tuple(
                    path
                    for path in paths
                    if project_builder.logo_match_key(path.stem) == normalized_key
                )
            if len(candidates) > 1:
                ambiguous.append(category)
        return matches, tuple(ambiguous)

    def _plan_slot(
        self,
        categories: tuple[str, ...],
        *,
        matches: dict[str, Path],
        slot: str,
        destination_dir: Path,
        workspace: ProductionWorkspace,
    ) -> tuple[_PlannedLogo, ...]:
        planned = []
        destinations: dict[Path, str] = {}
        for category in categories:
            source_path = matches.get(category)
            if source_path is None:
                continue
            suffix = source_path.suffix.lower()
            filename = self._destination_filename(category, suffix)
            destination_path = (destination_dir / filename).resolve(strict=False)
            if destination_path.parent != destination_dir:
                raise ValueError("Planned logo destination escapes its slot directory.")
            previous_category = destinations.get(destination_path)
            if previous_category is not None and previous_category != category:
                raise ValueError(
                    f"Destination name collision in {slot} slot between categories "
                    f"{previous_category!r} and {category!r}."
                )
            if destination_path.exists():
                raise FileExistsError(
                    f"Planned {slot} logo destination already exists for "
                    f"category {category!r}."
                )
            destinations[destination_path] = category
            planned.append(
                _PlannedLogo(
                    category=category,
                    slot=slot,
                    source_path=source_path,
                    destination_path=destination_path,
                    relative_path=destination_path.relative_to(
                        workspace.root_path
                    ).as_posix(),
                )
            )
        return tuple(planned)

    @staticmethod
    def _destination_filename(category: str, suffix: str) -> str:
        slug = project_builder.logo_match_key(category).replace("_", "-")
        slug = slug.strip("-")[:64] or "category"
        if slug.casefold() in _WINDOWS_RESERVED_NAMES:
            slug = f"category-{slug}"
        category_hash = hashlib.sha256(category.encode("utf-8")).hexdigest()[:12]
        return f"{slug}--{category_hash}{suffix.lower()}"

    def _publish_plan(
        self,
        plan: _ResolutionPlan,
        *,
        category_column: str,
        workspace: ProductionWorkspace,
    ) -> LogoResolutionResult:
        created_directories: list[Path] = []
        created_files: list[Path] = []
        primary_assets = []
        secondary_assets = []
        current_plan = None
        stage = "copy"
        try:
            for slot_plans, destination_dir, asset_list in (
                (plan.primary, workspace.primary_logos_dir, primary_assets),
                (plan.secondary, workspace.secondary_logos_dir, secondary_assets),
            ):
                if slot_plans and not destination_dir.exists():
                    destination_dir.mkdir(exist_ok=False)
                    created_directories.append(destination_dir)
                for current_plan in slot_plans:
                    self._copy_file_exclusive(
                        current_plan.source_path,
                        current_plan.destination_path,
                    )
                    created_files.append(current_plan.destination_path)
                    asset_list.append(
                        LogoAsset(
                            category=current_plan.category,
                            slot=current_plan.slot,
                            source_path=current_plan.source_path,
                            workspace_path=current_plan.destination_path,
                            relative_path=current_plan.relative_path,
                            sha256=self._sha256(current_plan.destination_path),
                            size_bytes=current_plan.destination_path.stat().st_size,
                        )
                    )

            result = LogoResolutionResult(
                workspace=workspace,
                category_column=category_column,
                primary_assets=tuple(primary_assets),
                secondary_assets=tuple(secondary_assets),
                missing_primary=plan.missing_primary,
                missing_secondary=plan.missing_secondary,
                ambiguous_primary=plan.ambiguous_primary,
                ambiguous_secondary=plan.ambiguous_secondary,
                warnings=plan.warnings,
                manifest_path=workspace.logo_resolution_manifest_path,
                total_categories=len(plan.categories),
            )
            stage = "manifest"
            workspace.publish_logo_resolution_manifest(
                self._manifest_data(result)
            )
            return result
        except Exception as exc:
            self._rollback_created_assets(
                created_files,
                created_directories,
                original_error=exc,
            )
            context = "publishing logo_resolution.json"
            if stage == "copy" and current_plan is not None:
                context = (
                    f"copying {current_plan.slot} logo for category "
                    f"{current_plan.category!r}"
                )
            raise self._error(stage, context) from exc

    @staticmethod
    def _copy_file_exclusive(source_path: Path, destination_path: Path) -> None:
        temporary_path = None
        published = False
        try:
            with source_path.open("rb") as source_file, tempfile.NamedTemporaryFile(
                mode="xb",
                prefix=f".{destination_path.name}.",
                suffix=".tmp",
                dir=destination_path.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                    temporary_file.write(chunk)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            try:
                os.link(temporary_path, destination_path)
                published = True
            except FileExistsError as exc:
                raise FileExistsError("Logo destination already exists.") from exc
            except OSError as exc:
                raise OSError("Atomic logo publication failed.") from exc
            temporary_path.unlink()
        except Exception as original_error:
            if published:
                try:
                    destination_path.unlink(missing_ok=True)
                except Exception as cleanup_error:
                    original_error.add_note(
                        "Published logo cleanup also failed: "
                        f"{type(cleanup_error).__name__}."
                    )
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except Exception as cleanup_error:
                    original_error.add_note(
                        "Temporary logo cleanup also failed: "
                        f"{type(cleanup_error).__name__}."
                    )
            raise

    @staticmethod
    def _rollback_created_assets(
        created_files: list[Path],
        created_directories: list[Path],
        *,
        original_error: Exception,
    ) -> None:
        for path in reversed(created_files):
            try:
                path.unlink(missing_ok=True)
            except Exception as cleanup_error:
                original_error.add_note(
                    "Logo rollback could not remove a created file: "
                    f"{type(cleanup_error).__name__}."
                )
        for path in reversed(created_directories):
            try:
                path.rmdir()
            except Exception as cleanup_error:
                original_error.add_note(
                    "Logo rollback could not remove a created directory: "
                    f"{type(cleanup_error).__name__}."
                )

    @staticmethod
    def _manifest_data(result: LogoResolutionResult) -> dict:
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
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _error(stage: str, operation: str) -> LogoResolutionError:
        return LogoResolutionError(
            f"Local logo resolution failed during {stage!r} while {operation}."
        )
