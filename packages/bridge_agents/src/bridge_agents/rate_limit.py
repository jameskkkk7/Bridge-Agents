"""Client address resolution and a small in-memory rate limiter."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def get_client_ip(request: Any) -> str:
    """Resolve the real client address behind the reverse proxy.

    The direct peer address is always the proxy, so using it directly would put
    every visitor into one bucket. The gateway overwrites ``X-Real-IP`` with the
    real address (client supplied values are replaced, so this header cannot be
    spoofed) and appends the connection address to the right of
    ``X-Forwarded-For``. Preference order: ``X-Real-IP``, then the right-most
    ``X-Forwarded-For`` entry, then the direct peer address.
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return parts[-1]

    peer = getattr(request, "client", None)
    if peer is not None and getattr(peer, "host", None):
        return peer.host
    return "127.0.0.1"


class WindowRateLimiter:
    """A fixed-window limiter keyed by an arbitrary string (user or address)."""

    def __init__(
        self,
        max_events: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_events = max_events
        self._window_seconds = window_seconds
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}

    def allow(self, key: str) -> bool:
        """Consume one event for ``key``; False when the window is exhausted."""
        now = self._clock()
        window_start, count = self._windows.get(key, (now, 0))
        if now - window_start >= self._window_seconds:
            self._windows[key] = (now, 1)
            return True
        if count >= self._max_events:
            return False
        self._windows[key] = (window_start, count + 1)
        return True

    def reset(self, key: str) -> None:
        """Forget the window for ``key`` (used when a connection closes)."""
        self._windows.pop(key, None)
