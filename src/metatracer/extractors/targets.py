"""Target classification (TASK-01 subtask 1.1.1).

Every host is validated against the confirmed scope BEFORE classification —
an out-of-scope target is rejected here and never reaches the network. Bare
domains get an ``https://`` prefix and are crawled as level-0 pages.
"""

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from metatracer.core.exceptions import SecurityViolationError
from metatracer.core.logging import sanitize_for_log
from metatracer.core.safety.scope import ScopeValidator

# OOXML and ODF. Legacy OLE (.doc/.xls/.ppt) is not in this list: the
# extractor only reads ZIP packages.
OFFICE_EXTENSIONS = (
    ".docx",
    ".xlsx",
    ".pptx",
    ".docm",
    ".xlsm",
    ".pptm",
    ".odt",
    ".ods",
    ".odp",
)
# Document extensions the crawler and resolver recognize (subtask 1.1.2).
DOCUMENT_EXTENSIONS = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".tiff",
    ".tif",
    ".webp",
    ".gif",
    ".svg",
) + OFFICE_EXTENSIONS
# First-class JS assets (TASK-09): downloaded like documents, not crawled as pages.
SCRIPT_EXTENSIONS = (".js",)
FILE_EXTENSIONS = DOCUMENT_EXTENSIONS + SCRIPT_EXTENSIONS


class TargetKind(StrEnum):
    """What a user-supplied target turns into."""

    file = "file"  # direct document URL: download, no crawl
    page = "page"  # HTML page: depth-1 crawl for document links


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    kind: TargetKind
    url: str
    original: str


class TargetResolver:
    """Validates and classifies raw target strings against the scope."""

    def __init__(self, scope: ScopeValidator) -> None:
        self._scope = scope

    def resolve(self, raw: str) -> ResolvedTarget:
        """Classify one target; raise on empty input, bad scheme or off-scope host.

        Raises:
            ValueError: the target is empty or whitespace.
            SecurityViolationError: the URL scheme is not http/https.
            OutOfScopeError: the host is not covered by the confirmed scope.
        """
        candidate = raw.strip()
        if not candidate:
            raise ValueError("empty target")
        if "://" not in candidate:
            candidate = f"https://{candidate}"
        parsed = urlsplit(candidate)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            raise SecurityViolationError(
                f"unsupported URL scheme blocked: {sanitize_for_log(parsed.scheme)}"
            )
        self._scope.validate(candidate)  # host check BEFORE classifying
        url = candidate if parsed.path else candidate + "/"
        kind = (
            TargetKind.file if parsed.path.lower().endswith(FILE_EXTENSIONS) else TargetKind.page
        )
        return ResolvedTarget(kind=kind, url=url, original=raw)
