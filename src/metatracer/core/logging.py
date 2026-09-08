"""Stdlib logging setup and the sanitization helper for target-controlled values.

Format: UTC timestamp, level, logger name, run_id (when a run context is set),
message. No print() anywhere in the library.

Threat 13 (log injection): a value written by the target is never interpolated
raw into a log message — it goes through sanitize_for_log (CR/LF and other line
separators become spaces, output truncated) or travels as a structured extra.
"""

import logging
import time
from contextvars import ContextVar

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [run_id=%(run_id)s] %(message)s"
DEFAULT_MAX_LOG_VALUE = 150

_run_id: ContextVar[str | None] = ContextVar("metatracer_run_id", default=None)

# CR/LF plus the other characters that would forge new lines in a log file.
_LINE_BREAKS = ("\r", "\n", "\x0b", "\x0c", "\x85", "\u2028", "\u2029")


def set_run_context(run_id: str | None) -> None:
    """Set the run_id attached to every subsequent log record in this context."""
    _run_id.set(run_id)


class _UtcFormatter(logging.Formatter):
    """ISO-8601 UTC timestamps; injects the contextual run_id into each record."""

    converter = time.gmtime
    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03dZ"

    def format(self, record: logging.LogRecord) -> str:
        record.run_id = _run_id.get() or "-"
        return super().format(record)


def configure_logging(level: str = "INFO") -> None:
    """Attach the UTC formatter to the 'metatracer' logger hierarchy (idempotent)."""
    logger = logging.getLogger("metatracer")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_UtcFormatter(LOG_FORMAT))
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(level.upper())


def sanitize_for_log(value: object, max_length: int = DEFAULT_MAX_LOG_VALUE) -> str:
    """Make a target-controlled value safe to embed in a log message.

    Line breaks become spaces, any remaining C0 control character (including
    the ANSI escape introducer) or DEL is stripped so the value cannot forge
    lines or alter the terminal, and the output is truncated with a marker.
    """
    text = str(value)
    for char in _LINE_BREAKS:
        text = text.replace(char, " ")
    text = "".join(c for c in text if ord(c) >= 0x20 and ord(c) != 0x7F)
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text
