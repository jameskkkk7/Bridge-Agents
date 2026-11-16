"""Create the database schema for local development.

Usage:
    uv run python scripts/init_db.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.models.database import dispose_engine, engine, init_db  # noqa: E402


async def main() -> None:
    """Create all tables and report where the database lives."""
    settings = get_settings()
    await init_db()
    database = engine.url.render_as_string(hide_password=True)
    await dispose_engine()
    print(f"Database schema ready (mode={settings.app_env}, url={database})")


if __name__ == "__main__":
    asyncio.run(main())
