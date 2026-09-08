"""Heuristic risk classification (TASK-03).

Rubric, evidence anchoring, deterministic classifier and persistence pipeline.
This package is an addition to the TASK-00 layout (which listed no home for
the classifier); it mirrors ``detectors/`` and is consumed by TASK-05 for the
rubric text, the ceilings and the fallback path.
"""

from metatracer.classification.anchor import evidence_is_anchored, parse_gps_line
from metatracer.classification.classifier import (
    HeuristicRiskClassifier,
    SeverityAssessment,
    apply_assessment,
    classify_heuristically,
    unanchored_assessment,
)
from metatracer.classification.pipeline import ClassificationPipeline, ClassificationSummary
from metatracer.classification.rubric import (
    HEURISTIC_CEILINGS,
    RUBRIC_PROMPT_TEXT,
    SEVERITY_RANK,
    cap_severity,
    ceiling_for,
)
from metatracer.classification.templates import SeverityTemplate

__all__ = [
    "HEURISTIC_CEILINGS",
    "RUBRIC_PROMPT_TEXT",
    "SEVERITY_RANK",
    "ClassificationPipeline",
    "ClassificationSummary",
    "HeuristicRiskClassifier",
    "SeverityAssessment",
    "SeverityTemplate",
    "apply_assessment",
    "cap_severity",
    "ceiling_for",
    "classify_heuristically",
    "evidence_is_anchored",
    "parse_gps_line",
    "unanchored_assessment",
]
