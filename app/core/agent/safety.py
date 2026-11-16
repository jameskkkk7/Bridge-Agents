"""Prompt-injection guard (re-exported from the core library)."""

from __future__ import annotations

from bridge_agents.guard import PromptSafetyError, is_prompt_safe, validate_prompt

__all__ = ["PromptSafetyError", "is_prompt_safe", "validate_prompt"]
