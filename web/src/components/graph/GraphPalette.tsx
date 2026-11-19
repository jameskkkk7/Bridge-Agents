import {
  Bot,
  Eye,
  PenTool,
  Play,
  Search,
  Shield,
  Square,
  Terminal,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/i18n";
import type { GraphFlowNode, GraphNodeKind } from "./model";

export const NODE_ICONS: Record<GraphNodeKind, typeof Bot> = {
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

export const PALETTE: GraphNodeKind[] = [
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

export default function GraphPalette({
  nodes,
  onAdd,
}: {
  nodes: GraphFlowNode[];
  onAdd: (kind: GraphNodeKind) => void;
}) {
  const { t } = useLanguage();
  return (
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
            onClick={() => onAdd(kind)}
          >
            <Icon className="size-3.5" />
            {t(`graph.kind.${kind}`)}
          </Button>
        );
      })}
    </div>
  );
}
