"""Lark (Feishu) channel: signed webhook intake and support commands.

The adapter implements the protocol pieces without any framework dependency:

* request verification: ``sha256(timestamp + nonce + encrypt_key + body)``;
* event decryption: ``base64(iv + AES-256-CBC(SHA256(encrypt_key), json))``
  with PKCS7 padding (Lark's documented Encrypt Key scheme);
* event extraction for ``im.message.receive_v1`` text messages;
* command parsing for ``/takeover``, ``/release``, ``/status`` and ``/help``;
* replies through the tenant access token API.

While ``LARK_ENABLED`` is false (the default), every method is inert and no
network request is made. Tests use a mocked transport, so CI never talks to a
real Lark endpoint.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.channel import SessionChannel
from app.models.session import Session
from app.services.channels.base import ChannelAdapter
from app.services.session_service import SessionService
from app.services.staff_reply import send_staff_message
from app.services.takeover_service import apply_takeover

LOGGER = logging.getLogger(__name__)

CHANNEL_NAME = "lark"
_BLOCK_SIZE = 16

AGENT_COMMAND_HELP = (
    "Support commands for this chat:\n"
    "* /takeover — pause the assistant and take over the linked session\n"
    "* /release — hand the linked session back to the assistant\n"
    "* /status — show the session, its status and who is answering\n"
    "* /help — print this list"
)

NO_SESSION_TEXT = (
    "No conversation is linked to this chat yet. Run /takeover <session-id> to link one."
)

FREE_TEXT_HINT = (
    "Take over the conversation first with /takeover <session-id>, then send "
    "your reply as plain text."
)

_COMMAND_ALIASES: dict[str, str] = {
    "/takeover": "takeover",
    "/接管": "takeover",
    "/release": "release",
    "/释放": "release",
    "/结束接管": "release",
    "/status": "status",
    "/状态": "status",
    "/help": "help",
    "/帮助": "help",
}


def sign_payload(encrypt_key: str, timestamp: str, nonce: str, body: bytes | str) -> str:
    """Return the Lark request signature for a raw webhook body."""
    body_bytes = body.encode("utf-8") if isinstance(body, str) else body
    material = (
        timestamp.encode("utf-8") + nonce.encode("utf-8") + encrypt_key.encode("utf-8") + body_bytes
    )
    return hashlib.sha256(material).hexdigest()


def verify_signature(
    encrypt_key: str, timestamp: str, nonce: str, body: bytes | str, signature: str
) -> bool:
    """Verify the ``X-Lark-Signature`` header; missing keys always fail."""
    if not encrypt_key or not signature:
        return False
    expected = sign_payload(encrypt_key, timestamp, nonce, body)
    return hmac.compare_digest(expected, signature)


def parse_command(text: str, allowed: list[str] | None = None) -> str | None:
    """Parse an agent command, tolerating whitespace and trailing arguments."""
    tokens = text.strip().split()
    if not tokens:
        return None
    command = _COMMAND_ALIASES.get(tokens[0].lower())
    if command is None:
        return None
    if allowed is not None and f"/{command}" not in allowed:
        return None
    return command


def command_argument(text: str) -> str:
    """Return the text after the command word, if any."""
    parts = text.strip().split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def agent_actor_id(open_id: str) -> str:
    """Stable message sender id for a Lark agent (no local user row needed)."""
    return str(uuid5(NAMESPACE_URL, f"lark:{open_id}"))


class LarkCrypto:
    """Decrypt Lark events encrypted with an Encrypt Key."""

    def __init__(self, encrypt_key: str) -> None:
        self._key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()

    def decrypt(self, encrypt_b64: str) -> str:
        """Decrypt one base64 ``iv + ciphertext`` payload."""
        raw = base64.b64decode(encrypt_b64)
        if len(raw) <= _BLOCK_SIZE:
            raise ValueError("encrypted payload too short")
        iv, data = raw[:_BLOCK_SIZE], raw[_BLOCK_SIZE:]
        decryptor = Cipher(algorithms.AES(self._key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(data) + decryptor.finalize()
        if not padded:
            raise ValueError("decrypted payload is empty")
        pad_len = padded[-1]
        if not 1 <= pad_len <= _BLOCK_SIZE:
            raise ValueError("invalid PKCS7 padding (wrong encrypt key?)")
        return padded[:-pad_len].decode("utf-8")


@dataclass(frozen=True)
class LarkMessage:
    """A text message received from a Lark chat."""

    chat_id: str
    open_id: str
    text: str
    message_id: str = ""


class LarkAdapter(ChannelAdapter):
    """Lark adapter; all network calls are skipped while disabled."""

    name = CHANNEL_NAME

    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._token: str | None = None
        self._token_expires_at = 0.0

    def is_configured(self) -> bool:
        """Enabled and fully configured (encrypt key is required to verify)."""
        return bool(
            self._settings.lark_enabled
            and self._settings.lark_app_id
            and self._settings.lark_app_secret
            and self._settings.lark_encrypt_key
        )

    @property
    def command_list(self) -> list[str]:
        return self._settings.lark_command_list

    @property
    def help_text(self) -> str:
        return AGENT_COMMAND_HELP

    def verify_request(self, timestamp: str, nonce: str, body: bytes, signature: str) -> bool:
        """Verify one webhook request against the configured Encrypt Key."""
        return verify_signature(self._settings.lark_encrypt_key, timestamp, nonce, body, signature)

    def decrypt_event(self, payload: dict) -> dict | None:
        """Return the decrypted event, or ``None`` when decryption fails."""
        ciphertext = payload.get("encrypt")
        if not ciphertext:
            return payload
        if not self._settings.lark_encrypt_key:
            LOGGER.error("lark events are encrypted but LARK_ENCRYPT_KEY is not set")
            return None
        try:
            return json.loads(LarkCrypto(self._settings.lark_encrypt_key).decrypt(ciphertext))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            LOGGER.error("lark event decryption failed", exc_info=True)
            return None

    def token_is_valid(self, payload: dict) -> bool:
        """Check the verification token when one is configured."""
        expected = self._settings.lark_verification_token
        if not expected:
            return True
        header = payload.get("header") or {}
        actual = payload.get("token") or header.get("token") or ""
        return hmac.compare_digest(str(expected), str(actual))

    def extract_message(self, payload: dict) -> LarkMessage | None:
        """Return a text message event, or ``None`` for anything else."""
        header = payload.get("header") or {}
        if header.get("event_type") != "im.message.receive_v1":
            return None
        event = payload.get("event") or {}
        sender = event.get("sender") or {}
        if sender.get("sender_type") not in (None, "user"):
            return None
        open_id = (sender.get("sender_id") or {}).get("open_id") or ""
        message = event.get("message") or {}
        if message.get("message_type") != "text":
            return None
        try:
            content = json.loads(message.get("content") or "{}")
        except (TypeError, json.JSONDecodeError):
            return None
        text = content.get("text") if isinstance(content, dict) else None
        chat_id = message.get("chat_id") or ""
        if not (open_id and text and chat_id):
            return None
        return LarkMessage(
            chat_id=chat_id,
            open_id=open_id,
            text=text,
            message_id=message.get("message_id", ""),
        )

    def is_agent(self, open_id: str) -> bool:
        """Only whitelisted open ids may run support commands."""
        return open_id in self._settings.lark_agent_open_id_list

    async def send_text(self, chat_id: str, text: str) -> bool:
        """Send a plain-text reply; disabled adapters never call the network."""
        if not self.is_configured():
            return False
        token = await self._tenant_token()
        if not token:
            return False
        url = f"{self._api_base}/open-apis/im/v1/messages"
        payload = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        try:
            response = await self._client().post(
                url,
                params={"receive_id_type": "chat_id"},
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            data = response.json()
        except (httpx.HTTPError, ValueError):
            LOGGER.error("lark send failed", exc_info=True)
            return False
        if response.status_code >= 400 or data.get("code", 0) != 0:
            LOGGER.error("lark send rejected: %s", data)
            return False
        return True

    @property
    def _api_base(self) -> str:
        return self._settings.lark_api_base_url.rstrip("/")

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict = {"timeout": 10.0}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def _tenant_token(self) -> str | None:
        if self._token and time.monotonic() < self._token_expires_at - 300:
            return self._token
        try:
            async with self._client() as client:
                response = await client.post(
                    f"{self._api_base}/open-apis/auth/v3/tenant_access_token/internal",
                    json={
                        "app_id": self._settings.lark_app_id,
                        "app_secret": self._settings.lark_app_secret,
                    },
                )
                data = response.json()
        except (httpx.HTTPError, ValueError):
            LOGGER.error("lark token request failed", exc_info=True)
            return None
        if response.status_code >= 400 or data.get("code", 0) != 0:
            LOGGER.error("lark token rejected: %s", data)
            return None
        self._token = data.get("tenant_access_token")
        expires_in = int(data.get("expire", 7200))
        self._token_expires_at = time.monotonic() + max(expires_in, 0)
        return self._token


async def _mapped_session_id(db: AsyncSession, chat_id: str) -> str | None:
    result = await db.execute(
        select(SessionChannel.session_id).where(
            SessionChannel.channel == CHANNEL_NAME,
            SessionChannel.external_id == chat_id,
        )
    )
    return result.scalar_one_or_none()


async def _bind_chat(db: AsyncSession, session_id: str, chat_id: str) -> None:
    result = await db.execute(
        select(SessionChannel).where(
            SessionChannel.channel == CHANNEL_NAME,
            SessionChannel.session_id == session_id,
        )
    )
    mapping = result.scalar_one_or_none()
    if mapping is None:
        db.add(
            SessionChannel(
                session_id=session_id,
                channel=CHANNEL_NAME,
                external_id=chat_id,
            )
        )
    else:
        mapping.external_id = chat_id
    await db.commit()


def _status_text(session, message_count: int) -> str:
    takeover = "on" if session.human_takeover else "off"
    return (
        f"Session: {session.id}\n"
        f"Title: {session.title}\n"
        f"Status: {session.status.value}\n"
        f"Human takeover: {takeover}\n"
        f"Messages: {message_count}"
    )


async def _session_for_command(
    db: AsyncSession, adapter: LarkAdapter, chat_id: str, text: str
) -> tuple[Session | None, bool]:
    """Resolve the target session; returns ``(session, explicit)``."""
    argument = command_argument(text)
    explicit = bool(argument)
    session_id = argument or await _mapped_session_id(db, chat_id)
    if not session_id:
        return None, explicit
    return await SessionService(db).get(session_id), explicit


async def handle_agent_message(adapter: LarkAdapter, db: AsyncSession, message: LarkMessage) -> str:
    """Execute one agent command or deliver a free-text reply to the customer.

    Returns the reply text (also useful in tests). Slash commands run the
    support actions; plain text from a whitelisted agent becomes a real human
    reply in the bound conversation, but only while takeover is active. Unknown
    slash commands get the help text instead of being sent to a customer.
    """
    command = parse_command(message.text, adapter.command_list)
    if command is None and not message.text.strip().startswith("/"):
        return await _handle_free_text(adapter, db, message)
    if command is None or command == "help":
        reply = adapter.help_text
        await adapter.send_text(message.chat_id, reply)
        return reply

    session, explicit = await _session_for_command(db, adapter, message.chat_id, message.text)
    if command == "status":
        if session is None:
            await adapter.send_text(message.chat_id, NO_SESSION_TEXT)
            return NO_SESSION_TEXT
        reply = _status_text(session, await _message_count(db, session.id))
        await adapter.send_text(message.chat_id, reply)
        return reply

    if session is None:
        await adapter.send_text(message.chat_id, NO_SESSION_TEXT)
        return NO_SESSION_TEXT

    enabled = command == "takeover"
    session = await apply_takeover(
        db, session.id, enabled=enabled, actor_id=agent_actor_id(message.open_id)
    )
    if session is None:
        await adapter.send_text(message.chat_id, NO_SESSION_TEXT)
        return NO_SESSION_TEXT
    await _bind_chat(db, session.id, message.chat_id)
    reply = (
        f'Takeover enabled for "{session.title}" ({session.id[:8]}). AI replies are paused.'
        if enabled
        else f'Takeover released for "{session.title}" ({session.id[:8]}). '
        "The assistant answers again."
    )
    await adapter.send_text(message.chat_id, reply)
    return reply


async def _handle_free_text(adapter: LarkAdapter, db: AsyncSession, message: LarkMessage) -> str:
    """Deliver a plain-text agent message to the bound conversation."""
    session_id = await _mapped_session_id(db, message.chat_id)
    if not session_id:
        await adapter.send_text(message.chat_id, NO_SESSION_TEXT)
        return NO_SESSION_TEXT
    session = await SessionService(db).get(session_id)
    if session is None:
        await adapter.send_text(message.chat_id, NO_SESSION_TEXT)
        return NO_SESSION_TEXT
    if not session.human_takeover:
        await adapter.send_text(message.chat_id, FREE_TEXT_HINT)
        return FREE_TEXT_HINT

    payload = await send_staff_message(
        db,
        session_id=session.id,
        actor_id=agent_actor_id(message.open_id),
        content=message.text.strip(),
    )
    if payload is None:
        await adapter.send_text(message.chat_id, NO_SESSION_TEXT)
        return NO_SESSION_TEXT
    reply = f'Delivered to the customer in "{session.title}".'
    await adapter.send_text(message.chat_id, reply)
    return reply


async def _message_count(db: AsyncSession, session_id: str) -> int:
    from sqlalchemy import func

    from app.models.message import Message

    result = await db.execute(
        select(func.count()).select_from(Message).where(Message.session_id == session_id)
    )
    return int(result.scalar() or 0)
