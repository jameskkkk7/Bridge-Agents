"""Lark channel tests: crypto vectors, signatures, commands and the webhook."""

from __future__ import annotations

import base64
import hashlib
import json

import httpx
import pytest
from sqlalchemy import select

from app.config import Settings
from app.models.channel import SessionChannel
from app.models.message import Message, MessageType, SenderType
from app.services.channels.lark import (
    AGENT_COMMAND_HELP,
    LarkAdapter,
    LarkCrypto,
    LarkMessage,
    parse_command,
    sign_payload,
    verify_signature,
)
from tests.helpers import add_message, create_session, create_user

ENCRYPT_KEY = "unit-test-encrypt-key"
TIMESTAMP = "1700000000"
NONCE = "test-nonce"

# Lark's published "Event decryption" example.
OFFICIAL_KEY = "test key"
OFFICIAL_CIPHER = "P37w+VZImNgPEO1RBhJ6RtKl7n6zymIbEG1pReEzghk="
OFFICIAL_PLAIN = "hello world"


def make_settings(**overrides) -> Settings:
    values = {
        "lark_enabled": True,
        "lark_app_id": "cli_test",
        "lark_app_secret": "secret",
        "lark_encrypt_key": ENCRYPT_KEY,
        "lark_verification_token": "",
        "lark_agent_open_ids": "ou_agent",
        "lark_commands": "/takeover,/release,/status,/help",
    }
    values.update(overrides)
    return Settings(**values)


def encrypt_text(plaintext: str, key: str = ENCRYPT_KEY, iv: bytes = b"\x07" * 16) -> str:
    """Encrypt like Lark: base64(iv + AES-256-CBC(SHA256(key), PKCS7(plain)))."""
    data = plaintext.encode("utf-8")
    pad_len = 16 - len(data) % 16
    data += bytes([pad_len]) * pad_len
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    encryptor = Cipher(
        algorithms.AES(hashlib.sha256(key.encode("utf-8")).digest()),
        modes.CBC(iv),
    ).encryptor()
    return base64.b64encode(iv + encryptor.update(data) + encryptor.finalize()).decode()


