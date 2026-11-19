"""WebSocket gateway: subscriptions, message intake and reply streaming."""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.core.agent.safety import PromptSafetyError, validate_prompt
from app.core.exceptions import AuthError
from app.core.rate_limit import WindowRateLimiter
from app.models.database import SessionLocal
from app.models.message import MessageType, SenderType, sender_kind
from app.models.user import Role, User
from app.services.image_service import (
    ALLOWED_IMAGE_TYPES,
    ImageService,
    image_content,
)
from app.services.message_service import MessageService
from app.services.reply_engine import start_reply
from app.services.session_service import SessionService
from app.services.user_service import UserService

router = APIRouter()
LOG = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000
RATE_LIMIT_MAX_MESSAGES = 100
RATE_LIMIT_WINDOW_SECONDS = 60.0
STAFF_ROLES = frozenset({Role.AGENT, Role.ADMIN})


class ConnectionManager:
    """Track live sockets and per-user subscriptions to conversations."""

    def __init__(self, max_connections: int) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._subscriptions: dict[str, set[str]] = {}
        self._limiter = WindowRateLimiter(RATE_LIMIT_MAX_MESSAGES, RATE_LIMIT_WINDOW_SECONDS)
        self._max_connections = max_connections

    def connection_count(self) -> int:
        return sum(len(sockets) for sockets in self._connections.values())

    async def connect(self, websocket: WebSocket, user_id: str) -> bool:
        if self.connection_count() >= self._max_connections:
            await websocket.close(code=1013, reason="Server at capacity")
            return False
        await websocket.accept()
        self._connections.setdefault(user_id, set()).add(websocket)
        self._subscriptions.setdefault(user_id, set())
        return True

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        sockets = self._connections.get(user_id)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            self._connections.pop(user_id, None)
            self._subscriptions.pop(user_id, None)
            self._limiter.reset(user_id)

    def subscribe(self, user_id: str, session_id: str) -> None:
        self._subscriptions.setdefault(user_id, set()).add(session_id)

    def unsubscribe(self, user_id: str, session_id: str) -> None:
        self._subscriptions.get(user_id, set()).discard(session_id)

    def is_subscribed(self, user_id: str, session_id: str) -> bool:
        return session_id in self._subscriptions.get(user_id, set())

    def allow_message(self, user_id: str) -> bool:
        return self._limiter.allow(user_id)

    async def _send_safe(self, websocket: WebSocket, payload: dict) -> None:
        try:
            await websocket.send_json(payload)
        except Exception:
            LOG.debug("websocket send failed; connection likely gone", exc_info=True)

    async def send_personal(self, user_id: str, payload: dict) -> None:
        for websocket in list(self._connections.get(user_id, ())):
            await self._send_safe(websocket, payload)

    async def broadcast_to_session(self, session_id: str, payload: dict) -> None:
        # Snapshot first: subscriptions can change while sends are in flight.
        targets = [
            user_id
            for user_id, sessions in list(self._subscriptions.items())
            if session_id in sessions
        ]
        for user_id in targets:
            await self.send_personal(user_id, payload)


connection_manager = ConnectionManager(get_settings().ws_max_connections)


async def _resolve_user(application, token: str) -> User:
    verifier = application.state.token_verifier
    identity = await verifier.verify(token)
    async with SessionLocal() as db:
        user = await UserService(db).get_or_create_from_identity(identity)
        if not user.is_active:
            raise AuthError("This account is inactive")
        return user


async def _can_access(user: User, session_id: str) -> bool:
    async with SessionLocal() as db:
        session = await SessionService(db).get(session_id)
        if session is None:
            return False
        if user.role in STAFF_ROLES:
            return True
        return session.user_id == user.id


