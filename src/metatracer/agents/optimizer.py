"""ContextOptimizer (TASK-05, subtask 5.1).

Builds the exact per-finding payload sent to the model — and nothing else.
The payload contract is closed (subtask 5.1.1):

    finding_type, field_source, evidence_snippet, confidence,
    heuristic_severity, target_domain, asset_content_type, asset_url

Hard rules enforced here:

- **Zero bytes**: payloads are plain JSON-safe strings; a bytes value anywhere
  is a construction error (rule 3 of the safety invariants).
- Empty keys and null template values are dropped (subtask 5.1.2).
- One finding per call in the MVP: grouping is skipped entirely, so evidence
  from different findings is never mixed (subtask 5.1.3).
- ~1.500-token budget per call, estimated as ``len(text) // 4``; an oversized
  snippet is truncated with a marker and the cut is logged.
- Cost cap (subtask 5.1.4): at most ``max_findings`` per run; the excess is
  prioritized by type (gps -> internal_path -> debug_comment -> email ->
  software_version) and the cut is logged. Cut findings keep their TASK-03
  heuristic baseline untouched.
"""

import json
import logging
from dataclasses import dataclass

from metatracer.core.exceptions import MetaTracerError
from metatracer.core.logging import sanitize_for_log
from metatracer.db.models import Asset, Finding, FindingType

logger = logging.getLogger("metatracer.agents.optimizer")

# Subtask 5.1.3: per-call budget, estimated with len(text)//4 (MVP estimate).
MAX_CALL_TOKENS = 1500
_SNIPPET_MARK = "..."

# Subtask 5.1.4: priority order when the run has more findings than the cap.
_TYPE_PRIORITY: dict[FindingType, int] = {
    FindingType.gps: 0,
    FindingType.internal_path: 1,
    FindingType.debug_comment: 2,
    FindingType.email: 3,
    FindingType.software_version: 4,
}

# The closed set of payload keys (subtask 5.1.1). Anything else — finding ids,
# baseline flags — travels alongside the payload, never inside it.
PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "finding_type",
        "field_source",
        "evidence_snippet",
        "confidence",
        "heuristic_severity",
        "target_domain",
        "asset_content_type",
        "asset_url",
    }
)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (subtask 5.1.3): ``len(text) // 4``, at least 1."""
    return max(1, len(text) // 4)


@dataclass(frozen=True, slots=True)
class OptimizedFinding:
    """One finding ready for the graph: the LLM payload plus bookkeeping.

    ``finding_id`` and ``had_baseline_severity`` are pipeline bookkeeping and
    must never be sent to the model — only ``payload`` is.
    """

    finding_id: str
    payload: dict[str, str]
    had_baseline_severity: bool


def _ensure_json_safe(payload: dict[str, str]) -> None:
    """Reject bytes and non-serializable values (zero-bytes invariant)."""
    for key, value in payload.items():
        if isinstance(value, bytes | bytearray | memoryview):
            raise MetaTracerError(f"payload key {key!r} holds bytes; the LLM never sees bytes")
    try:
        json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise MetaTracerError(f"payload is not JSON-serializable: {exc}") from exc


class ContextOptimizer:
    """Turns persisted findings into minimal, budgeted LLM payloads."""

    def __init__(self, max_findings: int, max_call_tokens: int = MAX_CALL_TOKENS) -> None:
        self._max_findings = max(0, max_findings)
        self._max_call_tokens = max_call_tokens

    def build_entry(
        self, finding: Finding, asset: Asset | None, target_domain: str
    ) -> OptimizedFinding:
        """Build the closed payload for one finding (subtasks 5.1.1-5.1.3)."""
        payload: dict[str, str | None] = {
            "finding_type": str(finding.finding_type),
            "field_source": finding.field_source,
            "evidence_snippet": finding.evidence_snippet,
            "confidence": str(finding.confidence),
            # The TASK-03 baseline may be absent (NULL) — nulls are dropped.
            "heuristic_severity": str(finding.severity) if finding.severity else None,
            "target_domain": target_domain,
            "asset_content_type": asset.content_type if asset is not None else None,
            "asset_url": asset.final_url if asset is not None else None,
        }
        # Subtask 5.1.2: drop empty keys and null template values.
        clean = {key: value for key, value in payload.items() if value and value.strip()}
        clean = self._enforce_budget(clean)
        _ensure_json_safe(clean)
        return OptimizedFinding(
            finding_id=finding.id,
            payload=clean,
            had_baseline_severity=finding.severity is not None,
        )

    def optimize(
        self, rows: list[tuple[Finding, Asset | None]], target_domain: str
    ) -> list[OptimizedFinding]:
        """Build payloads and apply the per-run cost cap (subtask 5.1.4).

        When the run exceeds the cap, findings are selected by type priority
        (stable: original order is kept within a type and across the result);
        the cut is logged. Cut findings are simply not agent-evaluated.
        """
        if len(rows) > self._max_findings:
            prioritized = sorted(
                enumerate(rows),
                key=lambda pair: (_TYPE_PRIORITY[pair[1][0].finding_type], pair[0]),
            )
            kept_indices = sorted(index for index, _ in prioritized[: self._max_findings])
            dropped = len(rows) - len(kept_indices)
            logger.warning(
                "context budget cut: %d findings exceed max_findings=%d; "
                "dropping %d lowest-priority findings (they keep the heuristic baseline)",
                len(rows),
                self._max_findings,
                dropped,
            )
            rows = [rows[index] for index in kept_indices]
        return [self.build_entry(finding, asset, target_domain) for finding, asset in rows]

    def _enforce_budget(self, payload: dict[str, str]) -> dict[str, str]:
        """Shrink an oversized snippet so the payload fits the token budget."""
        text = json.dumps(payload, ensure_ascii=False)
        if estimate_tokens(text) <= self._max_call_tokens:
            return payload
        snippet = payload.get("evidence_snippet", "")
        overflow_chars = len(text) - self._max_call_tokens * 4
        keep = len(snippet) - overflow_chars - len(_SNIPPET_MARK)
        if keep <= 0:
            # Even an empty snippet overflows (huge URL/field_source): drop the
            # evidence; the downstream guard forces severity info (rule 3.2.1).
            payload["evidence_snippet"] = ""
        else:
            payload["evidence_snippet"] = snippet[:keep] + _SNIPPET_MARK
        logger.warning(
            "payload exceeded %d estimated tokens; evidence snippet truncated to fit (%s)",
            self._max_call_tokens,
            sanitize_for_log(payload.get("finding_type", "?")),
        )
        return payload
