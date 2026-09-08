"""Pydantic contracts for the LLM agent layer (TASK-05, subtask 5.2.1).

``AgentFindingEvaluation`` is the persisted evaluation contract. It is fed by
two structured-output calls (routing, subtask 5.2.2):

- the strong model produces :class:`AgentFindingAnalysis` (analysis, severity
  proposal, cited evidence and prose body);
- the fast model produces :class:`FindingTitle` (report title) and
  :class:`ReportSummary` (executive summary, once per run).

The schema deliberately has **no** ``finding_type`` / ``evidence_snippet``
fields: the model cannot mutate evidence it never returns. ``cited_evidence``
must be a verbatim substring of the finding's ``evidence_snippet`` — enforced
deterministically by :mod:`metatracer.agents.guard`, not by the prompt.

All models forbid extra keys so a model that emits unexpected fields fails
validation (one retry, then heuristic fallback). Enum values are lowercase per
the data contract: ``Severity`` is the same StrEnum the database stores.
"""

from pydantic import BaseModel, ConfigDict, Field

from metatracer.db.models import Severity


class AgentFindingAnalysis(BaseModel):
    """Strong-model output for one finding (everything except the title)."""

    model_config = ConfigDict(extra="forbid")

    severity: Severity
    justification: str
    impact_analysis: str
    remediation: str
    reproduction_steps: list[str] = Field(default_factory=list)
    cited_evidence: str


class FindingTitle(BaseModel):
    """Fast-model output: a short report title for one finding."""

    model_config = ConfigDict(extra="forbid")

    title: str


class ReportSummary(BaseModel):
    """Fast-model output: one executive paragraph for the whole run."""

    model_config = ConfigDict(extra="forbid")

    executive_summary: str


class AgentFindingEvaluation(BaseModel):
    """Full per-finding evaluation persisted by TASK-05 (contract 5.2.1)."""

    model_config = ConfigDict(extra="forbid")

    severity: Severity
    justification: str
    impact_analysis: str
    remediation: str
    reproduction_steps: list[str] = Field(default_factory=list)
    cited_evidence: str
    title: str
