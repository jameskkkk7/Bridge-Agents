import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addEdge,
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection,
  type NodeTypes,
  type OnSelectionChangeParams,
  type ReactFlowInstance,
} from "@xyflow/react";
import {
  Bot,
  Eye,
  LayoutGrid,
  PenTool,
  Play,
  RotateCcw,
  Save,
  Search,
  Shield,
  Square,
  Terminal,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { deleteJson, errorText, getJson, putJson } from "@/api";
import { useLanguage } from "@/i18n";
import GraphNodeView from "./GraphNodeView";
import NodeInspector from "./NodeInspector";
import {
  autoLayout,
  configToFlow,
  connectEdge,
  defaultConfig,
  flowToConfig,
  newEdgeId,
  newNodeId,
  snap,
  validateFlow,
  type GraphConfigDto,
  type GraphFlowEdge,
  type GraphFlowNode,
  type GraphNodeKind,
  type ToolInfo,
} from "./model";

const NODE_ICONS: Record<GraphNodeKind, typeof Bot> = {
  start: Play,
  end: Square,
  system: Terminal,
  retrieval: Search,
  agent: Bot,
  tools: Wrench,
  custom: PenTool,
  sanitize: Shield,
  review: Eye,
};

const PALETTE: GraphNodeKind[] = [
  "system",
  "retrieval",
  "agent",
  "tools",
  "review",
  "custom",
  "sanitize",
  "start",
  "end",
];

const MINIMAP_COLORS: Record<GraphNodeKind, string> = {
  start: "#94a3b8",
  end: "#94a3b8",
  system: "#6366f1",
  retrieval: "#10b981",
  agent: "#818cf8",
  tools: "#f59e0b",
  custom: "#8b5cf6",
  sanitize: "#f43f5e",
  review: "#f97316",
};

const nodeTypes = { graphNode: GraphNodeView } as NodeTypes;

export default function GraphEditor({ token }: { token: string }) {
  const { t } = useLanguage();
  const [nodes, setNodes, onNodesChange] = useNodesState<GraphFlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<GraphFlowEdge>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [instance, setInstance] = useState<
    ReactFlowInstance<GraphFlowNode, GraphFlowEdge> | null
  >(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const inspectorRef = useRef<HTMLDivElement>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [config, toolList] = await Promise.all([
        getJson<GraphConfigDto>("/admin/runtime-config/agent-graph-config", token),
        getJson<ToolInfo[]>("/admin/runtime-config/agent-tools", token),
      ]);
      const flow = configToFlow(config);
      setNodes(flow.nodes);
      setEdges(flow.edges);
      setTools(toolList);
      setSelectedId(null);
      setError("");
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setLoading(false);
    }
  }, [token, setEdges, setNodes]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Nodes arrive asynchronously, so the initial fitView prop runs on an empty
  // canvas. Fit again once the real graph is on screen (and after add/delete).
  useEffect(() => {
    if (loading || !instance || nodes.length === 0) return;
    const timer = window.setTimeout(
      () => void instance.fitView({ padding: 0.2, duration: 200 }),
      60,
    );
    return () => window.clearTimeout(timer);
  }, [loading, instance, nodes.length]);

  const selectedNode = nodes.find((node) => node.id === selectedId) ?? null;

  // The inspector sits below the canvas; make sure selecting a node reveals
  // its settings instead of leaving the operator looking at the canvas.
  useEffect(() => {
    if (!selectedId) return;
    const element = inspectorRef.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    if (rect.top < window.innerHeight - 120) return;
    element.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [selectedId]);

  const onSelectionChange = useCallback((params: OnSelectionChangeParams) => {
    setSelectedId(params.nodes[0]?.id ?? null);
  }, []);

  const updateNode = useCallback(
    (id: string, patch: Record<string, unknown>) => {
      setNodes((current) =>
        current.map((node) =>
          node.id === id
            ? {
                ...node,
                data: { ...node.data, config: { ...node.data.config, ...patch } },
              }
            : node,
        ),
      );
    },
    [setNodes],
  );

  const deleteNode = useCallback(
    (id: string) => {
      setNodes((current) => current.filter((node) => node.id !== id));
      setEdges((current) => current.filter((edge) => edge.source !== id && edge.target !== id));
      setSelectedId(null);
    },
    [setEdges, setNodes],
  );

  const addNode = useCallback(
    (kind: GraphNodeKind) => {
      if (kind === "start" && nodes.some((node) => node.data.kind === "start")) return;
      if (kind === "end" && nodes.some((node) => node.data.kind === "end")) return;
      const rect = canvasRef.current?.getBoundingClientRect();
      const center =
        rect && instance
          ? instance.screenToFlowPosition({
              x: rect.left + rect.width / 2,
              y: rect.top + Math.min(rect.height / 2, 260),
            })
          : null;
      const maxX = nodes.reduce((max, node) => Math.max(max, node.position.x), 60);
      const baseY = nodes.reduce((sum, node) => sum + node.position.y, 0) / Math.max(1, nodes.length);
      const position = center
        ? { x: snap(center.x), y: snap(center.y) }
        : kind === "start"
          ? { x: 60, y: 200 }
          : { x: snap(maxX + 240), y: snap(kind === "end" ? baseY : baseY + 120) };
      const id = newNodeId(kind);
      setNodes((current) => [
        ...current.map((node) => ({ ...node, selected: false })),
        {
          id,
          type: "graphNode",
          position,
          selected: true,
          deletable: kind !== "start" && kind !== "end",
          data: { kind, config: defaultConfig(kind) },
        },
      ]);
      setSelectedId(id);
      setNotice("");
    },
    [nodes, setNodes],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      const edge = connectEdge(
        connection.source,
        connection.target,
        connection.sourceHandle ?? null,
        newEdgeId(),
      );
      setEdges((current) => {
        const condition = edge.data?.condition;
        if (
          condition &&
          current.some(
            (candidate) =>
              candidate.source === edge.source && candidate.data?.condition === condition,
          )
        ) {
          return current;
        }
        return addEdge(edge, current);
      });
    },
    [setEdges],
  );

  const handleDeleteNodes = useCallback(
    (deleted: GraphFlowNode[]) => {
      const removed = new Set(deleted.map((node) => node.id));
      setEdges((current) =>
        current.filter((edge) => !removed.has(edge.source) && !removed.has(edge.target)),
      );
      setSelectedId(null);
    },
    [setEdges],
  );

  const save = async () => {
    setError("");
    setNotice("");
    const issue = validateFlow(nodes, edges);
    if (issue) {
      setError(t(issue.key, issue.vars));
      return;
    }
    setSaving(true);
    try {
      await putJson(
        "/admin/runtime-config/agent-graph-config",
        flowToConfig(nodes, edges),
        token,
      );
      setNotice(t("flow.saved"));
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    if (!window.confirm(t("flow.resetConfirm"))) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await deleteJson("/admin/runtime-config/agent-graph-config", token);
      await reload();
      setNotice(t("flow.resetDone"));
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setSaving(false);
    }
  };

  const applyLayout = () => {
    setNodes((current) => autoLayout(current, edges));
    window.setTimeout(() => void instance?.fitView({ padding: 0.15, duration: 250 }), 60);
  };

  const minimapColor = useMemo(
    () => (node: GraphFlowNode) => MINIMAP_COLORS[node.data.kind] ?? "#94a3b8",
    [],
  );

  if (loading) {
    return (
      <Card className="flex min-h-64 items-center justify-center p-10 text-sm text-muted-foreground">
        {t("common.loading")}
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-auto hidden text-xs text-muted-foreground sm:inline">
          {t("graph.toolbarHint")}
        </span>
        <Button variant="outline" size="sm" onClick={applyLayout}>
          <LayoutGrid />
          {t("graph.autoLayout")}
        </Button>
        <Button variant="outline" size="sm" disabled={saving} onClick={() => void reset()}>
          <RotateCcw />
          {t("common.reset")}
        </Button>
        <Button size="sm" disabled={saving} onClick={() => void save()}>
          <Save />
          {saving ? t("graph.saving") : t("flow.save")}
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {notice && (
        <div className="rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
          {notice}
        </div>
      )}

      <div className="flex flex-col gap-3">
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center gap-1.5 border-b border-border p-3">
            <Badge variant="outline" className="mr-1">
              {t("graph.palette")}
            </Badge>
            {PALETTE.map((kind) => {
              const Icon = NODE_ICONS[kind];
              const taken =
                (kind === "start" || kind === "end") &&
                nodes.some((node) => node.data.kind === kind);
              return (
                <Button
                  key={kind}
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 px-2 text-xs"
                  disabled={taken}
                  onClick={() => addNode(kind)}
                >
                  <Icon className="size-3.5" />
                  {t(`graph.kind.${kind}`)}
                </Button>
              );
            })}
          </div>
          <div ref={canvasRef} className="h-[52vh] min-h-[420px] w-full">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onSelectionChange={onSelectionChange}
              onInit={setInstance}
              onNodesDelete={handleDeleteNodes}
              fitView
              proOptions={{ hideAttribution: true }}
              fitViewOptions={{ padding: 0.2 }}
              minZoom={0.3}
              maxZoom={1.6}
              deleteKeyCode={["Backspace", "Delete"]}
              className="rounded-b-xl"
            >
              <Background gap={20} size={1} />
              <Controls showInteractive={false} />
              <MiniMap
                pannable
                zoomable
                nodeColor={minimapColor}
                className="hidden sm:block"
                maskColor="color-mix(in srgb, var(--background) 70%, transparent)"
              />
            </ReactFlow>
          </div>
        </Card>

        <div ref={inspectorRef}>
          <NodeInspector
            node={selectedNode}
            tools={tools}
            onChange={updateNode}
            onDelete={deleteNode}
          />
        </div>
      </div>
    </div>
  );
}

