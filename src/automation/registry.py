from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from automation.brief_loader import validate_builder_id
from automation.builder_parameters import (
    DatasetBuilderParameterParser,
    parse_national_team_goals_parameters,
)
from automation.builders import DatasetBuilder, NationalTeamGoalsDatasetBuilder
from automation.models import FrozenParameters


class DatasetBuilderRegistryError(ValueError):
    """Base error for invalid registry definitions and resolutions."""


class UnknownDatasetBuilderError(DatasetBuilderRegistryError):
    """Raised when a valid builder ID is not present in the registry."""


@dataclass(frozen=True)
class DatasetBuilderDefinition:
    """Immutable association of an ID, factory, and optional parameter parser."""

    builder_id: str
    factory: Callable[[], DatasetBuilder]
    parameter_parser: DatasetBuilderParameterParser | None = None


@dataclass(frozen=True, init=False)
class DatasetBuilderRegistry:
    """Immutable registry of explicit dataset-builder factories."""

    _definitions: tuple[DatasetBuilderDefinition, ...]
    _factories: Mapping[str, Callable[[], DatasetBuilder]]
    _parameter_parsers: Mapping[str, DatasetBuilderParameterParser | None]
    available_builder_ids: tuple[str, ...]

    def __init__(
        self,
        definitions: Iterable[DatasetBuilderDefinition] = (),
    ) -> None:
        copied_definitions = tuple(definitions)
        factories: dict[str, Callable[[], DatasetBuilder]] = {}
        parameter_parsers: dict[str, DatasetBuilderParameterParser | None] = {}

        for index, definition in enumerate(copied_definitions):
            if not isinstance(definition, DatasetBuilderDefinition):
                raise DatasetBuilderRegistryError(
                    "Registry definition at index "
                    f"{index} must be a DatasetBuilderDefinition."
                )

            try:
                builder_id = validate_builder_id(definition.builder_id)
            except ValueError as exc:
                raise DatasetBuilderRegistryError(
                    f"Invalid registered builder ID {definition.builder_id!r}: {exc}"
                ) from exc

            if builder_id in factories:
                raise DatasetBuilderRegistryError(
                    f"Duplicate registered builder ID: {builder_id!r}."
                )
            if not callable(definition.factory):
                raise DatasetBuilderRegistryError(
                    f"Factory for builder {builder_id!r} must be callable."
                )
            if (
                definition.parameter_parser is not None
                and not callable(definition.parameter_parser)
            ):
                raise DatasetBuilderRegistryError(
                    f"Parameter parser for builder {builder_id!r} must be callable."
                )

            _create_validated_builder(builder_id, definition.factory)
            factories[builder_id] = definition.factory
            parameter_parsers[builder_id] = definition.parameter_parser

        ordered_definitions = tuple(
            sorted(copied_definitions, key=lambda item: item.builder_id)
        )
        ordered_factories = {
            definition.builder_id: factories[definition.builder_id]
            for definition in ordered_definitions
        }
        ordered_parameter_parsers = {
            definition.builder_id: parameter_parsers[definition.builder_id]
            for definition in ordered_definitions
        }
        object.__setattr__(self, "_definitions", ordered_definitions)
        object.__setattr__(self, "_factories", MappingProxyType(ordered_factories))
        object.__setattr__(
            self,
            "_parameter_parsers",
            MappingProxyType(ordered_parameter_parsers),
        )
        object.__setattr__(
            self,
            "available_builder_ids",
            tuple(ordered_factories),
        )

    def create(self, builder_id: object) -> DatasetBuilder:
        """Create and validate a new builder instance for ``builder_id``."""
        validated_id = self._resolve_builder_id(builder_id)
        return _create_validated_builder(validated_id, self._factories[validated_id])

    def parse_parameters(
        self,
        builder_id: object,
        parameters: FrozenParameters,
    ) -> object:
        """Parse immutable generic parameters without creating a builder."""
        validated_id = self._resolve_builder_id(builder_id)
        parser = self._parameter_parsers[validated_id]
        if parser is None:
            raise DatasetBuilderRegistryError(
                f"Dataset builder {validated_id!r} has no parameter parser."
            )
        try:
            return parser(parameters)
        except Exception as exc:
            raise DatasetBuilderRegistryError(
                f"Parameter parser for builder {validated_id!r} failed: {exc}"
            ) from exc

    def _resolve_builder_id(self, builder_id: object) -> str:
        try:
            validated_id = validate_builder_id(builder_id)
        except ValueError as exc:
            raise DatasetBuilderRegistryError(
                f"Invalid requested builder ID {builder_id!r}: {exc}"
            ) from exc

        if validated_id not in self._factories:
            available = ", ".join(self.available_builder_ids) or "(none)"
            raise UnknownDatasetBuilderError(
                f"Unknown dataset builder {validated_id!r}. "
                f"Available builder IDs: {available}."
            )
        return validated_id


def create_default_dataset_builder_registry() -> DatasetBuilderRegistry:
    """Create the explicit registry shipped with BarChartStudio."""
    return DatasetBuilderRegistry(
        definitions=(
            DatasetBuilderDefinition(
                builder_id="national_team_goals",
                factory=NationalTeamGoalsDatasetBuilder,
                parameter_parser=parse_national_team_goals_parameters,
            ),
        )
    )


def _create_validated_builder(
    registered_id: str,
    factory: Callable[[], DatasetBuilder],
) -> DatasetBuilder:
    try:
        builder = factory()
    except Exception as exc:
        raise DatasetBuilderRegistryError(
            f"Factory for builder {registered_id!r} failed while creating an instance."
        ) from exc

    if builder is None:
        raise DatasetBuilderRegistryError(
            f"Factory for builder {registered_id!r} returned None."
        )

    builder_id = _required_attribute(builder, "builder_id", registered_id)
    if builder_id != registered_id:
        raise DatasetBuilderRegistryError(
            f"Builder created for {registered_id!r} declares builder_id "
            f"{builder_id!r}."
        )

    builder_version = _required_attribute(builder, "builder_version", registered_id)
    if not isinstance(builder_version, str) or not builder_version.strip():
        raise DatasetBuilderRegistryError(
            f"Builder {registered_id!r} must declare a non-empty string "
            "builder_version."
        )

    build = _required_attribute(builder, "build", registered_id)
    if not callable(build):
        raise DatasetBuilderRegistryError(
            f"Builder {registered_id!r} must provide a callable build method."
        )
    return builder


def _required_attribute(builder: Any, name: str, registered_id: str) -> Any:
    sentinel = object()
    value = getattr(builder, name, sentinel)
    if value is sentinel:
        raise DatasetBuilderRegistryError(
            f"Builder created for {registered_id!r} is incompatible: "
            f"missing {name!r}."
        )
    return value
