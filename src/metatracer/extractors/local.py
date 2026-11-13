"""Local-folder ingest (TASK-51): walk allowlisted files without a socket.

The HTTP crawler is not used. HTML on disk is extracted as HTML metadata and
its links are not followed. Symlinks are not followed. A generic ZIP is not
an Office package (the sniff already refuses it without an Office extension).
Directory walks only consider allowlisted extensions; other names are ignored
so a dump folder does not flood the run with skipped junk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from metatracer.db.models import ExtractionStatus, SkipReason
from metatracer.extractors.targets import FILE_EXTENSIONS

LOCAL_EXTENSIONS = FILE_EXTENSIONS + (".html", ".htm")
LOCAL_SOURCE = "local"


@dataclass(frozen=True, slots=True)
class LocalEntry:
    """One path considered for local ingest (file or a failed root)."""

    path: Path
    uri: str
    status: ExtractionStatus | None = None
    skip_reason: SkipReason | None = None
    error_message: str | None = None


def file_uri(path: Path) -> str:
    """Stable ``file:`` URI for an absolute path; does not read the file."""
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = candidate.absolute()
    return candidate.as_uri()


def file_uris_for(paths: list[str]) -> list[str]:
    """``file:`` URIs for operator-supplied roots (existence not required)."""
    return [file_uri(Path(raw)) for raw in paths]


def has_local_extension(path: Path) -> bool:
    return path.suffix.lower() in LOCAL_EXTENSIONS


def list_local_entries(roots: list[str]) -> list[LocalEntry]:
    """Walk directories / list files. Does not follow symlinks. No unpack."""
    seen: set[str] = set()
    entries: list[LocalEntry] = []
    for raw in roots:
        root = Path(raw).expanduser()
        if not root.is_absolute():
            root = root.absolute()
        entries.extend(_walk_root(root, seen, explicit=True))
    return entries


def _walk_root(root: Path, seen: set[str], *, explicit: bool) -> list[LocalEntry]:
    uri = file_uri(root)
    if not root.exists():
        if not explicit:
            return []
        return [
            LocalEntry(
                path=root,
                uri=uri,
                status=ExtractionStatus.failed,
                error_message="path not found",
            )
        ]
    if root.is_symlink():
        if not explicit:
            return []
        return [
            LocalEntry(
                path=root,
                uri=uri,
                status=ExtractionStatus.skipped,
                skip_reason=SkipReason.unsupported_type,
                error_message="symlink not followed",
            )
        ]
    if root.is_file():
        return [_file_entry(root, seen, explicit=explicit)]
    if not root.is_dir():
        if not explicit:
            return []
        return [
            LocalEntry(
                path=root,
                uri=uri,
                status=ExtractionStatus.failed,
                error_message="not a file or directory",
            )
        ]
    found: list[LocalEntry] = []
    try:
        children = sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError as exc:
        return [
            LocalEntry(
                path=root,
                uri=uri,
                status=ExtractionStatus.failed,
                error_message=f"unreadable directory: {type(exc).__name__}",
            )
        ]
    for child in children:
        if child.is_symlink():
            continue
        if child.is_dir():
            found.extend(_walk_root(child, seen, explicit=False))
            continue
        if child.is_file() and has_local_extension(child):
            found.append(_file_entry(child, seen, explicit=False))
    return found


def _file_entry(path: Path, seen: set[str], *, explicit: bool) -> LocalEntry:  # noqa: ARG001
    key = str(path)
    uri = file_uri(path)
    if key in seen:
        return LocalEntry(
            path=path,
            uri=uri,
            status=ExtractionStatus.skipped,
            skip_reason=SkipReason.duplicate_hash,
            error_message="path already queued in this run",
        )
    seen.add(key)
    if not has_local_extension(path):
        return LocalEntry(
            path=path,
            uri=uri,
            status=ExtractionStatus.skipped,
            skip_reason=SkipReason.unsupported_type,
            error_message="extension is not on the local ingest allowlist",
        )
    return LocalEntry(path=path, uri=uri)
