import copy
from dataclasses import dataclass


CURRENT_PROJECT_SCHEMA_VERSION = 1


class ProjectSchemaError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectMigration:
    data: dict
    original_version: int
    current_version: int
    applied_migrations: tuple[str, ...]

    @property
    def migrated(self):
        return bool(self.applied_migrations)


def migrate_project_data(project_data):
    if not isinstance(project_data, dict):
        raise ProjectSchemaError("Project file must contain a JSON object.")

    migrated_data = copy.deepcopy(project_data)
    original_version = _schema_version(migrated_data)
    version = original_version
    applied_migrations = []

    if version > CURRENT_PROJECT_SCHEMA_VERSION:
        raise ProjectSchemaError(
            "Project schema version "
            f"{version} is newer than supported version "
            f"{CURRENT_PROJECT_SCHEMA_VERSION}."
        )

    while version < CURRENT_PROJECT_SCHEMA_VERSION:
        migration = _MIGRATIONS.get(version)
        if migration is None:
            raise ProjectSchemaError(
                f"No migration is available from project schema version {version}."
            )

        migrated_data = migration(migrated_data)
        applied_migrations.append(f"{version}_to_{version + 1}")
        version += 1

    migrated_data["schema_version"] = CURRENT_PROJECT_SCHEMA_VERSION
    return ProjectMigration(
        data=migrated_data,
        original_version=original_version,
        current_version=CURRENT_PROJECT_SCHEMA_VERSION,
        applied_migrations=tuple(applied_migrations),
    )


def _schema_version(project_data):
    version = project_data.get("schema_version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise ProjectSchemaError(
            "Project field 'schema_version' must be a non-negative integer."
        )
    return version


def _migrate_v0_to_v1(project_data):
    migrated = copy.deepcopy(project_data)
    chart = migrated.get("chart")

    if chart is None:
        chart = {}
        migrated["chart"] = chart
    elif not isinstance(chart, dict):
        raise ProjectSchemaError("Project section 'chart' must be an object.")

    _move_legacy_section(migrated, chart, "animation")
    _move_legacy_section(migrated, chart, "selection")
    legacy_logo_positions = {
        "outside": "outside_left",
        "inside": "inside_left",
    }
    for field in ("bar_logo_position", "bar_secondary_logo_position"):
        if chart.get(field) in legacy_logo_positions:
            chart[field] = legacy_logo_positions[chart[field]]

    migrated["schema_version"] = 1
    return migrated


def _move_legacy_section(project_data, chart, section_name):
    legacy_section = chart.pop(section_name, None)
    if legacy_section is None:
        return
    if not isinstance(legacy_section, dict):
        raise ProjectSchemaError(
            f"Legacy chart.{section_name} must be an object."
        )

    current_section = project_data.get(section_name, {})
    if not isinstance(current_section, dict):
        raise ProjectSchemaError(
            f"Project section '{section_name}' must be an object."
        )

    project_data[section_name] = {
        **legacy_section,
        **current_section,
    }


_MIGRATIONS = {
    0: _migrate_v0_to_v1,
}
