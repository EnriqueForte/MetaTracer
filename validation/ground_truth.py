"""Ground truth schema for real-environment validation (post-MVP Phase 0).

A ground truth file describes what a scan of one authorized target *must*
find. ``validation.seed_site`` generates one automatically next to the seeded
files; for targets without planted documents (own real domains, in-scope bug
bounty programs) the file is written by hand during manual triage.

Pure data layer: stdlib + pydantic, no network, no file bytes. Enum values
reuse the closed sets from :mod:`metatracer.db.models` (lowercase in JSON).
"""

from pydantic import BaseModel, Field

from metatracer.db.models import FindingType, Severity


class ExpectedFinding(BaseModel):
    """One finding the scan is expected to report on the asset."""

    type: FindingType
    # Case-insensitive substrings that must ALL appear in the finding's
    # evidence snippet. Empty list = the type match alone is enough.
    evidence_contains: list[str] = Field(default_factory=list)
    # Expected severity once triaged; None = severity is not judged yet
    # (the measure tool reports the observed severity to help fill this in).
    expected_severity: Severity | None = None


class GroundTruthAsset(BaseModel):
    """One asset of the target, matched by URL path suffix."""

    # e.g. "/gps-photo.jpg"; matches any report asset URL whose path ends
    # with it, so the files may be uploaded under any directory prefix.
    url_path: str
    expect_findings: list[ExpectedFinding] = Field(default_factory=list)


class GroundTruth(BaseModel):
    """Root object of a ground truth JSON file."""

    version: int = 1
    target: str
    # complete=True: every report finding must map to an expectation —
    # anything else is a false positive. complete=False (manual triage still
    # in progress): findings on unlisted assets are reported but not
    # penalized as false positives.
    complete: bool = True
    notes: str = ""
    assets: list[GroundTruthAsset] = Field(default_factory=list)