def _message_payload(message) -> dict:
    return {
        "type": "message",
        "id": message.id,
        "session_id": message.session_id,
        "sender_id": message.sender_id,
        "sender_type": message.sender_type.value,
        "sender_kind": sender_kind(message),
        "content": message.content,
        "message_type": message.message_type.value if message.message_type else "text",
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


async def _handle_join(websocket: WebSocket, user: User, data: dict) -> None:
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        await websocket.send_json({"type": "error", "message": "session_id is required"})
        return
    if not await _can_access(user, session_id):
        await websocket.send_json({"type": "error", "message": "Access denied to this session"})
        return
    connection_manager.subscribe(user.id, session_id)
    await websocket.send_json({"type": "joined", "session_id": session_id})


async def _handle_message(websocket: WebSocket, application, user: User, data: dict) -> None:
    session_id = data.get("session_id")
    content = data.get("content")
    if not isinstance(session_id, str) or not isinstance(content, str):
        await websocket.send_json(
            {"type": "error", "message": "session_id and content are required"}
        )
        return
    try:
        validate_prompt(content)
    except PromptSafetyError:
        await websocket.send_json({"type": "error", "message": "Message contains unsafe content"})
        return
    stripped = content.strip()
    if not stripped:
        await websocket.send_json({"type": "error", "message": "Message cannot be blank"})
        return
    if len(stripped) > MAX_MESSAGE_LENGTH:
        await websocket.send_json(
            {"type": "error", "message": f"Message too long (max {MAX_MESSAGE_LENGTH} chars)"}
        )
        return
    if not connection_manager.is_subscribed(user.id, session_id) and not await _can_access(
        user, session_id
    ):
        await websocket.send_json({"type": "error", "message": "Access denied to this session"})
        return

    sender_type = SenderType.AGENT if user.role in STAFF_ROLES else SenderType.USER
    try:
        async with SessionLocal() as db:
            message = await MessageService(db).create(
                session_id=session_id,
                sender_id=user.id,
                sender_type=sender_type,
                content=stripped,
            )
    except Exception:
        LOG.error("could not persist websocket message", exc_info=True)
        await websocket.send_json(
            {"type": "error", "message": "Message could not be saved, please retry"}
        )
        return

    await connection_manager.broadcast_to_session(session_id, _message_payload(message))
    label = "Customer" if sender_type is SenderType.USER else "Support"
    from app.services.channel_mirror import schedule_channel_mirror

    schedule_channel_mirror(session_id, label, stripped)
    if sender_type is SenderType.USER:
        start_reply(application, session_id, stripped)


async def _handle_image(websocket: WebSocket, application, user: User, data: dict) -> None:
    session_id = data.get("session_id")
    payload_data = data.get("data")
    mime_type = data.get("mime_type", "image/png")
    filename = data.get("filename", "image")
    if not isinstance(session_id, str) or not isinstance(payload_data, str):
        await websocket.send_json({"type": "error", "message": "session_id and data are required"})
        return
    if mime_type not in ALLOWED_IMAGE_TYPES:
        await websocket.send_json({"type": "error", "message": "Unsupported image type"})
        return
    if not connection_manager.is_subscribed(user.id, session_id) and not await _can_access(
        user, session_id
    ):
        await websocket.send_json({"type": "error", "message": "Access denied to this session"})
        return
    try:
        image_bytes = base64.b64decode(payload_data)
    except Exception:
        await websocket.send_json({"type": "error", "message": "Invalid base64 image data"})
        return
    if len(image_bytes) > get_settings().max_image_size:
        await websocket.send_json({"type": "error", "message": "Image too large"})
        return

    try:
        async with SessionLocal() as db:
            image = await ImageService(db).save(
                data=image_bytes,
                filename=str(filename),
                mime_type=mime_type,
                session_id=session_id,
                sender_id=user.id,
            )
            message = await MessageService(db).create(
                session_id=session_id,
                sender_id=user.id,
                sender_type=SenderType.USER,
                content=image_content(image.id),
                message_type=MessageType.IMAGE,
            )
    except Exception:
        LOG.error("could not store websocket image", exc_info=True)
        await websocket.send_json(
            {"type": "error", "message": "Image could not be saved, please retry"}
        )
        return

    image_event = {
        "type": "image",
        "id": message.id,
        "image_id": image.id,
        "session_id": session_id,
        "sender_id": user.id,
        "sender_type": "user",
        "sender_kind": "user",
        "mime_type": image.mime_type,
        "filename": image.filename,
        "file_size": image.file_size,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }
    await connection_manager.broadcast_to_session(session_id, image_event)
    from app.services.channel_mirror import schedule_channel_mirror

    schedule_channel_mirror(session_id, "Customer", "[image]")


async def _handle_connection(websocket: WebSocket, application, user: User) -> None:
    while True:
        try:
            data = await websocket.receive_json()
        except WebSocketDisconnect:
            raise
        except ValueError:
            await websocket.send_json({"type": "error", "message": "Invalid JSON payload"})
            continue
        if not isinstance(data, dict):
            await websocket.send_json({"type": "error", "message": "Invalid payload"})
            continue

        message_type = data.get("type")
        if message_type == "ping":
            # Heartbeats are never rate limited.
            await websocket.send_json({"type": "pong"})
            continue

        if not connection_manager.allow_message(user.id):
            await websocket.send_json({"type": "error", "message": "Rate limit exceeded"})
            continue

        if message_type == "join":
            await _handle_join(websocket, user, data)
        elif message_type == "leave":
            session_id = data.get("session_id")
            if isinstance(session_id, str):
                connection_manager.unsubscribe(user.id, session_id)
                await websocket.send_json({"type": "left", "session_id": session_id})
        elif message_type == "message":
            await _handle_message(websocket, application, user, data)
        elif message_type == "image":
            await _handle_image(websocket, application, user, data)
        else:
            await websocket.send_json(
                {"type": "error", "message": f"Unsupported message type: {message_type!r}"}
            )


@router.websocket("/ws/v1/chat")
async def chat_socket(websocket: WebSocket) -> None:
    """Authenticate with ``?token=``, then exchange JSON frames."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    try:
        user = await _resolve_user(websocket.app, token)
    except AuthError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    if not await connection_manager.connect(websocket, user.id):
        return
    try:
        await websocket.send_json(
            {"type": "connected", "user_id": user.id, "role": user.role.value}
        )
        await _handle_connection(websocket, websocket.app, user)
    except WebSocketDisconnect:
        pass
    finally:
        await connection_manager.disconnect(user.id, websocket)
