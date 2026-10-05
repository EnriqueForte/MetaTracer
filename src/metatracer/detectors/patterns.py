"""Shared debug-comment patterns used by the detector and the classifier.

A single copy so the two layers cannot drift (TASK-33).
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