def text_event(
    text: str,
    *,
    open_id: str = "ou_agent",
    chat_id: str = "oc_demo",
    event_type: str = "im.message.receive_v1",
    message_type: str = "text",
    token: str = "",
) -> dict:
    return {
        "schema": "2.0",
        "header": {"event_id": "evt_1", "event_type": event_type, "token": token},
        "event": {
            "sender": {"sender_id": {"open_id": open_id}, "sender_type": "user"},
            "message": {
                "message_id": "om_1",
                "chat_id": chat_id,
                "message_type": message_type,
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        },
    }


def signed_headers(body: bytes, key: str = ENCRYPT_KEY) -> dict[str, str]:
    return {
        "X-Lark-Request-Timestamp": TIMESTAMP,
        "X-Lark-Request-Nonce": NONCE,
        "X-Lark-Signature": sign_payload(key, TIMESTAMP, NONCE, body),
    }


async def post_event(client, event: dict, *, key: str = ENCRYPT_KEY, headers=None):
    body = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return await client.post(
        "/webhook/lark", content=body, headers=headers or signed_headers(body, key)
    )


async def post_encrypted_event(client, event: dict):
    plain = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    body = json.dumps({"encrypt": encrypt_text(plain)}, separators=(",", ":")).encode("utf-8")
    return await client.post("/webhook/lark", content=body, headers=signed_headers(body))


class TestCrypto:
    def test_official_doc_vector(self) -> None:
        assert LarkCrypto(OFFICIAL_KEY).decrypt(OFFICIAL_CIPHER) == OFFICIAL_PLAIN

    def test_roundtrip_json_event(self) -> None:
        event = text_event("/takeover")
        plain = json.dumps(event, ensure_ascii=False)
        decrypted = LarkCrypto(ENCRYPT_KEY).decrypt(encrypt_text(plain))
        assert json.loads(decrypted) == event

    def test_wrong_key_raises(self) -> None:
        with pytest.raises((ValueError, UnicodeDecodeError)):
            LarkCrypto("wrong-key").decrypt(encrypt_text("hello"))

    def test_short_payload_raises(self) -> None:
        with pytest.raises(ValueError):
            LarkCrypto(ENCRYPT_KEY).decrypt(base64.b64encode(b"short").decode())


class TestSignature:
    def test_valid_signature(self) -> None:
        body = b'{"hello": "world"}'
        signature = sign_payload(ENCRYPT_KEY, TIMESTAMP, NONCE, body)
        assert verify_signature(ENCRYPT_KEY, TIMESTAMP, NONCE, body, signature)

    def test_tampered_body_rejected(self) -> None:
        body = b'{"hello": "world"}'
        signature = sign_payload(ENCRYPT_KEY, TIMESTAMP, NONCE, body)
        assert not verify_signature(ENCRYPT_KEY, TIMESTAMP, NONCE, b'{"hello": "there"}', signature)

    def test_missing_key_or_signature_rejected(self) -> None:
        body = b"{}"
        assert not verify_signature("", TIMESTAMP, NONCE, body, "x")
        assert not verify_signature(ENCRYPT_KEY, TIMESTAMP, NONCE, body, "")


class TestCommands:
    def test_aliases(self) -> None:
        assert parse_command("/takeover") == "takeover"
        assert parse_command("/接管") == "takeover"
        assert parse_command("/release") == "release"
        assert parse_command("/结束接管") == "release"
        assert parse_command("/status") == "status"
        assert parse_command("/状态") == "status"
        assert parse_command("/help") == "help"
        assert parse_command("/帮助") == "help"

    def test_whitespace_and_arguments(self) -> None:
        assert parse_command("  /接管  now  ") == "takeover"
        assert parse_command("/takeover 1234") == "takeover"

    def test_unknown_and_non_commands(self) -> None:
        assert parse_command("/关机") is None
        assert parse_command("接管") is None
        assert parse_command("") is None

    def test_allowed_commands_filter(self) -> None:
        assert parse_command("/release", ["/takeover", "/help"]) is None
        assert parse_command("/takeover", ["/takeover", "/help"]) == "takeover"


class TestMessageExtraction:
    def test_text_message(self) -> None:
        adapter = LarkAdapter(make_settings())
        message = adapter.extract_message(text_event("/status"))
        assert message == LarkMessage(
            chat_id="oc_demo", open_id="ou_agent", text="/status", message_id="om_1"
        )

    def test_non_text_and_other_events_ignored(self) -> None:
        adapter = LarkAdapter(make_settings())
        assert adapter.extract_message(text_event("x", message_type="image")) is None
        assert (
            adapter.extract_message(text_event("x", event_type="im.chat.member.bot.added_v1"))
            is None
        )
        assert adapter.extract_message({"challenge": "c"}) is None

    def test_bot_sender_ignored(self) -> None:
        adapter = LarkAdapter(make_settings())
        event = text_event("/status")
        event["event"]["sender"]["sender_type"] = "app"
        assert adapter.extract_message(event) is None


class TestDisabledAdapter:
    def test_not_configured(self) -> None:
        adapter = LarkAdapter(make_settings(lark_enabled=False))
        assert adapter.is_configured() is False

    def test_send_text_is_inert_and_offline(self) -> None:
        calls: list[httpx.Request] = []

        def fail(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            raise AssertionError("network must not be used while disabled")

        adapter = LarkAdapter(
            make_settings(lark_enabled=False), transport=httpx.MockTransport(fail)
        )

        import asyncio

        assert asyncio.run(adapter.send_text("oc_demo", "hi")) is False
        assert calls == []


class TestWebhook:
    async def test_hidden_while_disabled(self, client) -> None:
        response = await client.post("/webhook/lark", json={"hello": "world"})
        assert response.status_code == 404

    async def test_bad_signature_rejected(self, app, client, monkeypatch) -> None:
        monkeypatch.setattr(app.state, "settings", make_settings())
        body = json.dumps({"challenge": "x"}).encode()
        response = await client.post(
            "/webhook/lark",
            content=body,
            headers={
                "X-Lark-Request-Timestamp": TIMESTAMP,
                "X-Lark-Request-Nonce": NONCE,
                "X-Lark-Signature": "0" * 64,
            },
        )
        assert response.status_code == 401

    async def test_url_verification_challenge(self, app, client, monkeypatch) -> None:
        monkeypatch.setattr(app.state, "settings", make_settings(lark_verification_token="vtoken"))
        event = {"challenge": "ch-123", "type": "url_verification", "token": "vtoken"}
        response = await post_event(client, event)
        assert response.status_code == 200
        assert response.json() == {"challenge": "ch-123"}

    async def test_verification_token_mismatch(self, app, client, monkeypatch) -> None:
        monkeypatch.setattr(app.state, "settings", make_settings(lark_verification_token="vtoken"))
        response = await post_event(client, text_event("/help", token="other"))
        assert response.status_code == 401

    async def test_non_agent_sender_ignored(self, app, client, monkeypatch) -> None:
        monkeypatch.setattr(app.state, "settings", make_settings())
        replies: list[str] = []

        async def fake_send(self, chat_id: str, text: str) -> bool:
            replies.append(text)
            return True

        monkeypatch.setattr(LarkAdapter, "send_text", fake_send)
        response = await post_event(client, text_event("/help", open_id="ou_customer"))
        assert response.status_code == 200
        assert response.json() == {"code": 0, "msg": "ignored"}
        assert replies == []

    async def test_encrypted_help_command(self, app, client, db_session, monkeypatch) -> None:
        monkeypatch.setattr(app.state, "settings", make_settings())
        replies: list[tuple[str, str]] = []

        async def fake_send(self, chat_id: str, text: str) -> bool:
            replies.append((chat_id, text))
            return True

        monkeypatch.setattr(LarkAdapter, "send_text", fake_send)
        response = await post_encrypted_event(client, text_event("/help"))
        assert response.status_code == 200
        assert replies == [("oc_demo", AGENT_COMMAND_HELP)]

    async def test_unknown_command_gets_help(self, app, client, monkeypatch) -> None:
        monkeypatch.setattr(app.state, "settings", make_settings())
        replies: list[str] = []

        async def fake_send(self, chat_id: str, text: str) -> bool:
            replies.append(text)
            return True

        monkeypatch.setattr(LarkAdapter, "send_text", fake_send)
        assert (await post_event(client, text_event("/shutdown"))).status_code == 200
        assert replies == [AGENT_COMMAND_HELP]

    async def test_takeover_links_chat_and_status_uses_mapping(
        self, app, client, db_session, monkeypatch
    ) -> None:
        monkeypatch.setattr(app.state, "settings", make_settings())
        replies: list[str] = []

        async def fake_send(self, chat_id: str, text: str) -> bool:
            replies.append(text)
            return True

        monkeypatch.setattr(LarkAdapter, "send_text", fake_send)
        customer = await create_user(db_session, "lark-customer@example.test")
        session = await create_session(db_session, customer, "Lark linked session")
        await add_message(db_session, session, customer.id, SenderType.USER, "hello")

        response = await post_event(client, text_event(f"/takeover {session.id}"))
        assert response.status_code == 200
        assert "Takeover enabled" in replies[-1]

        await db_session.refresh(session)
        assert session.human_takeover is True
        system_messages = list(
            (
                await db_session.execute(
                    select(Message).where(
                        Message.session_id == session.id,
                        Message.message_type == MessageType.SYSTEM,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert system_messages
        mapping = (
            await db_session.execute(
                select(SessionChannel).where(SessionChannel.session_id == session.id)
            )
        ).scalar_one()
        assert mapping.channel == "lark"
        assert mapping.external_id == "oc_demo"

        status = await post_event(client, text_event("/status"))
        assert status.status_code == 200
        assert "Human takeover: on" in replies[-1]
        assert "Lark linked session" in replies[-1]

        release = await post_event(client, text_event("/release"))
        assert release.status_code == 200
        await db_session.refresh(session)
        assert session.human_takeover is False
