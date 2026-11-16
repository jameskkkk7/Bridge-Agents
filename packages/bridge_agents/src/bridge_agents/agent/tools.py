"""Agent tools: current time, a safe calculator and a local documentation search.

Tools live in a small registry so the admin API can list them and a graph can
bind a subset. Tools are only handed to the model when the saved graph routes
tool calls, which is decided by the pipeline, not by this module.
"""

from __future__ import annotations

import ast
import json
import operator
import re
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import tool

from bridge_agents.config import get_settings

_TOOL_REGISTRY: dict[str, object] = {}


def _docs_directory() -> Path:
    """Locate the documentation bundle without hard-coding an install layout."""
    configured = (get_settings().docs_dir or "").strip()
    if configured:
        return Path(configured)
    working_copy = Path.cwd() / "docs" / "kb"
    if working_copy.is_dir():
        return working_copy
    return Path(__file__).resolve().parents[4] / "docs" / "kb"


_MAX_EXPRESSION_LENGTH = 200
_MAX_POWER_BASE = 1_000_000
_MAX_POWER_EXPONENT = 100
_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def register(name: str):
    """Decorator registering a tool function under a stable name."""

    def decorator(function):
        _TOOL_REGISTRY[name] = function
        return function

    return decorator


def list_available_tools() -> list[dict[str, str]]:
    """Return name and description for every registered tool."""
    entries: list[dict[str, str]] = []
    for name, function in _TOOL_REGISTRY.items():
        description = getattr(function, "description", "") or ""
        entries.append({"name": name, "description": description.strip()})
    return entries


def get_tools() -> list:
    """Return the tool objects enabled through the environment settings."""
    settings = get_settings()
    if not settings.agent_tools_enabled:
        return []
    try:
        requested = json.loads(settings.agent_tools)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(requested, list):
        return []
    return [_TOOL_REGISTRY[name] for name in requested if name in _TOOL_REGISTRY]


@register("get_current_time")
@tool
def get_current_time(timezone: str = "") -> str:
    """Return the current date and time in the configured timezone.

    Args:
        timezone: Optional IANA timezone name such as "Europe/Berlin".
            Leave empty to use the deployment default.
    """
    settings = get_settings()
    zone_name = (timezone or "").strip() or settings.default_timezone or "UTC"
    if zone_name.upper() == "UTC":
        zone = UTC
    else:
        try:
            zone = ZoneInfo(zone_name)
        except (ZoneInfoNotFoundError, ValueError):
            zone = UTC
            zone_name = "UTC"
    stamp = datetime.now(zone).strftime("%Y-%m-%d %H:%M:%S %Z")
    return f"{stamp} ({zone_name})"


def _evaluate_arithmetic(node: ast.AST) -> float | int:
    """Evaluate a restricted arithmetic syntax tree."""
    if isinstance(node, ast.Expression):
        return _evaluate_arithmetic(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("only numbers are supported")
        return node.value
    if isinstance(node, ast.BinOp):
        left = _evaluate_arithmetic(node.left)
        right = _evaluate_arithmetic(node.right)
        operation = _BINARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise ValueError(f"unsupported operator: {type(node.op).__name__}")
        if isinstance(node.op, ast.Pow):
            if abs(left) > _MAX_POWER_BASE or abs(right) > _MAX_POWER_EXPONENT:
                raise ValueError("power operands are too large")
        return operation(left, right)
    if isinstance(node, ast.UnaryOp):
        operation = _UNARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise ValueError(f"unsupported operator: {type(node.op).__name__}")
        return operation(_evaluate_arithmetic(node.operand))
    raise ValueError(f"unsupported syntax: {type(node).__name__}")


@register("calculate")
@tool
def calculate(expression: str) -> str:
    """Evaluate a basic arithmetic expression.

    Args:
        expression: Numbers combined with +, -, *, /, ** or parentheses.
    """
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        return "The expression is too long."
    try:
        tree = ast.parse(expression, mode="eval")
        return str(_evaluate_arithmetic(tree))
    except (SyntaxError, ValueError, ZeroDivisionError, TypeError) as exc:
        return f"Cannot evaluate the expression: {exc}"


def _document_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or fallback
    return fallback


def _sections(markdown: str) -> list[tuple[str, str]]:
    """Split a markdown document into (heading, body) pairs."""
    sections: list[tuple[str, str]] = []
    heading = "Overview"
    body: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if body:
                sections.append((heading, "\n".join(body).strip()))
            heading = line[3:].strip() or heading
            body = []
        elif not line.startswith("# "):
            body.append(line)
    if body:
        sections.append((heading, "\n".join(body).strip()))
    return sections


_WORD_PATTERN = re.compile(r"[a-z0-9]+")


def _search_terms(query: str) -> list[str]:
    return [term for term in _WORD_PATTERN.findall(query.lower()) if len(term) >= 2]


@register("search_docs")
@tool
def search_docs(query: str) -> str:
    """Search the bundled product documentation for sections relevant to the question.

    Args:
        query: Keywords or a question, for example "Widget Pro activation".
    """
    documents: list[tuple[str, str]] = []
    docs_dir = _docs_directory()
    if docs_dir.is_dir():
        for path in sorted(docs_dir.glob("*.md")):
            documents.append((path.name, path.read_text(encoding="utf-8")))
    if not documents:
        return "The documentation bundle is not available in this deployment."

    titles = {name: _document_title(text, name) for name, text in documents}
    if not query.strip():
        listing = "\n".join(f"- {name}: {titles[name]}" for name, _ in documents)
        return f"Available documentation:\n{listing}"

    terms = _search_terms(query)
    matches: list[tuple[int, str, str, str]] = []
    for name, text in documents:
        for heading, body in _sections(text):
            haystack = f"{heading}\n{body}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score:
                matches.append((score, name, heading, body))
    if not matches:
        available = ", ".join(name for name, _ in documents)
        return f"No documentation matched '{query}'. Available documents: {available}"

    matches.sort(key=lambda item: item[0], reverse=True)
    replies: list[str] = []
    for _, name, heading, body in matches[:2]:
        excerpt = " ".join(body.split())
        if len(excerpt) > 600:
            excerpt = excerpt[:600].rstrip() + "..."
        replies.append(f"[{titles[name]} - {heading}]\n{excerpt}")
    return "\n\n".join(replies)
