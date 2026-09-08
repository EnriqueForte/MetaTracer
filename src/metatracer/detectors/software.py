"""SoftwareVersionDetector (TASK-02 subtask 2.4).

A finding requires a software name *and* a numeric version (``x.y`` or an
explicit build): ``Apache FOP 2.4``, ``wkhtmltopdf 0.12.5``,
``macOS Version 14.5 (Build 23F79)``. A producer with no version
(``Microsoft Word``, ``Quartz PDFContext``, ``Canva``) stays in raw metadata
— no ``info`` findings "just in case".

Scanned fields: Producer, Creator, CreatorTool, Software, Application and
their XMP equivalents (matched by local name, so ``xmp:CreatorTool`` and
``pdf:Producer`` count), plus TASK-09 recon headers / HTML generator
(``server``, ``x-powered-by``, ``generator``, …). ``dc:creator`` is excluded:
it is a person (the XMP equivalent of Author), not software. Version-only
headers such as ``x-aspnet-version: 4.0.30319`` do not require a name token
in front of the number — the header name is the software identity.
"""

import re
from collections.abc import Sequence

from metatracer.db.models import Confidence, FindingType, RawMetadataItem
from metatracer.detectors.base import FindingDraft, collapse_whitespace, normalize_text, snippet

# Local key names (part after the last ":") that carry the producing software.
_SOFTWARE_KEYS = frozenset(
    {
        "producer",
        "creator",
        "creatortool",
        "software",
        "application",
        "processingsoftware",
        "server",
        "x-powered-by",
        "x-generator",
        "generator",
        "x-runtime",
        "x-application-version",
    }
)
# Headers whose value is often just the version number (the key names the stack).
_VERSION_ONLY_KEYS = frozenset({"x-aspnet-version", "x-aspnetmvc-version", "x-version"})
# Person fields that share a local name with software fields.
_PERSON_KEYS = frozenset({"dc:creator"})

# x.y minimum (optionally v-prefixed, optionally longer: 0.12.5, 18.2.1-beta).
_VERSION_RE = re.compile(r"\bv?\d+(?:\.\d+)+(?:[-.][0-9A-Za-z]+)*")
# Explicit build token: "Build 23F79", "(Build 19045.4291)".
_BUILD_RE = re.compile(r"\bbuild[\s(]*[0-9A-Za-z.\-]+", re.IGNORECASE)
_NAME_RE = re.compile(r"[A-Za-z]")


class SoftwareVersionDetector:
    """Detects software name + version strings in producer/creator fields."""

    finding_type = FindingType.software_version

    def detect(self, items: Sequence[RawMetadataItem]) -> list[FindingDraft]:
        drafts: list[FindingDraft] = []
        for item in items:
            if item.key in _PERSON_KEYS:
                continue
            local = item.key.rpartition(":")[2].lower()
            version_only = local in _VERSION_ONLY_KEYS
            if local not in _SOFTWARE_KEYS and not version_only:
                continue
            text = collapse_whitespace(normalize_text(item.value))
            if not text:
                continue
            match = _VERSION_RE.search(text) or _BUILD_RE.search(text)
            if match is None:
                continue  # no version or build: not a finding, stays raw metadata
            if not version_only and not _NAME_RE.search(text[: match.start()]):
                continue  # a bare version number names no software
            drafts.append(
                FindingDraft(
                    finding_type=FindingType.software_version,
                    field_source=f"{item.namespace}:{item.key}",
                    evidence_snippet=snippet(text),
                    confidence=Confidence.high,
                )
            )
        return drafts
