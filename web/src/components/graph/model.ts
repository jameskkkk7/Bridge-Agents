import { MarkerType, type Edge, type Node } from "@xyflow/react";

export type GraphNodeKind =
  | "start"
  | "end"
  | "system"
  | "retrieval"
  | "agent"
  | "tools"
  | "custom"
  | "sanitize"
  | "review";

export interface GraphNodeConfig {
  id: string;
  type: GraphNodeKind;
  config: Record<string, unknown>;
}

export interface GraphEdgeConfig {
  id?: string;
  source: string;
  target: string;
  condition?: string | null;
  source_handle?: string | null;
  target_handle?: string | null;
}

export interface GraphConfigDto {
  nodes: GraphNodeConfig[];
  edges: GraphEdgeConfig[];
}

export interface GraphNodeData extends Record<string, unknown> {
  kind: GraphNodeKind;
  config: Record<string, unknown>;
}

export type GraphFlowNode = Node<GraphNodeData, "graphNode">;
export type GraphFlowEdge = Edge<{ condition: string | null }>;

export interface ToolInfo {
  name: string;
  description: string;
}

export const NODE_KINDS: GraphNodeKind[] = [
  "start",
  "end",
  "system",
  "retrieval",
  "agent",
  "tools",
  "custom",
  "sanitize",
  "review",
];

export const RESERVED_IDS: Partial<Record<GraphNodeKind, string>> = {
  start: "__start__",
  end: "__end__",
};

export const CONDITION_OPTIONS: Partial<Record<GraphNodeKind, string[]>> = {
  agent: ["respond", "tool_call"],
  review: ["pass", "block"],
};

export const GRID = 20;

export function snap(value: number): number {
  return Math.round(value / GRID) * GRID;
}

export function newEdgeId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `edge_${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`;
  }
  return `edge_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

export function newNodeId(kind: GraphNodeKind): string {
  if (RESERVED_IDS[kind]) return RESERVED_IDS[kind] as string;
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `${kind}_${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`;
  }
  return `${kind}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

export function defaultConfig(kind: GraphNodeKind): Record<string, unknown> {
  switch (kind) {
    case "retrieval":
      return { top_k: 4, min_score: 0.12 };
    case "tools":
      return { tools: [] };
    case "review":
      return { on_block: "fallback", max_retries: 0, fallback_message: "" };
    case "sanitize":
      return { banned_words: "", replacement: "***" };
    case "system":
    case "custom":
      return { system_prompt: "" };
    default:
      return {};
  }
}

function numberOr(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function layoutPositions(nodes: GraphNodeConfig[], edges: GraphEdgeConfig[]) {
  const positions = new Map<string, { x: number; y: number }>();
  const existing = new Set<string>();
  for (const node of nodes) {
    const x = node.config?.x;
    const y = node.config?.y;
    if (typeof x === "number" && typeof y === "number") {
      positions.set(node.id, { x, y });
      existing.add(node.id);
    }
  }

  const start = nodes.find((node) => node.type === "start")?.id;
  const outgoing = new Map<string, string[]>();
  for (const edge of edges) {
    const list = outgoing.get(edge.source) ?? [];
    list.push(edge.target);
    outgoing.set(edge.source, list);
  }
  const depth = new Map<string, number>();
  if (start) {
    depth.set(start, 0);
    const queue = [start];
    const seen = new Set([start]);
    while (queue.length > 0) {
      const current = queue.shift() as string;
      for (const next of outgoing.get(current) ?? []) {
        if (seen.has(next)) continue;
        seen.add(next);
        depth.set(next, (depth.get(current) ?? 0) + 1);
        queue.push(next);
      }
    }
  }
  const perLevel = new Map<number, number>();
  for (const node of nodes) {
    if (existing.has(node.id)) continue;
    const level = depth.get(node.id) ?? 0;
    const row = perLevel.get(level) ?? 0;
    perLevel.set(level, row + 1);
    positions.set(node.id, {
      x: 80 + (level % 3) * 260,
      y: 140 + Math.floor(level / 3) * 200 + row * 120,
    });
  }
  return positions;
}

export function conditionColor(condition: string | null): string | null {
  if (condition === "pass") return "var(--success)";
  if (condition === "block") return "var(--destructive)";
  return null;
}

function conditionMarker(condition: string | null) {
  const color = conditionColor(condition);
  return color
    ? { type: MarkerType.ArrowClosed as const, color }
    : { type: MarkerType.ArrowClosed as const };
}

export function configToFlow(config: GraphConfigDto): {
  nodes: GraphFlowNode[];
  edges: GraphFlowEdge[];
} {
  const positions = layoutPositions(config.nodes, config.edges);
  const nodes: GraphFlowNode[] = config.nodes.map((node) => ({
    id: node.id,
    type: "graphNode" as const,
    position: positions.get(node.id) ?? { x: 80, y: 120 },
    deletable: node.type !== "start" && node.type !== "end",
    data: {
      kind: node.type,
      config: { ...(node.config ?? {}) },
    },
  }));
  const edges: GraphFlowEdge[] = config.edges.map((edge, index) => {
    const condition = edge.condition ?? null;
    return {
      id: edge.id ?? `edge-${index}`,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.source_handle ?? undefined,
      targetHandle: edge.target_handle ?? undefined,
      label: condition ?? undefined,
      data: { condition },
      markerEnd: conditionMarker(condition),
      style: conditionColor(condition)
        ? { stroke: conditionColor(condition) as string, strokeWidth: 2 }
        : undefined,
      labelStyle: conditionColor(condition)
        ? { fill: conditionColor(condition) as string, fontWeight: 600 }
        : undefined,
      labelBgStyle: conditionColor(condition)
        ? { fill: "var(--card)", opacity: 0.9 }
        : undefined,
      type: "default",
    };
  });
  return { nodes, edges };
}

export function flowToConfig(
  nodes: GraphFlowNode[],
  edges: GraphFlowEdge[],
): GraphConfigDto {
  return {
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.data.kind,
      config: {
        ...node.data.config,
        x: snap(node.position.x),
        y: snap(node.position.y),
      },
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      condition: edge.data?.condition ?? null,
      source_handle: edge.sourceHandle ?? null,
      target_handle: edge.targetHandle ?? null,
    })),
  };
}

