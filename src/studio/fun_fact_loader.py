import json
import re
from pathlib import Path

from core.fun_fact_scheduler import FunFactScheduler
from models.fun_fact import FunFact, FunFactCollection
from studio.image_validation import ImageValidationError, validate_image_file
from studio.package_paths import ProjectPathError, resolve_project_path


FUN_FACT_FILE_VERSION = 1
_ROOT_FIELDS = {"version", "fun_facts"}
_FACT_FIELDS = {
    "id",
    "start",
    "end",
    "headline",
    "body",
    "image",
    "layout",
    "accent_color",
    "image_fit",
    "credit",
}
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class FunFactFileError(ValueError):
    pass


def load_fun_fact_scheduler(config, timeline, *, project_root):
    if not config.enabled:
        return None
    collection = load_fun_fact_collection(config.source, project_root=project_root)
    return FunFactScheduler(
        collection,
        timeline,
        fade_in=config.fade_in,
        fade_out=config.fade_out,
    )


def load_fun_fact_collection(source, *, project_root, validate_images=True):
    if not isinstance(source, str) or not source.strip():
        raise FunFactFileError(
            "fun_facts.source must be a non-empty path when fun facts are enabled."
        )
    try:
        source_path = resolve_project_path(
            source,
            project_root=project_root,
            required=True,
            field_name="fun_facts.source",
        )
    except ProjectPathError as exc:
        raise FunFactFileError(str(exc)) from exc
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FunFactFileError(
            f"Invalid JSON in fun fact file '{source_path}': {exc.msg}."
        ) from exc
    except OSError as exc:
        raise FunFactFileError(
            f"Could not read fun fact file for fun_facts.source: {source_path}"
        ) from exc
    return parse_fun_fact_data(
        data,
        source_path=source_path,
        project_root=project_root,
        validate_images=validate_images,
    )


def parse_fun_fact_data(
    data,
    *,
    source_path="fun_facts.json",
    project_root,
    validate_images=True,
):
    if not isinstance(data, dict):
        raise FunFactFileError("Fun fact file must contain a JSON object.")
    _reject_unknown(data, _ROOT_FIELDS, "fun fact file")
    version = data.get("version")
    if version != FUN_FACT_FILE_VERSION or isinstance(version, bool):
        raise FunFactFileError(
            f"Fun fact file field 'version' must be {FUN_FACT_FILE_VERSION}."
        )
    items = data.get("fun_facts")
    if not isinstance(items, list):
        raise FunFactFileError("Fun fact file field 'fun_facts' must be a list.")

    facts = []
    ids = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise FunFactFileError(f"Fun fact at index {index} must be an object.")
        fact_id = item.get("id")
        context = f"fun fact at index {index}"
        if isinstance(fact_id, str) and fact_id.strip():
            context = f"fun fact '{fact_id.strip()}'"
        _reject_unknown(item, _FACT_FIELDS, context)
        fact = _parse_fact(
            item,
            index=index,
            project_root=project_root,
            validate_images=validate_images,
        )
        if fact.id in ids:
            raise FunFactFileError(f"Duplicate fun fact id '{fact.id}'.")
        ids.add(fact.id)
        facts.append(fact)
    return FunFactCollection(
        version=version,
        facts=tuple(facts),
        source_path=str(Path(source_path)),
    )


def _parse_fact(item, *, index, project_root, validate_images):
    fact_id = _required_text(item, "id", f"fun fact at index {index}")
    context = f"Fun fact '{fact_id}'"
    start = _required_text(item, "start", context)
    end = _required_text(item, "end", context)
    headline = _required_text(item, "headline", context)
    body = _optional_text(item, "body", context)
    credit = _optional_text(item, "credit", context)
    layout = item.get("layout", "right_panel")
    if layout != "right_panel":
        raise FunFactFileError(
            f"{context} field 'layout' must be 'right_panel'."
        )
    image_fit = item.get("image_fit", "cover")
    if image_fit not in ("cover", "contain"):
        raise FunFactFileError(
            f"{context} field 'image_fit' must be 'cover' or 'contain'."
        )
    accent_color = item.get("accent_color")
    if accent_color is not None:
        if not isinstance(accent_color, str) or not _HEX_COLOR.fullmatch(accent_color):
            raise FunFactFileError(
                f"{context} field 'accent_color' must be null or #RRGGBB."
            )

    image_value = item.get("image")
    image_path = None
    if image_value is not None:
        if not isinstance(image_value, str) or not image_value.strip():
            raise FunFactFileError(
                f"{context} field 'image' must be null or a non-empty path."
            )
        try:
            resolved = resolve_project_path(
                image_value.strip(),
                project_root=project_root,
                required=True,
                field_name=f"fun fact '{fact_id}' field 'image'",
            )
        except ProjectPathError as exc:
            raise FunFactFileError(str(exc)) from exc
        if validate_images:
            try:
                info = validate_image_file(
                    resolved,
                    field_name=f"fun fact '{fact_id}' field 'image'",
                    original_value=image_value,
                )
            except ImageValidationError as exc:
                raise FunFactFileError(str(exc)) from exc
            if (info.format or "").upper() not in {"PNG", "JPEG", "WEBP"}:
                raise FunFactFileError(
                    f"{context} field 'image' must be PNG, JPEG, or WEBP: {resolved}"
                )
        image_path = str(resolved)

    return FunFact(
        id=fact_id,
        start=start,
        end=end,
        headline=headline,
        body=body,
        image_path=image_path,
        layout=layout,
        accent_color=accent_color,
        image_fit=image_fit,
        credit=credit,
    )


def _required_text(data, field_name, context):
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise FunFactFileError(
            f"{context} field '{field_name}' must be a non-empty string."
        )
    return value.strip()


def _optional_text(data, field_name, context):
    value = data.get(field_name, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise FunFactFileError(f"{context} field '{field_name}' must be a string.")
    return value.strip()


def _reject_unknown(data, allowed, context):
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise FunFactFileError(
            f"Unknown field(s) in {context}: {', '.join(unknown)}."
        )
