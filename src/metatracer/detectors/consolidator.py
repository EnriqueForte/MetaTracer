"""FindingConsolidator (TASK-02 subtask 2.6).

Pure draft -> Finding consolidation: no I/O, no session. The dedup signature
is ``sha256(f"{asset_id}:{finding_type}:{evidence_snippet.strip().lower()}")``;
drafts sharing asset + signature merge into one Finding whose ``field_source``
is the sorted, unique ``" | "``-joined list of origins. When merged drafts
disagree on confidence (the same email bare in Author and buried in a long
Description), the highest wins. ``severity`` stays NULL and
``detector_method`` stays ``rule``.
"""

import hashlib
from collections.abc import Iterable

from metatracer.db.models import Confidence, DetectorMethod, Finding, FindingType
from metatracer.detectors.base import FindingDraft

_CONFIDENCE_RANK = {Confidence.low: 0, Confidence.medium: 1, Confidence.high: 2}


def dedup_signature(asset_id: str, finding_type: FindingType, evidence_snippet: str) -> str:
    """Contracted dedup signature: sha256 of asset + type + normalized snippet."""
    payload = f"{asset_id}:{finding_type}:{evidence_snippet.strip().lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def finding_identity(asset_url: str, finding_type: FindingType | str, evidence_snippet: str) -> str:
    """Run-independent identity of a finding (TASK-35).

    ``dedup_signature`` embeds the asset id, which is new in every run, so it
    cannot match across runs. Comparisons and watch deltas key on the asset's
    final URL instead, with the same snippet normalization.
    """
    kind = finding_type.value if isinstance(finding_type, FindingType) else str(finding_type)
    payload = f"{asset_url}:{kind}:{evidence_snippet.strip().lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def consolidate_drafts(run_id: str, asset_id: str, drafts: Iterable[FindingDraft]) -> list[Finding]:
    """Merge drafts of one asset into deduplicated, persistable Findings."""
    by_signature: dict[str, Finding] = {}
    for draft in drafts:
        signature = dedup_signature(asset_id, draft.finding_type, draft.evidence_snippet)
        finding = by_signature.get(signature)
        if finding is None:
            by_signature[signature] = Finding(
                run_id=run_id,
                asset_id=asset_id,
                finding_type=draft.finding_type,
                field_source=draft.field_source,
                evidence_snippet=draft.evidence_snippet,
                dedup_signature=signature,
                detector_method=DetectorMethod.rule,
                confidence=draft.confidence,
            )
            continue
        sources = set(finding.field_source.split(" | "))
        sources.add(draft.field_source)
        finding.field_source = " | ".join(sorted(sources))
        if _CONFIDENCE_RANK[draft.confidence] > _CONFIDENCE_RANK[finding.confidence]:
            finding.confidence = draft.confidence
    return list(by_signature.values())
