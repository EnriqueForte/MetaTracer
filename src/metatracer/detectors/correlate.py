"""Deterministic shared-value observations (Fase 3).

A shared value is not a shared identity. This module only decides which
already-stored fields are worth grouping. It does not create findings and
does not assign severity. ``internal_endpoint`` findings are grouped under
that correlation kind. ``cloud_storage`` stays a finding, not a correlation kind.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from metatracer.db.models import CorrelationKind, Finding, FindingType, RawMetadataItem

_MAX_VALUE_CHARS = 200
_WHITESPACE = re.compile(r"\s+")

_FINDING_KINDS = {
    FindingType.email: CorrelationKind.email,
    FindingType.gps: CorrelationKind.gps_point,
    FindingType.software_version: CorrelationKind.software_version,
    FindingType.internal_endpoint: CorrelationKind.internal_endpoint,
}

# Local names only. ``CreatorTool`` is software, not an author (ADR-0009).
_AUTHOR_KEYS = frozenset({"author", "creator", "lastmodifiedby"})
_SERIAL_KEYS = frozenset(
    {
        "bodyserialnumber",
        "serialnumber",
        "lensserialnumber",
        "internalserialnumber",
        "cameraserialnumber",
    }
)
_DOCUMENT_KEYS = frozenset({"documentid", "instanceid", "originaldocumentid"})
_PLACEHOLDERS = frozenset({"", "0", "00", "0000", "000000", "none", "unknown", "n/a", "null", "-"})


@dataclass(frozen=True, slots=True)
class ValueObservation:
    """One stored field that carries a correlatable value."""

    kind: CorrelationKind
    value_norm: str
    namespace: str
    key: str

    @property
    def value_hash(self) -> str:
        payload = f"{self.kind.value}:{self.value_norm}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def collect_observations(
    items: list[RawMetadataItem], findings: list[Finding]
) -> list[ValueObservation]:
    """Observations for one asset. Duplicates of the same provenance collapse."""
    seen: set[tuple[str, str, str, str]] = set()
    found: list[ValueObservation] = []

    def add(kind: CorrelationKind, raw: str, namespace: str, key: str) -> None:
        norm = _normalize(kind, raw)
        if norm is None:
            return
        marker = (kind.value, norm, namespace, key)
        if marker in seen:
            return
        seen.add(marker)
        found.append(ValueObservation(kind, norm, namespace, key))

    for finding in findings:
        kind = _FINDING_KINDS.get(FindingType(finding.finding_type))
        if kind is None:
            continue
        for namespace, key in _sources(finding.field_source):
            add(kind, finding.evidence_snippet, namespace, key)
    for item in items:
        local = _local(item.key)
        if local in _SERIAL_KEYS:
            add(CorrelationKind.device_serial, item.value, item.namespace, item.key)
        elif local in _DOCUMENT_KEYS:
            add(CorrelationKind.document_id, item.value, item.namespace, item.key)
        elif local in _AUTHOR_KEYS:
            add(CorrelationKind.author_string, item.value, item.namespace, item.key)
    return found


def _sources(field_source: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for part in field_source.split(" | "):
        text = part.strip()
        if not text:
            continue
        namespace, separator, key = text.partition(":")
        if separator and key:
            pairs.append((namespace, key))
        else:
            pairs.append(("finding", text))
    return pairs or [("finding", field_source or "unknown")]


def _normalize(kind: CorrelationKind, raw: str) -> str | None:
    text = _WHITESPACE.sub(" ", (raw or "").strip())
    if not text or len(text) > _MAX_VALUE_CHARS:
        return None
    folded = text.casefold()
    if folded in _PLACEHOLDERS:
        return None
    if kind is CorrelationKind.device_serial:
        if len(folded) < 4 or not any(char.isdigit() for char in folded):
            return None
        return folded
    if kind is CorrelationKind.document_id:
        if len(folded) < 8:
            return None
        return folded
    if kind is CorrelationKind.author_string:
        if len(folded) < 2:
            return None
        return folded
    return folded


def _local(key: str) -> str:
    return key.rsplit(":", 1)[-1].casefold()
