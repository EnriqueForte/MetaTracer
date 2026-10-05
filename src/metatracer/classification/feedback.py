"""Operator-feedback example carried into classification and the agent.

Leaf module: it must not import ``metatracer.agents`` or
``metatracer.classification`` package init (TASK-33). The agent memory
re-exports this class so older import paths keep working.
"""

from pydantic import BaseModel

from metatracer.db.models import FeedbackVote, FindingType, Severity


class FeedbackExample(BaseModel):
    """One structured, LLM-safe example distilled from a feedback row."""

    finding_type: FindingType
    evidence_snippet: str
    field_source: str
    severity_before: Severity
    severity_after: Severity
    vote: FeedbackVote
