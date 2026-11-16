"""Channel abstractions for mirroring conversations into external chats."""

from __future__ import annotations

from typing import Protocol


class ChannelAdapter(Protocol):
    """Minimal contract shared by messaging channel adapters.

    Adapters are disabled unless every required credential is configured. A
    disabled adapter must never perform outbound network calls.
    """

    name: str

    def is_configured(self) -> bool:
        """True when the channel is enabled and all credentials exist."""
        ...

    async def send_text(self, external_id: str, text: str) -> bool:
        """Send a text reply into an external conversation."""
        ...
