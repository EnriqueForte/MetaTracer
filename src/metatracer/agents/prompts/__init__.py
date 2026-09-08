"""Versioned prompt artifacts for the agent layer (TASK-05, subtask 5.2.2).

Prompts live as ``.md`` files next to this module so they are reviewed and
versioned like code — never f-strings scattered through the codebase. They
are written in English because they feed the English report layer.

Templates use ``{{TOKEN}}`` placeholders interpolated with plain
``str.replace`` (never ``str.format``: the prompts contain literal JSON
braces). The TASK-03 rubric is injected verbatim from
:data:`metatracer.classification.rubric.RUBRIC_PROMPT_TEXT` so the prompt and
the post-LLM guard can never drift apart.
"""

from functools import cache
from importlib import resources

from metatracer.classification.rubric import RUBRIC_PROMPT_TEXT

_ANALYSIS_TEMPLATE = "analysis_system.md"
_DEPTH_FILES = {
    "brief": "depth_brief.md",
    "standard": "depth_standard.md",
    "detailed": "depth_detailed.md",
}
_TITLE_TEMPLATE = "title_system.md"
_SUMMARY_TEMPLATE = "summary_system.md"


@cache
def load_prompt(name: str) -> str:
    """Read a prompt artifact shipped inside the ``agents.prompts`` package."""
    return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")


def _depth_key(reasoning_depth: str) -> str:
    return reasoning_depth if reasoning_depth in _DEPTH_FILES else "standard"


def analysis_system_prompt(reasoning_depth: str) -> str:
    """System prompt for the strong model: rubric + prohibitions + depth.

    ``reasoning_depth`` only changes the prose-length directive, never the
    evidence rules (subtask 5.4.4).
    """
    depth_text = load_prompt(_DEPTH_FILES[_depth_key(reasoning_depth)])
    return (
        load_prompt(_ANALYSIS_TEMPLATE)
        .replace("{{RUBRIC}}", RUBRIC_PROMPT_TEXT.strip())
        .replace("{{DEPTH_INSTRUCTIONS}}", depth_text.strip())
    )


def title_system_prompt() -> str:
    """System prompt for the fast model when drafting a finding title."""
    return load_prompt(_TITLE_TEMPLATE)


def summary_system_prompt() -> str:
    """System prompt for the fast model when writing the executive summary."""
    return load_prompt(_SUMMARY_TEMPLATE)
