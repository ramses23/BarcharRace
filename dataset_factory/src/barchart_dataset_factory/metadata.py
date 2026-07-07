import json
from dataclasses import asdict, dataclass
from datetime import date


VALID_CLASSIFICATIONS = {"A", "B", "C"}


@dataclass(frozen=True)
class DatasetMetadata:
    dataset_key: str
    title: str
    classification: str
    source_name: str
    source_url: str
    metric: str
    unit: str
    downloaded_at: str
    methodology_note: str
    year_column: str = "year"
    name_column: str = "country"
    value_column: str = "value"


def metadata_template(dataset_idea):
    return DatasetMetadata(
        dataset_key=dataset_idea.key,
        title=dataset_idea.title,
        classification=dataset_idea.classification,
        source_name=dataset_idea.likely_source,
        source_url="",
        metric=dataset_idea.metric,
        unit="",
        downloaded_at=date.today().isoformat(),
        methodology_note=dataset_idea.notes,
    )


def validate_metadata(metadata):
    errors = []

    if metadata.classification not in VALID_CLASSIFICATIONS:
        errors.append("classification must be A, B, or C.")

    required_fields = (
        "dataset_key",
        "title",
        "source_name",
        "metric",
        "downloaded_at",
        "methodology_note",
        "year_column",
        "name_column",
        "value_column",
    )

    for field_name in required_fields:
        value = getattr(metadata, field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field_name} must be a non-empty string.")

    return errors


def metadata_to_json(metadata):
    return json.dumps(asdict(metadata), indent=2, ensure_ascii=False)