export function connectEdge(
  source: string,
  target: string,
  sourceHandle: string | null | undefined,
  id: string,
): GraphFlowEdge {
  const condition = sourceHandle ?? null;
  return {
    id,
    source,
    target,
    sourceHandle: sourceHandle ?? undefined,
    label: condition ?? undefined,
    data: { condition },
    markerEnd: conditionMarker(condition),
    style: conditionColor(condition)
      ? { stroke: conditionColor(condition) as string, strokeWidth: 2 }
      : undefined,
    labelStyle: conditionColor(condition)
      ? { fill: conditionColor(condition) as string, fontWeight: 600 }
      : undefined,
    labelBgStyle: conditionColor(condition)
      ? { fill: "var(--card)", opacity: 0.9 }
      : undefined,
    type: "default",
  };
}

export function autoLayout(
  nodes: GraphFlowNode[],
  edges: GraphFlowEdge[],
): GraphFlowNode[] {
  const outgoing = new Map<string, string[]>();
  for (const edge of edges) {
    const list = outgoing.get(edge.source) ?? [];
    list.push(edge.target);
    outgoing.set(edge.source, list);
  }
  const start = nodes.find((node) => node.data.kind === "start")?.id;
  const depth = new Map<string, number>();
  if (start) {
    depth.set(start, 0);
    const queue = [start];
    const seen = new Set([start]);
    while (queue.length > 0) {
      const current = queue.shift() as string;
      for (const next of outgoing.get(current) ?? []) {
        if (seen.has(next)) continue;
        seen.add(next);
        depth.set(next, (depth.get(current) ?? 0) + 1);
        queue.push(next);
      }
    }
  }
  const rows = new Map<number, number>();
  return nodes.map((node) => {
    const level = depth.get(node.id) ?? 0;
    const row = rows.get(level) ?? 0;
    rows.set(level, row + 1);
    return {
      ...node,
      position: {
        x: snap(80 + (level % 3) * 260),
        y: snap(140 + Math.floor(level / 3) * 200 + row * 120),
      },
    };
  });
}

export interface FlowIssue {
  key: string;
  vars?: Record<string, string>;
}

