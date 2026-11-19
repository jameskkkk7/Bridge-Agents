/** Left-to-right level layout: the main flow goes right, siblings stack vertically. */
export interface LayoutNode {
  id: string;
  config?: Record<string, unknown> | null;
}

export interface LayoutEdge {
  source: string;
  target: string;
}

export interface Point {
  x: number;
  y: number;
}

const COLUMN_GAP = 220;
const ROW_GAP = 150;
const LEFT = 70;
const CENTER_Y = 210;
const GRID = 20;

function snap(value: number): number {
  return Math.round(value / GRID) * GRID;
}

function depths(nodes: LayoutNode[], edges: LayoutEdge[], startId?: string): Map<string, number> {
  const outgoing = new Map<string, string[]>();
  for (const edge of edges) {
    const list = outgoing.get(edge.source) ?? [];
    list.push(edge.target);
    outgoing.set(edge.source, list);
  }
  const depth = new Map<string, number>();
  const first = startId ?? nodes[0]?.id;
  if (first) {
    depth.set(first, 0);
    const queue = [first];
    const seen = new Set([first]);
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
  return depth;
}

/**
 * Compute horizontal levels. When `preserve` is true, existing x/y coordinates
 * are kept and only unpositioned nodes are placed; otherwise every node moves
 * to its level (the "auto layout" action).
 */
export function computeLayout(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  preserve: boolean,
  startId?: string,
): Map<string, Point> {
  const positions = new Map<string, Point>();
  if (preserve) {
    for (const node of nodes) {
      const x = node.config?.x;
      const y = node.config?.y;
      if (typeof x === "number" && typeof y === "number") positions.set(node.id, { x, y });
    }
  }
  const depth = depths(nodes, edges, startId);
  const levels = new Map<number, string[]>();
  for (const node of nodes) {
    if (positions.has(node.id)) continue;
    const level = depth.get(node.id) ?? 0;
    const group = levels.get(level) ?? [];
    group.push(node.id);
    levels.set(level, group);
  }
  for (const [level, ids] of levels) {
    const offset = ((ids.length - 1) * ROW_GAP) / 2;
    ids.forEach((id, index) => {
      positions.set(id, {
        x: snap(LEFT + level * COLUMN_GAP),
        y: snap(CENTER_Y - offset + index * ROW_GAP),
      });
    });
  }
  return positions;
}
