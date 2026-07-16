import json
import os
from pathlib import Path
from time import sleep
from uuid import uuid4


ATOMIC_REPLACE_ATTEMPTS = 8
ATOMIC_REPLACE_INITIAL_DELAY = 0.01
ATOMIC_REPLACE_MAX_DELAY = 0.2


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

        _replace_with_retry(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    return path


def _replace_with_retry(source, destination):
    delay = ATOMIC_REPLACE_INITIAL_DELAY

    for attempt in range(ATOMIC_REPLACE_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == ATOMIC_REPLACE_ATTEMPTS - 1:
                raise

            sleep(delay)
            delay = min(delay * 2, ATOMIC_REPLACE_MAX_DELAY)
