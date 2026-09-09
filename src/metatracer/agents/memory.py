"""FeedbackMemory: few-shot examples from operator corrections (TASK-13, v2.1+).

The feedback loop turns persisted :class:`~metatracer.db.models.FindingFeedback`
rows into bounded few-shot guidance for runs with similar findings.

Contract rules (subtasks 13.3/13.4 of TASK-13):

- ``examples_for(finding_type)`` returns only examples of that exact type and
  at most ``max_examples_per_type`` (newest first) — cross-type contamination
  would teach the wrong lesson.
- **The operator ``reason`` never travels to the LLM**: it may carry engagement
  context that belongs to the hunter alone. Only structured fields that are
  already part of the closed payload (finding type, evidence snippet, field
  source, before/after severity, vote) appear in an example.
- A memory with no rows is a complete no-op: pipelines that inject it behave
  exactly as before when it is empty.
- Zero new dependencies: the loader reuses the session factory / repositories.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel

from metatracer.db.models import FeedbackVote, Finding, FindingType, Severity
from metatracer.db.repositories import FeedbackRepository


class FeedbackExample(BaseModel):
    """One structured, LLM-safe example distilled from a feedback row."""

    finding_type: FindingType
    evidence_snippet: str
    field_source: str
    severity_before: Severity
    severity_after: Severity
    vote: FeedbackVote


@dataclass(slots=True)
class FeedbackMemory:
    """In-memory store of operator feedback, keyed by finding_type.

    ``load`` is async because it reads through the session factory; the
    pipelines call it once per phase. ``examples_for`` is a pure read of the
    loaded rows and never touches the database.
    """

    max_examples_per_type: int = 5
    _by_type: dict[FindingType, list[FeedbackExample]] = field(
        default_factory=dict, init=False
    )

    @staticmethod
    def example_from_row(row, finding: Finding) -> FeedbackExample:
        """Distill one feedback row + its finding into an LLM-safe example.

        ``row.severity_before`` is stored at vote time and may lag behind the
        finding's current severity; the persisted pair is the truth of what
        the operator saw and corrected.
        """
        return FeedbackExample(
            finding_type=FindingType(finding.finding_type),
            evidence_snippet=finding.evidence_snippet,
            field_source=finding.field_source,
            severity_before=Severity(row.severity_before),
            severity_after=Severity(row.severity_after),
            vote=FeedbackVote(row.vote),
        )

    async def load(self, session_factory) -> None:
        """Load recent feedback joined with its finding, bucketed by type."""
        self._by_type = {}
        async with session_factory() as session:
            rows = await FeedbackRepository(session).list_recent(limit=200)
            findings: dict[str, Finding] = {}
            # Feedback rows always reference a persisted finding; guard a
            # missing one defensively (a corrupt row must not crash a scan).
            for row in rows:
                if row.finding_id in findings:
                    continue
                finding = await session.get(Finding, row.finding_id)
                if finding is not None:
                    findings[row.finding_id] = finding
        for row in rows:
            finding = findings.get(row.finding_id)
            if finding is None:
                continue
            ftype = FindingType(finding.finding_type)
            bucket = self._by_type.setdefault(ftype, [])
            if len(bucket) >= self.max_examples_per_type:
                continue
            bucket.append(self.example_from_row(row, finding))

    def examples_for(self, finding_type: FindingType) -> list[FeedbackExample]:
        """Newest-loaded examples for one finding type (bounded, type-safe)."""
        return list(self._by_type.get(finding_type, []))


def examples_to_payload(
    examples: list[FeedbackExample], *, max_chars: int = 1200
) -> list[dict[str, str]]:
    """Serialize examples for prompt injection, JSON-safe and size-capped.

    Only the closed contract keys travel: no ``reason``, no identifiers.
    The agent prompt renders this as "operator guidance" — never as evidence.
    """
    rendered: list[dict[str, str]] = []
    used = 0
    for example in examples:
        payload = {
            "vote": str(example.vote),
            "severity_before": str(example.severity_before),
            "severity_after": str(example.severity_after),
            "finding_type": str(example.finding_type),
            "field_source": example.field_source,
            "evidence_snippet": example.evidence_snippet,
        }
        cost = sum(len(value) for value in payload.values())
        if used + cost > max_chars:
            break
        used += cost
        rendered.append(payload)
    return rendered