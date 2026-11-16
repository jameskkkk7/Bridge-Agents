"""Prompt-injection guard for user messages.

The guard is a single regular expression. Top-level alternations may contain
groups with their own ``|``, so the configured pattern must always be compiled
as one expression and never split on the pipe character.
"""

from __future__ import annotations

import logging
import re

from bridge_agents.config import get_settings

LOGGER = logging.getLogger(__name__)

# Applied when no pattern is configured. Each entry is compiled together into
# one expression, so grouped alternations stay intact when the guard runs.
_BUILTIN_PATTERNS = (
    r"\bignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|prompts|commands)",
    r"\bdisregard\b[^.\n]{0,40}\b(?:instructions|prompt|system)\b",
    r"\bforget\b[^.\n]{0,30}\b(?:prompt|instructions|rules|training)\b",
    r"\b(?:you are now|from now on you are|new persona)\b",
    r"\b(?:reveal|print|show|leak)\b[^.\n]{0,40}\b(?:system prompt|instructions|system message)\b",
    r"\boverride\b[^.\n]{0,30}\b(?:mode|role|persona|instructions|rules)\b",
    r"\bact as\b[^.\n]{0,20}\b(?:admin|root|sudo|superuser)\b",
    r"\b(?:jailbreak|do anything now|developer mode)\b|\bdan\b",
    r"\b(?:skip|bypass|circumvent)\b[^.\n]{0,30}\b(?:rules|filter|guard|safety)\b",
    r"\bpretend\b[^.\n]{0,30}\b(?:you are|to be)\b",
    r"system prompt",
    r"\b(?:translate|output)\b[^.\n]{0,30}\b(?:prompt|instructions|system)\b",
)
_BUILTIN_PATTERN = "|".join(_BUILTIN_PATTERNS)

_guard: re.Pattern[str] | None = None
_guard_source: str | None = None


def _guard_source_value() -> str:
    configured = (get_settings().agent_injection_patterns or "").strip()
    return configured or _BUILTIN_PATTERN


def _active_guard() -> re.Pattern[str] | None:
    """Compile (and memoise) the active injection pattern."""
    global _guard, _guard_source
    source = _guard_source_value()
    if not source:
        return None
    if _guard is None or _guard_source != source:
        try:
            _guard = re.compile(source, re.IGNORECASE)
        except re.error:
            LOGGER.exception("The configured injection pattern is not valid; the guard is off")
            _guard = None
        _guard_source = source
    return _guard


def is_prompt_safe(message: str) -> bool:
    """Return True when the message does not match an injection pattern."""
    if not message:
        return True
    guard = _active_guard()
    if guard is None:
        return True
    return guard.search(message) is None


class PromptSafetyError(ValueError):
    """Raised when a user message trips the injection guard."""


def validate_prompt(message: str) -> None:
    """Raise ``PromptSafetyError`` when the message is not safe to forward."""
    if not is_prompt_safe(message):
        raise PromptSafetyError("The message contains instructions that are not allowed")
