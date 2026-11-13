"""Shared detector patterns used by detectors, the classifier, and the guard.

A single copy so the layers cannot drift (TASK-33 / TASK-49).
"""

import re

STRONG_DEBUG_RES = (
    re.compile(r"\b(?:TODO|FIXME|DEBUG|XXX|HACK)\s*:", re.IGNORECASE),
    re.compile(r"\bNOT\s+FOR\s+PUBLIC\s+RELEASE\b", re.IGNORECASE),
    re.compile(r"\bJIRA-\d+\b", re.IGNORECASE),
    re.compile(r"\bGL-\d+\b", re.IGNORECASE),
    re.compile(r"#ISSUE-\d+\b", re.IGNORECASE),
)
WEAK_DEBUG_RE = re.compile(r"\b(?:CONFIDENTIAL|INTERNAL|DRAFT|TEST)\b", re.IGNORECASE)

# Closed allowlist for finding_type=secret (TASK-49). Quantifiers are bounded.
# password= and similar open markers stay on debug_comment only.
SECRET_RES = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----"),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,200}\.[A-Za-z0-9_-]{8,200}\.[A-Za-z0-9_-]{8,200}"),
)


def first_secret_match(text: str) -> re.Match[str] | None:
    """First closed-allowlist secret in ``text``, or None."""
    for pattern in SECRET_RES:
        match = pattern.search(text)
        if match is not None:
            return match
    return None


def snippet_has_closed_secret(text: str) -> bool:
    """True when a closed-allowlist secret pattern is present."""
    return first_secret_match(text) is not None
