"""Bundled agent tools."""

from __future__ import annotations

import re

from app.core.agent.tools import (
    calculate,
    get_current_time,
    get_tools,
    list_available_tools,
    search_docs,
)


def test_registry_lists_the_bundled_tools() -> None:
    entries = list_available_tools()
    names = {entry["name"] for entry in entries}
    assert {"get_current_time", "calculate", "search_docs"} <= names
    assert all(entry["description"] for entry in entries)


def test_tools_are_disabled_by_default() -> None:
    assert get_tools() == []


def test_calculate_handles_arithmetic() -> None:
    assert calculate.invoke("2 + 3 * 4") == "14"
    assert calculate.invoke("(2 + 3) * 4") == "20"
    assert calculate.invoke("-2 ** 10") == "-1024"


def test_calculate_rejects_unsafe_syntax() -> None:
    assert "Cannot evaluate" in calculate.invoke("__import__('os').system('id')")
    assert "Cannot evaluate" in calculate.invoke("True + 1")
    assert "Cannot evaluate" in calculate.invoke("1 +")
    assert "Cannot evaluate" in calculate.invoke("1 / 0")
    assert "too long" in calculate.invoke("1 + " * 120 + "1")
    assert "too large" in calculate.invoke("1000000 ** 101")


def test_get_current_time_defaults_to_utc() -> None:
    value = get_current_time.invoke("")
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value)
    assert value.endswith("(UTC)")


def test_get_current_time_accepts_a_timezone() -> None:
    value = get_current_time.invoke("Europe/Berlin")
    assert value.endswith("(Europe/Berlin)")


def test_get_current_time_falls_back_for_unknown_zones() -> None:
    assert get_current_time.invoke("Nowhere/Land").endswith("(UTC)")


def test_search_docs_returns_relevant_sections() -> None:
    result = search_docs.invoke("refund policy")
    assert "Refund policy" in result
    assert "14 days" in result


def test_search_docs_blank_query_lists_documents() -> None:
    result = search_docs.invoke("")
    assert "widget-pro.md" in result
    assert "widget-cloud.md" in result


def test_search_docs_reports_misses() -> None:
    assert "No documentation matched" in search_docs.invoke("zebra unicorn")
