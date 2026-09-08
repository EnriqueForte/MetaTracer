"""Deterministic finding detectors (TASK-02)."""

from metatracer.detectors.base import (
    MAX_SNIPPET_CHARS,
    Detector,
    FindingDraft,
    collapse_whitespace,
    normalize_text,
    snippet,
    snippet_around,
)
from metatracer.detectors.consolidator import consolidate_drafts, dedup_signature
from metatracer.detectors.debug import DebugCommentDetector
from metatracer.detectors.email import EmailDetector
from metatracer.detectors.gps import GpsDetector
from metatracer.detectors.paths import InternalPathDetector
from metatracer.detectors.pipeline import DetectionPipeline, DetectionSummary
from metatracer.detectors.registry import DetectorRegistry
from metatracer.detectors.software import SoftwareVersionDetector

__all__ = [
    "MAX_SNIPPET_CHARS",
    "DebugCommentDetector",
    "DetectionPipeline",
    "DetectionSummary",
    "Detector",
    "DetectorRegistry",
    "EmailDetector",
    "FindingDraft",
    "GpsDetector",
    "InternalPathDetector",
    "SoftwareVersionDetector",
    "collapse_whitespace",
    "consolidate_drafts",
    "dedup_signature",
    "normalize_text",
    "snippet",
    "snippet_around",
]
