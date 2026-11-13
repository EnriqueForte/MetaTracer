"""SecretDetector (TASK-49): closed-allowlist credentials in extracted metadata.

Reads stored ``RawMetadataItem`` values only — never file bodies, JS source,
or sourcemaps. Patterns live in ``detectors/patterns.py`` so the classifier
and the post-LLM guard cannot drift.

``password=`` and other open markers are not this type: those stay on
``debug_comment`` when a debug keyword is also present. A clean AKIA / PAT /
PEM / JWT without TODO/FIXME is ``secret``, not ``debug_comment``.
"""

from collections.abc import Sequence

from metatracer.db.models import Confidence, FindingType, RawMetadataItem
from metatracer.detectors.base import FindingDraft, collapse_whitespace, normalize_text, snippet
from metatracer.detectors.patterns import SECRET_RES

_WRAPPER = "<>()[]{}\"' "


class SecretDetector:
    """Closed-allowlist secrets in any extracted metadata field."""

    finding_type = FindingType.secret

    def detect(self, items: Sequence[RawMetadataItem]) -> list[FindingDraft]:
        drafts: list[FindingDraft] = []
        for item in items:
            text = collapse_whitespace(normalize_text(item.value))
            if not text:
                continue
            seen: set[str] = set()
            for pattern in SECRET_RES:
                for match in pattern.finditer(text):
                    token = snippet(match.group(0))
                    key = token.casefold()
                    if not token or key in seen:
                        continue
                    seen.add(key)
                    drafts.append(_draft(item, token, text))
        return drafts


def _draft(item: RawMetadataItem, evidence: str, field_text: str) -> FindingDraft:
    bare = field_text.strip(_WRAPPER)
    confidence = Confidence.high if bare.casefold() == evidence.casefold() else Confidence.medium
    return FindingDraft(
        finding_type=FindingType.secret,
        field_source=f"{item.namespace}:{item.key}",
        evidence_snippet=evidence,
        confidence=confidence,
    )
