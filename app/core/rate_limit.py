"""Client address resolution and rate limiting (re-exported from the library)."""

from __future__ import annotations

from bridge_agents.rate_limit import WindowRateLimiter, get_client_ip

__all__ = ["WindowRateLimiter", "get_client_ip"]
