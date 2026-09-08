"""LLM agent graph (TASK-05).

ContextOptimizer builds the closed per-finding payload (zero bytes), the
LangGraph loop analyzes/classifies/drafts/persists per finding, the
EvidenceGuard enforces the anti-hallucination invariants deterministically,
and any model failure degrades to the TASK-03 heuristic without losing
findings or aborting the run.
"""

from metatracer.agents.pipeline import AgentPipeline, AgentSummary

__all__ = ["AgentPipeline", "AgentSummary"]
