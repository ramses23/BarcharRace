import copy
import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectDraft:
    project_data: dict
    project_file: str
    preview_settings: dict
    fingerprint: str

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
        )

    def is_dirty(self, saved_fingerprint):
        return self.fingerprint != saved_fingerprint


def project_fingerprint(project_data, project_file=""):
    payload = {
        "project_data": project_data,
        "project_file": str(project_file).strip(),
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
