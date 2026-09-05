import os
from pathlib import Path
from uuid import uuid4


class RenderOutputPromotionError(OSError):
    def __init__(
        self,
        partial_path,
        final_path,
        cause,
        *,
        partial_preserved=True,
    ):
        self.partial_path = Path(partial_path)
        self.final_path = Path(final_path)
        self.cause = cause
        self.partial_preserved = bool(partial_preserved)
        partial_detail = (
            f"Temporary file preserved at: {self.partial_path}. "
            if self.partial_preserved
            else f"Temporary file was not found at: {self.partial_path}. "
        )
        super().__init__(
            "Render completed but final file promotion failed. "
            f"{partial_detail}"
            f"Final destination: {self.final_path}. "
            f"Original error: {type(cause).__name__}: {cause}"
        )


def temporary_render_output_path(final_path):
    """Return a short, unique staging path beside the final render output."""
    final_path = Path(final_path)
    token = uuid4().hex[:16]
    return final_path.with_name(f".render.{token}.partial{final_path.suffix}")


def promote_render_output(partial_path, final_path):
    """Atomically promote a completed render while preserving it on failure."""
    partial_path = Path(partial_path)
    final_path = Path(final_path)
    if partial_path.parent != final_path.parent:
        raise ValueError("Render partial and final output must share a directory.")

    filesystem_partial = _filesystem_path(partial_path)
    filesystem_final = _filesystem_path(final_path)
    if not os.path.isfile(filesystem_partial):
        cause = FileNotFoundError(
            f"Completed render temporary file does not exist: {partial_path}"
        )
        raise RenderOutputPromotionError(
            partial_path,
            final_path,
            cause,
            partial_preserved=False,
        )

    try:
        os.replace(filesystem_partial, filesystem_final)
    except OSError as exc:
        raise RenderOutputPromotionError(
            partial_path,
            final_path,
            exc,
            partial_preserved=os.path.isfile(filesystem_partial),
        ) from exc

    return final_path


def _filesystem_path(path):
    """Use Win32 extended syntax internally; leave other platforms untouched."""
    path_string = os.fspath(path)
    if os.name != "nt":
        return path_string

    absolute_path = os.path.abspath(path_string)
    if absolute_path.startswith("\\\\?\\"):
        return absolute_path
    if absolute_path.startswith("\\\\"):
        return f"\\\\?\\UNC\\{absolute_path[2:]}"
    return f"\\\\?\\{absolute_path}"
