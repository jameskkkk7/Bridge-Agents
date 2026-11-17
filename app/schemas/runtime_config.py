"""Schemas for the editable runtime configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NodeKind = Literal[
    "start", "end", "agent", "tools", "custom", "sanitize", "review", "system", "retrieval"
]


class GraphNode(BaseModel):
    """One node of the agent graph."""

    id: str = Field(min_length=1, description="Unique node identifier.")
    type: NodeKind = Field(description="Node kind.")
    config: dict = Field(default_factory=dict, description="Node specific settings.")


class GraphEdge(BaseModel):
    """One edge of the agent graph."""

    id: str | None = Field(default=None, description="Optional edge identifier.")
    source: str = Field(min_length=1, description="Source node id or __start__.")
    target: str = Field(min_length=1, description="Target node id or __end__.")
    condition: str | None = Field(
        default=None, description="Route key when this is a conditional edge."
    )
    source_handle: str | None = Field(default=None, description="Optional visual handle.")
    target_handle: str | None = Field(default=None, description="Optional visual handle.")


class AgentGraphConfig(BaseModel):
    """Editable agent graph definition."""

    nodes: list[GraphNode] = Field(description="Graph nodes.")
    edges: list[GraphEdge] = Field(description="Graph edges.")


class AgentGraphDiagram(BaseModel):
    """Rendered graph diagram."""

    type: str = Field(description="Diagram format, currently always mermaid.")
    diagram: str | None = Field(default=None, description="Mermaid source.")


class AgentToolInfo(BaseModel):
    """One tool that a graph node can bind."""

    name: str
    description: str = ""


class GraphConfigSaved(BaseModel):
    """Result of saving or resetting the graph configuration."""

    saved: bool
    deleted: bool = False