export function validateFlow(nodes: GraphFlowNode[], edges: GraphFlowEdge[]): FlowIssue | null {
  const ids = new Set<string>();
  let startCount = 0;
  let endCount = 0;
  let startId = "";
  let endId = "";
  for (const node of nodes) {
    if (ids.has(node.id)) return { key: "graph.error.duplicateId", vars: { id: node.id } };
    ids.add(node.id);
    if (node.data.kind === "start") {
      startCount += 1;
      startId = node.id;
    }
    if (node.data.kind === "end") {
      endCount += 1;
      endId = node.id;
    }
  }
  if (startCount === 0) return { key: "graph.error.startRequired" };
  if (startCount > 1) return { key: "graph.error.startMultiple" };
  if (endCount === 0) return { key: "graph.error.endRequired" };
  if (endCount > 1) return { key: "graph.error.endMultiple" };
  if (startId !== "__start__") return { key: "graph.error.reservedStart" };
  if (endId !== "__end__") return { key: "graph.error.reservedEnd" };

  const hasSystemPrompt = nodes.some((node) => {
    if (node.data.kind !== "system") return false;
    const prompt = node.data.config.system_prompt;
    return typeof prompt === "string" && prompt.trim().length > 0;
  });
  if (!hasSystemPrompt) return { key: "graph.error.systemPrompt" };

  const conditionsBySource = new Map<string, Set<string>>();
  const kindsBySource = new Map<string, boolean>();
  for (const edge of edges) {
    if (!ids.has(edge.source)) return { key: "graph.error.edgeMissing", vars: { id: edge.source } };
    if (!ids.has(edge.target)) return { key: "graph.error.edgeMissing", vars: { id: edge.target } };
    const sourceNode = nodes.find((node) => node.id === edge.source);
    const allowed = CONDITION_OPTIONS[sourceNode?.data.kind ?? "custom"] ?? [];
    const condition = edge.data?.condition ?? null;
    if (condition && !allowed.includes(condition)) {
      return {
        key: "graph.error.invalidCondition",
        vars: { id: edge.source, condition },
      };
    }
    const set = conditionsBySource.get(edge.source) ?? new Set<string>();
    if (condition) {
      if (set.has(condition)) {
        return {
          key: "graph.error.duplicateCondition",
          vars: { id: edge.source, condition },
        };
      }
      set.add(condition);
    }
    conditionsBySource.set(edge.source, set);
    const hadConditional = kindsBySource.get(edge.source);
    const isConditional = Boolean(condition);
    if (hadConditional !== undefined && hadConditional !== isConditional) {
      return { key: "graph.error.mixedEdges", vars: { id: edge.source } };
    }
    kindsBySource.set(edge.source, isConditional);
  }

  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    const list = adjacency.get(edge.source) ?? [];
    list.push(edge.target);
    adjacency.set(edge.source, list);
  }
  const visited = new Set<string>(["__start__"]);
  const queue = ["__start__"];
  while (queue.length > 0) {
    const current = queue.shift() as string;
    for (const next of adjacency.get(current) ?? []) {
      if (!visited.has(next)) {
        visited.add(next);
        queue.push(next);
      }
    }
  }
  if (!visited.has("__end__")) return { key: "graph.error.endUnreachable" };
  return null;
}

export function nodeSummary(kind: GraphNodeKind, config: Record<string, unknown>): string {
  if (kind === "system" || kind === "custom") {
    const prompt = typeof config.system_prompt === "string" ? config.system_prompt.trim() : "";
    return prompt.length > 60 ? `${prompt.slice(0, 60)}…` : prompt;
  }
  if (kind === "retrieval") {
    return `top_k ${numberOr(config.top_k, 4)} · min ${numberOr(config.min_score, 0.12)}`;
  }
  if (kind === "tools") {
    const tools = Array.isArray(config.tools) ? (config.tools as string[]) : [];
    return tools.length ? tools.join(", ") : "all tools";
  }
  if (kind === "sanitize") {
    const words = config.banned_words;
    return typeof words === "string" ? words : Array.isArray(words) ? words.join(", ") : "";
  }
  if (kind === "review") {
    return config.on_block === "pass_through" ? "pass through" : "fallback";
  }
  return "";
}
