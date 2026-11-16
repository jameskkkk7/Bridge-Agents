"""Application configuration.

The settings model lives in the reusable core package; this module keeps the
historical import path used across the server and tests.
"""

from __future__ import annotations

from bridge_agents.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
