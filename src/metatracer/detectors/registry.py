"""DetectorRegistry: runs the deterministic detectors over one asset's items.

A detector that raises must not kill the run (same isolation rule as a failed
asset): the failure is logged — type names only, never target-controlled
values — and the remaining detectors still run.
"""

import logging
from collections.abc import Sequence

from metatracer.core.logging import sanitize_for_log
from metatracer.db.models import RawMetadataItem
from metatracer.detectors.base import Detector, FindingDraft
from metatracer.detectors.debug import DebugCommentDetector
from metatracer.detectors.email import EmailDetector
from metatracer.detectors.gps import GpsDetector
from metatracer.detectors.network import CloudStorageDetector, InternalEndpointDetector
from metatracer.detectors.paths import InternalPathDetector
from metatracer.detectors.secrets import SecretDetector
from metatracer.detectors.software import SoftwareVersionDetector

logger = logging.getLogger("metatracer.detectors.registry")


class DetectorRegistry:
    """Ordered bundle of the MVP detectors; ``detect_all`` fans items out to them."""

    def __init__(self, detectors: Sequence[Detector] | None = None) -> None:
        self._detectors: list[Detector] = (
            list(detectors)
            if detectors is not None
            else [
                GpsDetector(),
                EmailDetector(),
                InternalPathDetector(),
                InternalEndpointDetector(),
                CloudStorageDetector(),
                SoftwareVersionDetector(),
                DebugCommentDetector(),
                SecretDetector(),
            ]
        )

    def detect_all(self, items: Sequence[RawMetadataItem]) -> list[FindingDraft]:
        drafts: list[FindingDraft] = []
        for detector in self._detectors:
            try:
                drafts.extend(detector.detect(items))
            except Exception as exc:
                logger.warning(
                    "detector %s failed and was skipped: %s",
                    type(detector).__name__,
                    sanitize_for_log(type(exc).__name__),
                )
        return drafts
