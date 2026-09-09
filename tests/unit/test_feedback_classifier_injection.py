"""Feedback injection into the heuristic classifier (TASK-13, v2.1+).

Contract verified here: ``feedback_examples`` may only LOWER the heuristic
severity (on a down-vote consensus), never raise it, and never touch the
evidence — the rubric ceilings and anchoring stay authoritative.
"""

from metatracer.agents.memory import FeedbackExample
from metatracer.classification import HeuristicRiskClassifier
from metatracer.db.models import (
    Confidence,
    DetectorMethod,
    FeedbackVote,
    Finding,
    FindingType,
    Severity,
)


def _finding(snippet: str, finding_type: FindingType = FindingType.internal_path) -> Finding:
    return Finding(
        run_id="run-1",
        asset_id="asset-1",
        finding_type=finding_type,
        field_source="EXIF:Path",
        evidence_snippet=snippet,
        dedup_signature="sig",
        detector_method=DetectorMethod.rule,
        confidence=Confidence.high,
    )


def _example(
    before: Severity,
    after: Severity,
    vote: FeedbackVote = FeedbackVote.down,
) -> FeedbackExample:
    return FeedbackExample(
        finding_type=FindingType.internal_path,
        evidence_snippet="/home/jane/private",
        field_source="EXIF:Path",
        severity_before=before,
        severity_after=after,
        vote=vote,
    )


def test_down_vote_lowers_heuristic_severity() -> None:
    classifier = HeuristicRiskClassifier()
    finding = _finding("/home/jane/private")  # heuristic: high
    baseline = classifier.classify(finding)
    assert baseline.severity is Severity.high

    lowered = classifier.classify(
        finding, feedback_examples=[_example(Severity.high, Severity.medium)]
    )
    assert lowered.severity is Severity.medium


def test_no_examples_is_identical_to_baseline() -> None:
    classifier = HeuristicRiskClassifier()
    finding = _finding("/home/jane/private")
    assert (
        classifier.classify(finding).severity
        is classifier.classify(finding, feedback_examples=[]).severity
    )


def test_up_vote_never_raises() -> None:
    """An up-vote is weaker than the rubric anchors: it must NOT raise."""
    classifier = HeuristicRiskClassifier()
    # generic-www path scores medium; an up-vote to high must be ignored
    finding = _finding("/var/www/intranet")
    assert classifier.classify(finding).severity is Severity.medium
    raised = classifier.classify(
        finding, feedback_examples=[_example(Severity.medium, Severity.high, FeedbackVote.up)]
    )
    assert raised.severity is Severity.medium  # unchanged


def test_down_vote_respects_floor_and_cannot_go_below_info() -> None:
    classifier = HeuristicRiskClassifier()
    finding = _finding("/var/www/intranet")  # medium
    # a down-vote to info is still >= info (rubric floor)
    lowered = classifier.classify(
        finding, feedback_examples=[_example(Severity.medium, Severity.info)]
    )
    assert lowered.severity is Severity.info


def test_multiple_down_votes_pick_the_least_renderable() -> None:
    classifier = HeuristicRiskClassifier()
    finding = _finding("/home/jane/private")  # high
    lowered = classifier.classify(
        finding,
        feedback_examples=[
            _example(Severity.high, Severity.medium),
            _example(Severity.high, Severity.low),
        ],
    )
    # internal_path has no template for `low`; the lowest renderable level is
    # `medium` (has_template guard keeps the report writable).
    assert lowered.severity is Severity.medium


def test_down_vote_to_non_renderable_level_is_ignored() -> None:
    classifier = HeuristicRiskClassifier()
    finding = _finding("/home/jane/private")  # high
    # both down votes target `low`, which internal_path cannot render
    lowered = classifier.classify(
        finding,
        feedback_examples=[
            _example(Severity.high, Severity.low),
            _example(Severity.high, Severity.low),
        ],
    )
    assert lowered.severity is Severity.high  # unchanged: no renderable target


def test_feedback_never_alters_evidence() -> None:
    classifier = HeuristicRiskClassifier()
    finding = _finding("/home/jane/private")
    before_snippet = finding.evidence_snippet
    before_type = finding.finding_type
    classifier.classify(
        finding, feedback_examples=[_example(Severity.high, Severity.medium)]
    )
    assert finding.evidence_snippet == before_snippet
    assert finding.finding_type is before_type