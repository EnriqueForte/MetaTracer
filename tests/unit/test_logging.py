"""sanitize_for_log: mitigation of threat 13 (log injection via target values)."""

from metatracer.core.logging import sanitize_for_log


def test_line_breaks_become_spaces() -> None:
    assert sanitize_for_log("one\ntwo\r\nthree\u2028four") == "one two  three four"


def test_ansi_escapes_and_c0_controls_are_stripped() -> None:
    # The ESC introducer of ANSI sequences and other C0 chars (e.g. BEL) are removed.
    assert sanitize_for_log("ok\x1b[31mred\x1b[0m\x07") == "ok[31mred[0m"


def test_truncation_has_explicit_marker() -> None:
    text = sanitize_for_log("x" * 500)
    assert len(text) == 153  # 150 chars + "..."
    assert text.endswith("...")
