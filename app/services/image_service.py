"""Image storage and retrieval under the configured storage directory."""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.image import Image

LOGGER = logging.getLogger(__name__)

MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}
ALLOWED_IMAGE_TYPES = frozenset(MIME_EXTENSIONS)
IMAGE_SUBDIR = "images"
IMAGE_CONTENT_PREFIX = "[image]"

_IMAGE_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)


def image_content(image_id: str) -> str:
    """Message body used for an image message (keeps the id discoverable)."""
    return f"{IMAGE_CONTENT_PREFIX} {image_id}"


def image_id_from_content(content: str) -> str | None:
    """Extract the image id from an image message body."""
    if not content.startswith(IMAGE_CONTENT_PREFIX):
        return None
    match = _IMAGE_ID_PATTERN.search(content)
    return match.group(0) if match else None


def _storage_root() -> Path:
    return Path(get_settings().storage_dir).expanduser().resolve()


class ImageService:
    """Store image bytes on disk and metadata in the database."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def save(
        self,
        *,
        data: bytes,
        filename: str,
        mime_type: str,
        session_id: str,
        sender_id: str,
    ) -> Image:
        extension = MIME_EXTENSIONS.get(mime_type, ".bin")
        relative_path = f"{IMAGE_SUBDIR}/{uuid4().hex}{extension}"
        target = _storage_root() / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        image = Image(
            session_id=session_id,
            sender_id=sender_id,
            filename=filename,
            mime_type=mime_type,
            file_size=len(data),
            storage_path=relative_path,
        )
        self.db.add(image)
        await self.db.commit()
        await self.db.refresh(image)
        LOGGER.info("image stored (id=%s, %d bytes)", image.id, len(data))
        return image

    async def get(self, image_id: str) -> Image | None:
        result = await self.db.execute(select(Image).where(Image.id == image_id))
        return result.scalar_one_or_none()

    @staticmethod
    def absolute_path(image: Image) -> Path:
        return _storage_root() / image.storage_path

    @staticmethod
    def read_bytes(image: Image) -> bytes:
        return ImageService.absolute_path(image).read_bytes()

    @staticmethod
    def data_url(image: Image) -> str:
        encoded = base64.b64encode(ImageService.read_bytes(image)).decode("ascii")
        return f"data:{image.mime_type};base64,{encoded}"
