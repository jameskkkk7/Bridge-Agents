"""Shared test helpers: tokens, users, conversations and stub pipelines."""

from __future__ import annotations

import os
from uuid import uuid4

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image import Image
from app.models.message import Message, MessageType, SenderType
from app.models.session import Session
from app.models.user import Role, User

TEST_SECRET = os.environ.get("JWT_SECRET", "test-secret-key-for-pytest-only-32b")
TEST_ISSUER = os.environ.get("JWT_ISSUER", "bridge-agents-test")


def make_token(user_id: str, role: Role | str) -> str:
    role_value = role.value if isinstance(role, Role) else role
    return jwt.encode(
        {"sub": user_id, "role": role_value, "iss": TEST_ISSUER},
        TEST_SECRET,
        algorithm="HS256",
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def dev_login(client, role: str = "user") -> dict:
    response = await client.post(f"/api/v1/auth/dev-login?role={role}")
    assert response.status_code == 200, response.text
    return response.json()


async def create_user(db: AsyncSession, email: str, role: Role = Role.USER) -> User:
    user = User(email=email, role=role)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def create_session(db: AsyncSession, user: User, title: str = "Test conversation") -> Session:
    session = Session(user_id=user.id, title=title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def add_message(
    db: AsyncSession,
    session: Session,
    sender_id: str,
    sender_type: SenderType,
    content: str,
    message_type: MessageType = MessageType.TEXT,
) -> Message:
    message = Message(
        session_id=session.id,
        sender_id=sender_id,
        sender_type=sender_type,
        content=content,
        message_type=message_type,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def add_image(
    db: AsyncSession, session: Session, sender_id: str, data: bytes = b"image-bytes"
) -> Image:
    from app.services.image_service import ImageService, image_content

    service = ImageService(db)
    image = await service.save(
        data=data,
        filename="sample.png",
        mime_type="image/png",
        session_id=session.id,
        sender_id=sender_id,
    )
    await add_message(
        db,
        session,
        sender_id,
        SenderType.USER,
        image_content(image.id),
        MessageType.IMAGE,
    )
    return image


class StubPipeline:
    """Deterministic fake pipeline used by reply and gateway tests."""

    def __init__(self, reply: str = "A safe answer.") -> None:
        self.reply = reply
        self.states: list[dict] = []

    async def stream(self, state, config=None):
        self.states.append(state)
        yield {"messages": [], "phase": "start"}
        if self.reply:
            yield {
                "messages": [{"role": "assistant", "content": self.reply}],
                "phase": "streaming",
            }
        yield {
            "messages": [{"role": "assistant", "content": self.reply}] if self.reply else [],
            "phase": "done",
        }

    async def invoke(self, state, config=None):
        self.states.append(state)
        messages = list(state.get("messages", []))
        if self.reply:
            messages.append({"role": "assistant", "content": self.reply})
        return {**state, "messages": messages}

    async def close(self) -> None:
        return None


class StuckPipeline(StubPipeline):
    """A pipeline whose stream waits until the task is cancelled."""

    def __init__(self) -> None:
        super().__init__()
        import asyncio

        self.gate = asyncio.Event()

    async def stream(self, state, config=None):
        self.states.append(state)
        yield {"messages": [], "phase": "start"}
        await self.gate.wait()


class RecordingBroadcasts:
    """Patch ``broadcast_to_session`` and collect every outgoing payload."""

    def __init__(self, monkeypatch) -> None:
        self.events: list[tuple[str, dict]] = []
        self._monkeypatch = monkeypatch

    def __enter__(self) -> RecordingBroadcasts:
        from app.ws.gateway import connection_manager

        async def record(session_id: str, payload: dict) -> None:
            self.events.append((session_id, payload))

        self._monkeypatch.setattr(connection_manager, "broadcast_to_session", record)
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def of_type(self, type_name: str) -> list[dict]:
        return [payload for _, payload in self.events if payload.get("type") == type_name]


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid4().hex[:12]}@example.test"
