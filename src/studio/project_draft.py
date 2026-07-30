import copy
import hashlib
import json
from dataclasses import dataclass


_PREVIEW_IRRELEVANT_CHART_FIELDS = {
    "fps",
    "frame_output_mode",
    "frames_dir",
    "output_file",
    "png_compress_level",
    "steps_per_transition",
}
_AUTO_PREVIEW_EXCLUDED_CHART_FIELDS = {
    *_PREVIEW_IRRELEVANT_CHART_FIELDS,
    "title",
}


@dataclass(frozen=True)
class ProjectDraft:
    project_data: dict
    project_file: str
    preview_settings: dict
    fingerprint: str
    preview_fingerprint: str
    auto_preview_fingerprint: str

    @classmethod
    def create(cls, project_data, project_file, preview_settings=None):
        project_data = copy.deepcopy(project_data)
        project_file = str(project_file).strip()
        preview_settings = copy.deepcopy(preview_settings or {})

        return cls(
            project_data=project_data,
            project_file=project_file,
            preview_settings=preview_settings,
            fingerprint=project_fingerprint(project_data, project_file),
            preview_fingerprint=preview_fingerprint(
                project_data,
                preview_settings,
            ),
            auto_preview_fingerprint=auto_preview_fingerprint(
                project_data,
                preview_settings,
            ),
        )

    def is_dirty(self, saved_fingerprint):
        return self.fingerprint != saved_fingerprint


def project_fingerprint(project_data, project_file=""):
    return _payload_fingerprint({
        "project_data": project_data,
        "project_file": str(project_file).strip(),
    })


def preview_fingerprint(project_data, preview_settings=None):
    chart = _filtered_chart(
        project_data,
        excluded_fields=_PREVIEW_IRRELEVANT_CHART_FIELDS,
    )
    payload = {
        "chart": chart,
        "selection": project_data.get("selection"),
        "categories": project_data.get("categories"),
        "data_source": project_data.get("data_source"),
        "dataset": project_data.get("dataset"),
        "animation": project_data.get("animation"),
        "preview_settings": preview_settings or {},
    }
    return _payload_fingerprint(payload)


def auto_preview_fingerprint(project_data, preview_settings=None):
    chart = _filtered_chart(
        project_data,
        excluded_fields=_AUTO_PREVIEW_EXCLUDED_CHART_FIELDS,
    )
    payload = {
        "chart": chart,
        "selection": project_data.get("selection"),
        "categories": project_data.get("categories"),
        "preview_settings": preview_settings or {},
    }
    return _payload_fingerprint(payload)


def _filtered_chart(project_data, *, excluded_fields):
    chart = project_data.get("chart")
    if not isinstance(chart, dict):
        return chart

    return {
        key: value
        for key, value in chart.items()
        if key not in excluded_fields
    }


def _payload_fingerprint(payload):
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
