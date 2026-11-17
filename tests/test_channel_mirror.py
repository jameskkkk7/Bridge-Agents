"""Channel mirroring: conversation messages reach the bound Lark chat."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.models.channel import SessionChannel
from app.services import channel_mirror
from app.services.reply_handler import deliver_agent_reply
from tests.helpers import create_session, create_user


class _FakeAdapter:
    """Stand-in for the Lark adapter; records what would be sent."""

    name = "lark"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def is_configured(self) -> bool:
        return True

    async def send_text(self, chat_id: str, text: str) -> bool:
        self.sent.append((chat_id, text))
        return True


@pytest.fixture
def lark_enabled(monkeypatch):
    monkeypatch.setenv("LARK_ENABLED", "true")
    monkeypatch.setenv("LARK_APP_ID", "cli_test")
    monkeypatch.setenv("LARK_APP_SECRET", "secret")
    monkeypatch.setenv("LARK_ENCRYPT_KEY", "encrypt-key")
    get_settings.cache_clear()
    channel_mirror.reset_channel_mirror()
    yield
    get_settings.cache_clear()
    channel_mirror.reset_channel_mirror()


async def _bind(db_session, session, chat_id: str = "oc_demo") -> None:
    db_session.add(SessionChannel(session_id=session.id, channel="lark", external_id=chat_id))
    await db_session.commit()


async def test_disabled_channel_does_not_send(db_session) -> None:
    customer = await create_user(db_session, "mirror-disabled@example.test")
    session = await create_session(db_session, customer)
    await _bind(db_session, session)
    assert await channel_mirror.mirror_to_channel(session.id, "Customer", "hello") is False


async def test_bound_session_is_mirrored(db_session, lark_enabled, monkeypatch) -> None:
    customer = await create_user(db_session, "mirror-enabled@example.test")
    session = await create_session(db_session, customer, "Mirrored conversation")
    await _bind(db_session, session)
    fake = _FakeAdapter()
    monkeypatch.setattr(channel_mirror, "get_lark_adapter", lambda settings: fake)

    assert await channel_mirror.mirror_to_channel(session.id, "Customer", "my order is late")
    assert fake.sent == [("oc_demo", "Customer: my order is late")]


async def test_unbound_session_is_not_mirrored(db_session, lark_enabled, monkeypatch) -> None:
    customer = await create_user(db_session, "mirror-unbound@example.test")
    session = await create_session(db_session, customer)
    fake = _FakeAdapter()
    monkeypatch.setattr(channel_mirror, "get_lark_adapter", lambda settings: fake)
    assert await channel_mirror.mirror_to_channel(session.id, "Customer", "hello") is False
    assert fake.sent == []


async def test_adapter_failure_is_swallowed(db_session, lark_enabled, monkeypatch) -> None:
    customer = await create_user(db_session, "mirror-failure@example.test")
    session = await create_session(db_session, customer)
    await _bind(db_session, session)

    class _BrokenAdapter(_FakeAdapter):
        async def send_text(self, chat_id: str, text: str) -> bool:
            raise RuntimeError("lark is down")

    monkeypatch.setattr(channel_mirror, "get_lark_adapter", lambda settings: _BrokenAdapter())
    assert await channel_mirror.mirror_to_channel(session.id, "Customer", "hello") is False


async def test_agent_replies_are_mirrored(db_session, monkeypatch) -> None:
    customer = await create_user(db_session, "mirror-reply@example.test")
    session = await create_session(db_session, customer)
    recorded: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        channel_mirror,
        "schedule_channel_mirror",
        lambda session_id, label, content: recorded.append((session_id, label, content)),
    )
    await deliver_agent_reply(db=db_session, session_id=session.id, content="Here is the answer.")
    assert recorded == [(session.id, "Assistant", "Here is the answer.")]
