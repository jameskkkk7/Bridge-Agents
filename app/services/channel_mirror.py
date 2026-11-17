"""Mirror conversation messages into a bound external chat channel.

Only the Lark adapter exists in v0.1. Mirroring is best-effort: a channel
outage must never block or fail a conversation, so sends happen in a background
task and every failure is logged.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.config import Settings, get_settings
from app.models.channel import SessionChannel
from app.models.database import SessionLocal
from app.services.channels.lark import CHANNEL_NAME, LarkAdapter

LOGGER = logging.getLogger(__name__)

_adapter: LarkAdapter | None = None
_adapter_key: tuple | None = None
_background: set[asyncio.Task] = set()


def get_lark_adapter(settings: Settings) -> LarkAdapter:
    """Return the cached adapter for the current Lark configuration."""
    global _adapter, _adapter_key
    key = (
        settings.lark_enabled,
        settings.lark_app_id,
        settings.lark_app_secret,
        settings.lark_encrypt_key,
        settings.lark_api_base_url,
    )
    if _adapter is None or _adapter_key != key:
        _adapter = LarkAdapter(settings)
        _adapter_key = key
    return _adapter


def reset_channel_mirror() -> None:
    """Drop the cached adapter (used by tests after changing settings)."""
    global _adapter, _adapter_key
    if _adapter is not None:
        _adapter = None
    _adapter_key = None


async def _bound_chat(session_id: str) -> str | None:
    async with SessionLocal() as db:
        result = await db.execute(
            select(SessionChannel.external_id).where(
                SessionChannel.channel == CHANNEL_NAME,
                SessionChannel.session_id == session_id,
            )
        )
        return result.scalar_one_or_none()


async def mirror_to_channel(session_id: str, label: str, content: str) -> bool:
    """Send one conversation message to the bound Lark chat, when configured."""
    settings = get_settings()
    if not settings.lark_enabled:
        return False
    adapter = get_lark_adapter(settings)
    if not adapter.is_configured():
        return False
    chat_id = await _bound_chat(session_id)
    if not chat_id:
        return False
    text = f"{label}: {content}"
    try:
        sent = await adapter.send_text(chat_id, text)
    except Exception:
        LOGGER.exception("channel mirror failed for session %s", session_id)
        return False
    if not sent:
        LOGGER.warning("channel mirror was rejected for session %s", session_id)
    return sent


async def _safe_mirror(session_id: str, label: str, content: str) -> None:
    try:
        await mirror_to_channel(session_id, label, content)
    except Exception:
        LOGGER.exception("channel mirror task failed for session %s", session_id)


def schedule_channel_mirror(session_id: str, label: str, content: str) -> None:
    """Queue a mirror without blocking the caller (no-op when Lark is disabled)."""
    if not get_settings().lark_enabled:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_safe_mirror(session_id, label, content))
    _background.add(task)
    task.add_done_callback(_background.discard)
