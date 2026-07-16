import json
import os
from pathlib import Path
from uuid import uuid4


def atomic_write_json(data, path):
    path = Path(path)

    if path.suffix.lower() != ".json":
        raise ValueError("Project file must use the .json extension.")

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    serialized = json.dumps(data, indent=2) + "\n"

    try:
        with temporary_path.open("x", encoding="utf-8", newline="\n") as file:
            file.write(serialized)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    return path
