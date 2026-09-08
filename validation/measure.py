"""Score a MetaTracer JSON report against a ground truth file.

Offline tool (no network): reads the exported report (TASK-04 JSON) and a
ground truth file (see :mod:`validation.ground_truth`), then prints per-type
precision / recall / F1, severity calibration and the triage lists (false
positives, missed expectations, evidence mismatches). With ``--json-out`` the
metrics record is stored for historical tracking; with ``--min-precision`` /
``--min-recall`` the exit code is 1 when the run falls below the gate.

    .venv\\Scripts\\python.exe -m validation.measure `
        --report reports\\metatracer-validation-example-com-....json `
        --ground-truth validation\\site\\ground_truth.json `
        --min-precision 1.0 --min-recall 1.0 `
        --json-out validation\\results\\2026-09-05-seeded-site.json

Matching rules: a report finding belongs to the ground truth asset whose
``url_path`` suffix matches the finding's URL path. An expectation matches an
unmatched finding of the same type on that asset; when ``evidence_contains``
is set, a finding whose evidence misses a substring still counts as a
detection (TP) but is flagged as an evidence mismatch instead of silently
passing. Convention: a metric with zero denominator scores 1.0 (vacuous).
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from metatracer.db.models import FindingType, Severity
from metatracer.reports.schemas import ReportDocument
from validation.ground_truth import ExpectedFinding, GroundTruth


@dataclass(slots=True)
class TpRecord:
    """One expectation matched by a report finding."""

    finding_type: FindingType
    url_path: str
    expected_severity: Severity | None
    actual_severity: Severity | None
    evidence_ok: bool


@dataclass(slots=True)
class ScoreResult:
    """Everything the report card prints and ``--json-out`` persists."""

    target: str
    run_id: str
    complete: bool
    true_positives: list[TpRecord] = field(default_factory=list)
    # (type, asset_url, evidence snippet) — findings to triage.
    false_positives: list[tuple[FindingType, str, str]] = field(default_factory=list)
    # (type, url_path) — expectations no finding matched.
    false_negatives: list[tuple[FindingType, str]] = field(default_factory=list)
    # Findings on assets absent from an INCOMPLETE ground truth: ignored.
    out_of_ground_truth: int = 0

    def counts_by_type(self) -> dict[FindingType, dict[str, int]]:
        types = {t for t, *_ in self.false_positives} | {
            t for t, *_ in self.false_negatives
        } | {r.finding_type for r in self.true_positives}
        return {
            t: {
                "tp": sum(1 for r in self.true_positives if r.finding_type == t),
                "fp": sum(1 for fpt, *_ in self.false_positives if fpt == t),
                "fn": sum(1 for fnt, *_ in self.false_negatives if fnt == t),
            }
            for t in sorted(types, key=lambda t: t.value)
        }


def _norm_path(path: str) -> str:
    normalized = "/" + path.strip().lstrip("/")
    return normalized.rstrip("/") or "/"


def _asset_path_for(asset_url: str, gt_paths: list[str]) -> str | None:
    """The ground truth path matching the finding's URL path, if any.

    ``gt_paths`` must be sorted longest-first so the most specific suffix wins.
    """
    try:
        path = _norm_path(urlsplit(asset_url).path)
    except ValueError:
        return None
    for gt_path in gt_paths:
        if path == gt_path or path.endswith(gt_path):
            return gt_path
    return None


def _evidence_ok(expectation: ExpectedFinding, evidence: str) -> bool:
    haystack = evidence.lower()
    return all(needle.lower() in haystack for needle in expectation.evidence_contains)


def score(report: ReportDocument, ground_truth: GroundTruth) -> ScoreResult:
    """Match report findings against expectations and compute TP / FP / FN."""
    result = ScoreResult(
        target=ground_truth.target,
        run_id=report.run_id,
        complete=ground_truth.complete,
    )
    expectations_by_path: dict[str, list[ExpectedFinding]] = {
        _norm_path(asset.url_path): list(asset.expect_findings)
        for asset in ground_truth.assets
    }
    gt_paths = sorted(expectations_by_path, key=len, reverse=True)

    findings_by_path: dict[str | None, list] = {}
    for finding in report.findings:
        path = _asset_path_for(finding.asset_url, gt_paths)
        findings_by_path.setdefault(path, []).append(finding)

    # Findings on assets the ground truth does not list.
    for finding in findings_by_path.pop(None, []):
        if ground_truth.complete:
            result.false_positives.append((finding.type, finding.asset_url, finding.evidence))
        else:
            result.out_of_ground_truth += 1

    for path, expectations in expectations_by_path.items():
        unmatched = list(findings_by_path.get(path, []))
        for expectation in expectations:
            candidates = [f for f in unmatched if f.type == expectation.type]
            if not candidates:
                result.false_negatives.append((expectation.type, path))
                continue
            chosen = next(
                (f for f in candidates if _evidence_ok(expectation, f.evidence)),
                candidates[0],
            )
            unmatched.remove(chosen)
            result.true_positives.append(
                TpRecord(
                    finding_type=expectation.type,
                    url_path=path,
                    expected_severity=expectation.expected_severity,
                    actual_severity=chosen.severity,
                    evidence_ok=_evidence_ok(expectation, chosen.evidence),
                )
            )
        # Findings of this asset no expectation claimed.
        for finding in unmatched:
            result.false_positives.append((finding.type, finding.asset_url, finding.evidence))

    return result


def _rate(hits: int, total: int) -> float:
    """Vacuous-truth convention: 0/0 scores 1.0 (nothing was wrong)."""
    return hits / total if total else 1.0


def _print_report_card(result: ScoreResult) -> dict:
    """Print the human report card; return the machine-readable metrics."""
    per_type: dict[str, dict[str, float | int]] = {}
    for finding_type, counts in result.counts_by_type().items():
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        per_type[finding_type.value] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": _rate(tp, tp + fp),
            "recall": _rate(tp, tp + fn),
        }

    tp = sum(c["tp"] for c in per_type.values())
    fp = sum(c["fp"] for c in per_type.values())
    fn = sum(c["fn"] for c in per_type.values())
    overall = {"tp": tp, "fp": fp, "fn": fn}
    overall["precision"] = _rate(tp, tp + fp)
    overall["recall"] = _rate(tp, tp + fn)
    overall["f1"] = _rate(
        2 * tp, 2 * tp + fp + fn
    )

    judged = [r for r in result.true_positives if r.expected_severity is not None]
    exact = [
        r
        for r in judged
        if r.actual_severity is not None and r.actual_severity == r.expected_severity
    ]
    unclassified = [r for r in judged if r.actual_severity is None]
    mismatched = [
        r
        for r in judged
        if r.actual_severity is not None and r.actual_severity != r.expected_severity
    ]
    severity = {
        "judged": len(judged),
        "exact": len(exact),
        "mismatch": len(mismatched),
        "unclassified_in_report": len(unclassified),
        "agreement": _rate(len(exact), len(judged)),
    }
    evidence_mismatches = [r for r in result.true_positives if not r.evidence_ok]

    print(f"Target: {result.target}  (run {result.run_id.split('-', 1)[0]})")
    print(
        f"Ground truth: {'complete' if result.complete else 'PARTIAL (triage in progress)'}"
        f" — {tp + fn} expected finding(s), {tp + fp} reported"
    )
    if result.out_of_ground_truth:
        print(
            f"Ignored: {result.out_of_ground_truth} finding(s) on assets not yet "
            "listed in the ground truth"
        )

    header = f"{'type':<18}{'TP':>4}{'FP':>4}{'FN':>4}{'precision':>11}{'recall':>9}{'F1':>7}"
    print(f"\n{header}\n{'-' * len(header)}")
    for name, m in per_type.items():
        f1 = _rate(2 * m["tp"], 2 * m["tp"] + m["fp"] + m["fn"])
        print(
            f"{name:<18}{m['tp']:>4}{m['fp']:>4}{m['fn']:>4}"
            f"{m['precision']:>11.2f}{m['recall']:>9.2f}{f1:>7.2f}"
        )
    print(
        f"{'OVERALL (micro)':<18}{tp:>4}{fp:>4}{fn:>4}"
        f"{overall['precision']:>11.2f}{overall['recall']:>9.2f}{overall['f1']:>7.2f}"
    )

    if judged:
        print(
            f"\nSeverity calibration: {len(exact)}/{len(judged)} exact "
            f"({severity['agreement']:.0%}), {len(mismatched)} mismatch, "
            f"{len(unclassified)} unclassified in report"
        )
        for record in mismatched:
            print(
                f"  MISMATCH {record.finding_type.value} on {record.url_path}: "
                f"expected {record.expected_severity}, report {record.actual_severity}"
            )
    else:
        print(
            "\nSeverity calibration: no expected_severity in the ground truth yet "
            "— fill it during triage to start measuring calibration."
        )

    if evidence_mismatches:
        print("\nEvidence mismatches (detected, but the snippet misses expected text):")
        for record in evidence_mismatches:
            print(f"  - {record.finding_type.value} on {record.url_path}")
    if result.false_positives:
        print("\nFalse positives to triage:")
        for finding_type, asset_url, evidence in result.false_positives:
            print(f"  - {finding_type.value} on {asset_url}: {evidence[:100]!r}")
    if result.false_negatives:
        print("\nMissed expectations (false negatives):")
        for finding_type, path in result.false_negatives:
            print(f"  - {finding_type.value} on {path}")

    return {
        "recorded_at": datetime.now(UTC).isoformat(),
        "target": result.target,
        "run_id": result.run_id,
        "ground_truth_complete": result.complete,
        "per_type": per_type,
        "overall": overall,
        "severity": severity,
        "evidence_mismatches": len(evidence_mismatches),
        "out_of_ground_truth": result.out_of_ground_truth,
        "false_positives": [
            {"type": t.value, "asset_url": url, "evidence": e}
            for t, url, e in result.false_positives
        ],
        "false_negatives": [
            {"type": t.value, "url_path": p} for t, p in result.false_negatives
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", type=Path, required=True, help="exported .json report")
    parser.add_argument(
        "--ground-truth", type=Path, required=True, help="ground truth JSON file"
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="optional path to persist the metrics record (e.g. validation/results/...)",
    )
    parser.add_argument("--min-precision", type=float, default=None)
    parser.add_argument("--min-recall", type=float, default=None)
    args = parser.parse_args()

    report = ReportDocument.model_validate(json.loads(args.report.read_text(encoding="utf-8")))
    ground_truth = GroundTruth.model_validate(
        json.loads(args.ground_truth.read_text(encoding="utf-8"))
    )
    metrics = _print_report_card(score(report, ground_truth))

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\nmetrics record written to {args.json_out}")

    failures = []
    if args.min_precision is not None and metrics["overall"]["precision"] < args.min_precision:
        failures.append(
            f"precision {metrics['overall']['precision']:.2f} < {args.min_precision:.2f}"
        )
    if args.min_recall is not None and metrics["overall"]["recall"] < args.min_recall:
        failures.append(f"recall {metrics['overall']['recall']:.2f} < {args.min_recall:.2f}")
    if failures:
        print(f"\nRESULT: BELOW THRESHOLDS — {'; '.join(failures)}")
        return 1
    print("\nRESULT: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
