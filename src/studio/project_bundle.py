import copy
import hashlib
import io
import json
import os
import re
import shutil
import stat
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from uuid import uuid4

from config.project_file_loader import load_project_file
from config.project_schema import migrate_project_data
from importers.data_source_loader import DataSourceLoader
from studio.project_storage import atomic_write_json
from validators.dataset_validator import DatasetValidator


BUNDLE_SCHEMA_VERSION = 1
MANIFEST_PATH = "manifest.json"
PROJECT_PATH = "project.json"
MAX_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_BUNDLE_FILES = 2_000
MAX_COMPRESSION_RATIO = 1_000
WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


class ProjectBundleError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectBundleExport:
    data: bytes
    filename: str
    file_count: int
    uncompressed_size: int


@dataclass(frozen=True)
class ProjectBundleImport:
    project_path: str
    asset_directory: str
    file_count: int
    uncompressed_size: int


@dataclass(frozen=True)
class _PathReference:
    container: dict
    key: str
    bucket: str


def build_project_bundle(project_data, *, root_dir):
    root_path = Path(root_dir).resolve()
    migrated = migrate_project_data(project_data).data
    bundled_project = copy.deepcopy(migrated)
    source_to_archive = {}
    archive_payloads = {}

    for reference in _path_references(bundled_project):
        raw_path = reference.container.get(reference.key)
        if not raw_path:
            continue

        source_path = _resolve_source_path(raw_path, root_path)
        if not source_path.is_file():
            raise ProjectBundleError(f"Referenced file was not found: {source_path}")

        resolved_source = str(source_path.resolve()).casefold()
        archive_path = source_to_archive.get(resolved_source)
        if archive_path is None:
            payload = source_path.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            archive_path = _archive_asset_path(
                reference.bucket,
                source_path.name,
                digest,
                archive_payloads,
            )
            archive_payloads[archive_path] = payload
            source_to_archive[resolved_source] = archive_path

        reference.container[reference.key] = archive_path

    chart = bundled_project.setdefault("chart", {})
    chart["output_file"] = "output/video.mp4"
    chart["frames_dir"] = "output/frames"
    project_bytes = _json_bytes(bundled_project)
    archive_payloads[PROJECT_PATH] = project_bytes
    if len(archive_payloads) + 1 > MAX_BUNDLE_FILES:
        raise ProjectBundleError("Project references too many files for one bundle.")
    payload_size = sum(len(payload) for payload in archive_payloads.values())
    if payload_size > MAX_BUNDLE_BYTES:
        raise ProjectBundleError("Bundle exceeds the 512 MB size limit.")
    project_name = _safe_slug(bundled_project.get("name") or "project")
    manifest = {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "project_name": project_name,
        "project_file": PROJECT_PATH,
        "files": [
            {
                "path": path,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for path, payload in sorted(archive_payloads.items())
        ],
    }
    manifest_bytes = _json_bytes(manifest)
    output = io.BytesIO()

    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        _write_zip_entry(archive, MANIFEST_PATH, manifest_bytes)
        for path, payload in sorted(archive_payloads.items()):
            _write_zip_entry(archive, path, payload)

    bundle_data = output.getvalue()
    uncompressed_size = len(manifest_bytes) + sum(
        len(payload) for payload in archive_payloads.values()
    )
    if len(bundle_data) > MAX_BUNDLE_BYTES or uncompressed_size > MAX_BUNDLE_BYTES:
        raise ProjectBundleError("Bundle exceeds the 512 MB size limit.")
    return ProjectBundleExport(
        data=bundle_data,
        filename=f"{project_name}.barchart.zip",
        file_count=len(archive_payloads) + 1,
        uncompressed_size=uncompressed_size,
    )


def import_project_bundle(bundle, *, root_dir):
    root_path = Path(root_dir).resolve()
    source = _bundle_source(bundle)
    import_root = root_path / "projects" / "imported"
    staging_directory = import_root / f".bundle.{uuid4().hex}.tmp"
    if source[0] == "directory" and staging_directory.is_relative_to(source[1]):
        raise ProjectBundleError(
            "Bundle source directory cannot contain the import staging area."
        )
    asset_directory = None
    project_path = None

    try:
        staging_directory.mkdir(parents=True, exist_ok=False)
        _materialize_bundle_source(source, staging_directory)
        manifest, records, total_size, file_count = _validate_staged_bundle(
            staging_directory
        )
        project_file = manifest.get("project_file")
        if project_file != PROJECT_PATH or project_file not in records:
            raise ProjectBundleError("Bundle manifest must reference project.json.")

        staging_project_path = staging_directory / PROJECT_PATH
        project_data = _read_staged_project_data(staging_project_path)
        preset = load_project_file(staging_project_path)
        _validate_staged_project_dataset(
            preset,
            staging_directory=staging_directory,
        )

        slug = _unique_import_slug(
            root_path,
            manifest.get("project_name") or project_data.get("name") or "project",
        )
        asset_directory = import_root / slug
        project_path = root_path / "projects" / f"{slug}.json"
        imported_relative_root = Path("projects") / "imported" / slug
        _rewrite_project_references(
            project_data,
            payload_paths=set(records),
            imported_relative_root=imported_relative_root,
        )

        chart = project_data.setdefault("chart", {})
        chart["output_file"] = f"output/{slug}.mp4"
        chart["frames_dir"] = f"output/{slug}_frames"
        project_data["name"] = slug
        staging_project_path.unlink()
        (staging_directory / MANIFEST_PATH).unlink()
        os.replace(staging_directory, asset_directory)

        try:
            atomic_write_json(project_data, project_path)
            load_project_file(project_path)
        except Exception:
            shutil.rmtree(asset_directory, ignore_errors=True)
            if project_path.exists():
                project_path.unlink()
            raise
    except (OSError, ValueError) as exc:
        if isinstance(exc, ProjectBundleError):
            raise
        raise ProjectBundleError(f"Could not import project bundle: {exc}") from exc
    finally:
        shutil.rmtree(staging_directory, ignore_errors=True)

    return ProjectBundleImport(
        project_path=str(project_path),
        asset_directory=str(asset_directory),
        file_count=file_count,
        uncompressed_size=total_size,
    )


def _bundle_source(bundle):
    if isinstance(bundle, (str, os.PathLike)):
        path = Path(bundle)
        if not path.exists():
            raise ProjectBundleError(f"Bundle path does not exist: {path}")
        if _is_link(path):
            raise ProjectBundleError("Bundle source must not be a symbolic link.")
        if path.is_dir():
            return "directory", path.resolve(strict=True)
        if path.is_file() and path.suffix.lower() == ".zip":
            if path.stat().st_size > MAX_BUNDLE_BYTES:
                raise ProjectBundleError(
                    "Bundle exceeds the 512 MB compressed size limit."
                )
            return "zip_path", path.resolve(strict=True)
        if path.is_file():
            raise ProjectBundleError(
                "Bundle path must reference a .zip file or a directory."
            )
        raise ProjectBundleError(
            "Bundle path must reference a regular .zip file or a directory."
        )

    bundle_bytes = _bundle_bytes(bundle)
    if len(bundle_bytes) > MAX_BUNDLE_BYTES:
        raise ProjectBundleError("Bundle exceeds the 512 MB compressed size limit.")
    return "zip_bytes", bundle_bytes


def _materialize_bundle_source(source, staging_directory):
    source_type, source_value = source
    if source_type == "directory":
        _copy_bundle_directory(source_value, staging_directory)
        return
    _extract_bundle_zip(source_value, staging_directory, from_bytes=(
        source_type == "zip_bytes"
    ))


def _extract_bundle_zip(source, staging_directory, *, from_bytes):
    try:
        archive_source = io.BytesIO(source) if from_bytes else source
        archive = zipfile.ZipFile(archive_source, mode="r")
    except zipfile.BadZipFile as exc:
        raise ProjectBundleError("Uploaded file is not a valid ZIP bundle.") from exc

    with archive:
        file_infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(file_infos) > MAX_BUNDLE_FILES:
            raise ProjectBundleError("Bundle contains too many files.")

        names = [info.filename for info in file_infos]
        if len(names) != len(set(names)) or len(names) != len(
            {name.casefold() for name in names}
        ):
            raise ProjectBundleError("Bundle contains duplicate file names.")

        total_size = 0
        for info in file_infos:
            _validate_zip_info(info)
            total_size += info.file_size
            if total_size > MAX_BUNDLE_BYTES:
                raise ProjectBundleError("Bundle exceeds the 512 MB size limit.")

        for info in file_infos:
            payload = _read_zip_entry(archive, info.filename)
            destination = staging_directory.joinpath(
                *PurePosixPath(info.filename).parts
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)


def _copy_bundle_directory(source_directory, staging_directory):
    file_count = 0
    total_size = 0
    seen_names = set()

    for current_root, directory_names, file_names in os.walk(
        source_directory,
        followlinks=False,
    ):
        current_path = Path(current_root)
        for directory_name in directory_names:
            if _is_link(current_path / directory_name):
                raise ProjectBundleError(
                    "Symbolic links are not allowed in project bundle folders."
                )

        for file_name in file_names:
            source_path = current_path / file_name
            if _is_link(source_path):
                raise ProjectBundleError(
                    "Symbolic links are not allowed in project bundle folders."
                )
            if not source_path.is_file():
                raise ProjectBundleError(
                    "Bundle folder contains an unsupported filesystem entry."
                )

            resolved_source = source_path.resolve(strict=True)
            if not resolved_source.is_relative_to(source_directory):
                raise ProjectBundleError(
                    "Bundle folder contains a path outside its root."
                )
            relative_path = source_path.relative_to(source_directory).as_posix()
            _validate_member_name(relative_path)
            folded_name = relative_path.casefold()
            if folded_name in seen_names:
                raise ProjectBundleError("Bundle contains duplicate file names.")
            seen_names.add(folded_name)

            file_count += 1
            total_size += source_path.stat().st_size
            if file_count > MAX_BUNDLE_FILES:
                raise ProjectBundleError("Bundle contains too many files.")
            if total_size > MAX_BUNDLE_BYTES:
                raise ProjectBundleError("Bundle exceeds the 512 MB size limit.")

            destination = staging_directory.joinpath(
                *PurePosixPath(relative_path).parts
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source_path.open("rb") as source_file, destination.open("xb") as target:
                shutil.copyfileobj(source_file, target)


def _validate_staged_bundle(staging_directory):
    staged_files = tuple(
        path
        for path in staging_directory.rglob("*")
        if path.is_file()
    )
    if len(staged_files) > MAX_BUNDLE_FILES:
        raise ProjectBundleError("Bundle contains too many files.")

    names = [path.relative_to(staging_directory).as_posix() for path in staged_files]
    if len(names) != len(set(names)) or len(names) != len(
        {name.casefold() for name in names}
    ):
        raise ProjectBundleError("Bundle contains duplicate file names.")
    for name in names:
        _validate_member_name(name)

    total_size = sum(path.stat().st_size for path in staged_files)
    if total_size > MAX_BUNDLE_BYTES:
        raise ProjectBundleError("Bundle exceeds the 512 MB size limit.")
    if MANIFEST_PATH not in names:
        raise ProjectBundleError("Bundle manifest.json is missing.")

    manifest_path = staging_directory / MANIFEST_PATH
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
        raise ProjectBundleError(f"Bundle manifest is invalid: {exc}") from exc

    records = _manifest_records(manifest)
    expected_names = {MANIFEST_PATH, *records}
    if set(names) != expected_names:
        raise ProjectBundleError(
            "Bundle file list does not match the signed manifest."
        )

    for path, record in records.items():
        staged_path = staging_directory.joinpath(*PurePosixPath(path).parts)
        expected_size = record.get("size")
        if staged_path.stat().st_size != expected_size:
            raise ProjectBundleError(f"Size check failed for {path}.")
        if _sha256_file(staged_path) != record.get("sha256"):
            raise ProjectBundleError(f"Checksum failed for {path}.")

    return manifest, records, total_size, len(staged_files)


def _manifest_records(manifest):
    if not isinstance(manifest, dict):
        raise ProjectBundleError("Bundle manifest must be a JSON object.")
    if manifest.get("bundle_schema_version") != BUNDLE_SCHEMA_VERSION:
        raise ProjectBundleError("Unsupported project bundle schema version.")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ProjectBundleError("Bundle manifest file list is missing.")

    records = {}
    for record in files:
        if not isinstance(record, dict):
            raise ProjectBundleError("Bundle manifest contains an invalid file record.")
        path = record.get("path")
        _validate_member_name(path)
        if path == MANIFEST_PATH or path.casefold() in {
            existing.casefold() for existing in records
        }:
            raise ProjectBundleError("Bundle manifest contains duplicate file records.")
        if not isinstance(record.get("size"), int) or record["size"] < 0:
            raise ProjectBundleError(f"Bundle manifest has an invalid size for {path}.")
        digest = record.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ProjectBundleError(f"Bundle manifest has an invalid checksum for {path}.")
        records[path] = record

    return records


def _validate_zip_info(info):
    _validate_member_name(info.filename)
    if info.flag_bits & 0x1:
        raise ProjectBundleError("Encrypted ZIP entries are not supported.")
    file_mode = info.external_attr >> 16
    if stat.S_ISLNK(file_mode):
        raise ProjectBundleError("Symbolic links are not allowed in project bundles.")
    if (
        info.file_size > 1024 * 1024
        and info.compress_size > 0
        and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
    ):
        raise ProjectBundleError("Bundle contains a suspicious compression ratio.")


def _validate_member_name(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ProjectBundleError("Bundle contains an unsafe file path.")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ProjectBundleError(f"Bundle contains an unsafe file path: {name}")
    for part in path.parts:
        if part.rstrip(" .") != part:
            raise ProjectBundleError(f"Bundle contains an unsafe file path: {name}")
        if part.split(".", 1)[0].casefold() in WINDOWS_RESERVED_NAMES:
            raise ProjectBundleError(f"Bundle contains an unsafe file path: {name}")


def _read_zip_entry(archive, path):
    try:
        return archive.read(path)
    except (KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ProjectBundleError(f"Bundle entry is corrupted: {path}") from exc


def _path_references(project_data):
    data_source = project_data.get("data_source")
    if isinstance(data_source, dict):
        source_type = data_source.get("source_type", "csv")
        if source_type == "sqlite":
            yield _PathReference(data_source, "sqlite_database_path", "data")
        else:
            yield _PathReference(data_source, "csv_path", "data")

    chart = project_data.get("chart")
    if isinstance(chart, dict):
        yield _PathReference(chart, "background_image_path", "assets/backgrounds")
        yield _PathReference(chart, "bar_texture_custom_image", "assets/textures")

    categories = project_data.get("categories")
    if isinstance(categories, dict):
        for style in categories.values():
            if not isinstance(style, dict):
                continue
            yield _PathReference(style, "logo", "assets/logos/primary")
            yield _PathReference(style, "secondary_logo", "assets/logos/secondary")


def _read_staged_project_data(project_path):
    try:
        project_data = json.loads(project_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
        raise ProjectBundleError(f"Bundled project JSON is invalid: {exc}") from exc
    return migrate_project_data(project_data).data


def _validate_staged_project_dataset(
    preset,
    *,
    staging_directory,
):
    data_source_config = _staged_data_source_config(
        preset.data_source_config,
        staging_directory=staging_directory,
    )
    try:
        dataframe = DataSourceLoader(data_source_config).load()
        DatasetValidator(config=preset.dataset_config).validate(dataframe)
    except (OSError, ValueError) as exc:
        raise ProjectBundleError(
            f"Bundled dataset is invalid: {exc}"
        ) from exc


def _staged_data_source_config(
    config,
    *,
    staging_directory,
):
    if config.source_type == "csv":
        field_name = "csv_path"
    elif config.source_type == "sqlite":
        field_name = "sqlite_database_path"
    else:
        raise ProjectBundleError(
            f"Bundled project uses unsupported data source type: {config.source_type}"
        )

    configured_value = getattr(config, field_name)
    _validate_member_name(configured_value)
    archive_path = PurePosixPath(configured_value)
    staged_path = staging_directory.joinpath(*archive_path.parts).resolve()
    staging_root = staging_directory.resolve()
    if not staged_path.is_relative_to(staging_root) or not staged_path.is_file():
        raise ProjectBundleError(
            "Bundled project dataset was not found inside the staged bundle."
        )

    return replace(config, **{field_name: str(staged_path)})


def _rewrite_project_references(
    project_data,
    *,
    payload_paths,
    imported_relative_root,
):
    for reference in _path_references(project_data):
        archive_path = reference.container.get(reference.key)
        if not archive_path:
            continue
        _validate_member_name(archive_path)
        if archive_path == PROJECT_PATH or archive_path not in payload_paths:
            raise ProjectBundleError(
                f"Project references a file missing from the bundle: {archive_path}"
            )
        reference.container[reference.key] = (
            imported_relative_root / Path(PurePosixPath(archive_path))
        ).as_posix()


def _is_link(path):
    return path.is_symlink() or (
        hasattr(path, "is_junction") and path.is_junction()
    )


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_source_path(path, root_path):
    source_path = Path(str(path)).expanduser()
    return source_path.resolve() if source_path.is_absolute() else (root_path / source_path).resolve()


def _archive_asset_path(bucket, filename, digest, existing):
    safe_name = _safe_filename(filename)
    candidate = f"{bucket}/{digest[:12]}_{safe_name}"
    suffix = 2
    while candidate in existing:
        candidate = f"{bucket}/{digest[:12]}_{suffix}_{safe_name}"
        suffix += 1
    return candidate


def _safe_filename(filename):
    path = Path(str(filename))
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._") or "asset"
    suffix = re.sub(r"[^A-Za-z0-9.]+", "", path.suffix.lower())
    return f"{stem[:80]}{suffix[:16]}"


def _safe_slug(value):
    slug = re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")
    slug = slug[:80] or "project"
    if slug in WINDOWS_RESERVED_NAMES:
        slug = f"project_{slug}"
    return slug


def _unique_import_slug(root_path, value):
    base = _safe_slug(value)
    candidate = base
    index = 2
    while (
        (root_path / "projects" / f"{candidate}.json").exists()
        or (root_path / "projects" / "imported" / candidate).exists()
    ):
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def _bundle_bytes(bundle):
    if isinstance(bundle, bytes):
        return bundle
    if isinstance(bundle, bytearray):
        return bytes(bundle)
    if hasattr(bundle, "read"):
        payload = bundle.read()
        return payload if isinstance(payload, bytes) else bytes(payload)
    raise ProjectBundleError("Bundle must be bytes or a readable binary file.")


def _json_bytes(data):
    return (
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _write_zip_entry(archive, path, payload):
    info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, payload, compresslevel=6)
