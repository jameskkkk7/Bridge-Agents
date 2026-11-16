"""Persisted runtime settings, including the editable agent graph."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.setting import Setting

AGENT_GRAPH_CONFIG_KEY = "agent_graph_config"


class RuntimeConfigService:
    """Read and write key/value runtime settings."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, key: str, default: str = "") -> str:
        """Return a stored setting value, or the default when absent."""
        result = await self.db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        return setting.value if setting is not None else default

    async def set(self, key: str, value: str) -> Setting:
        """Create or update one setting."""
        result = await self.db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting is None:
            setting = Setting(key=key, value=value)
            self.db.add(setting)
        else:
            setting.value = value
        await self.db.commit()
        await self.db.refresh(setting)
        return setting

    async def delete(self, key: str) -> bool:
        """Delete one setting; returns True when a row was removed."""
        result = await self.db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting is None:
            return False
        await self.db.delete(setting)
        await self.db.commit()
        return True

    async def get_agent_graph_config(self) -> dict | None:
        """Return the saved graph configuration, or None for the built-in graph."""
        raw = await self.get(AGENT_GRAPH_CONFIG_KEY)
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError("The stored agent graph configuration is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValidationError("The stored agent graph configuration is not an object")
        return parsed

    async def set_agent_graph_config(self, config: dict) -> Setting:
        """Persist a validated graph configuration."""
        return await self.set(AGENT_GRAPH_CONFIG_KEY, json.dumps(config))

    async def delete_agent_graph_config(self) -> bool:
        """Remove the saved configuration so the built-in graph is used again."""
        return await self.delete(AGENT_GRAPH_CONFIG_KEY)
