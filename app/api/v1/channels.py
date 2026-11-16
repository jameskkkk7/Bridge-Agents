"""Webhook endpoints for external messaging channels.

The Lark webhook is the only channel route in v0.1. It is hidden while the
channel is disabled, verifies the request signature, decrypts encrypted events
and hands text messages from whitelisted agents to the adapter.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.exceptions import AuthError, NotFoundError, ValidationError
from app.models.database import get_db
from app.services.channels.lark import LarkAdapter, handle_agent_message

router = APIRouter()


def build_lark_adapter(config: Settings) -> LarkAdapter:
    """Build the Lark adapter for one request; tests patch this factory."""
    return LarkAdapter(config)


@router.post("/lark")
async def lark_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Receive, verify and handle one Lark event."""
    config: Settings = request.app.state.settings
    adapter = build_lark_adapter(config)
    if not adapter.is_configured():
        raise NotFoundError("Lark channel is disabled")

    raw = await request.body()
    if not adapter.verify_request(
        request.headers.get("X-Lark-Request-Timestamp", ""),
        request.headers.get("X-Lark-Request-Nonce", ""),
        raw,
        request.headers.get("X-Lark-Signature", ""),
    ):
        raise AuthError("Invalid Lark signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise ValidationError("Invalid event payload")

    event = adapter.decrypt_event(payload)
    if event is None:
        raise AuthError("Encrypted Lark event could not be decrypted")
    if not adapter.token_is_valid(event):
        raise AuthError("Invalid Lark verification token")
    if event.get("type") == "url_verification":
        return {"challenge": str(event.get("challenge", ""))}

    message = adapter.extract_message(event)
    if message is None or not adapter.is_agent(message.open_id):
        return {"code": 0, "msg": "ignored"}

    await handle_agent_message(adapter, db, message)
    return {"code": 0}
