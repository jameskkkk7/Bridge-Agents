"""Client address resolution and the rate limiter."""

from __future__ import annotations

from starlette.requests import Request

from app.core.rate_limit import WindowRateLimiter, get_client_ip


def _request(headers: dict[str, str] | None = None, client=("10.0.0.1", 12345)) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in (headers or {}).items()
        ],
        "client": client,
    }
    return Request(scope)


def test_prefers_the_header_set_by_the_gateway() -> None:
    request = _request({"x-real-ip": "203.0.113.7", "x-forwarded-for": "spoofed, 10.0.0.1"})
    assert get_client_ip(request) == "203.0.113.7"


def test_falls_back_to_the_right_most_forwarded_entry() -> None:
    request = _request({"x-forwarded-for": "1.2.3.4, 203.0.113.9"})
    assert get_client_ip(request) == "203.0.113.9"


def test_falls_back_to_the_direct_peer() -> None:
    assert get_client_ip(_request()) == "10.0.0.1"


def test_handles_a_missing_client() -> None:
    assert get_client_ip(_request(client=None)) == "127.0.0.1"


def test_rate_limiter_enforces_the_window() -> None:
    now = {"value": 100.0}
    limiter = WindowRateLimiter(2, window_seconds=60.0, clock=lambda: now["value"])
    assert limiter.allow("user-1") is True
    assert limiter.allow("user-1") is True
    assert limiter.allow("user-1") is False
    assert limiter.allow("user-2") is True


def test_rate_limiter_window_rolls_over() -> None:
    now = {"value": 0.0}
    limiter = WindowRateLimiter(1, window_seconds=10.0, clock=lambda: now["value"])
    assert limiter.allow("key") is True
    assert limiter.allow("key") is False
    now["value"] = 11.0
    assert limiter.allow("key") is True


def test_rate_limiter_reset_clears_one_key() -> None:
    limiter = WindowRateLimiter(1, window_seconds=10.0, clock=lambda: 0.0)
    assert limiter.allow("key") is True
    assert limiter.allow("key") is False
    limiter.reset("key")
    assert limiter.allow("key") is True
