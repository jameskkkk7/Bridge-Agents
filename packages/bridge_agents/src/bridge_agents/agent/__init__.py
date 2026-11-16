"""Agent pipeline abstraction.

The runtime has a single implementation: the LangGraph pipeline. The
abstraction keeps the HTTP and streaming layers free of graph details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class AgentPipeline(ABC):
    """Interface every agent runtime implements."""

    @abstractmethod
    async def invoke(self, state: dict, config: dict | None = None) -> dict:
        """Run one conversation turn and return the final state."""

    @abstractmethod
    async def stream(self, state: dict, config: dict | None = None) -> AsyncGenerator[dict, None]:
        """Run one conversation turn, yielding incremental state updates."""

    async def close(self) -> None:
        """Release resources held by the pipeline (optional hook)."""
        return None
