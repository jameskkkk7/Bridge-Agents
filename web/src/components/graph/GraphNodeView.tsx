import type { NodeProps } from "@xyflow/react";
import { Handle, Position } from "@xyflow/react";
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

import { useLanguage } from "@/i18n";
import { nodeSummary, type GraphFlowNode, type GraphNodeKind } from "./model";

const ICONS: Record<GraphNodeKind, typeof Bot> = {
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

const TONES: Record<GraphNodeKind, string> = {
  start: "bg-muted text-muted-foreground",
  end: "bg-muted text-muted-foreground",
  system: "bg-primary/10 text-primary",
  retrieval: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  agent: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
  tools: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  custom: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
  sanitize: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
  review: "bg-orange-500/10 text-orange-700 dark:text-orange-400",
};

const handleClass = "!size-2.5 !border-2 !border-background !bg-primary";

export default function GraphNodeView({ data, selected }: NodeProps<GraphFlowNode>) {
  const { t } = useLanguage();
  const Icon = ICONS[data.kind];
  const summary = nodeSummary(data.kind, data.config);
  const isStart = data.kind === "start";
  const isEnd = data.kind === "end";
  const isAgent = data.kind === "agent";
  const isReview = data.kind === "review";

  return (
    <div
      className={`w-[200px] rounded-xl border bg-card px-3 py-3 text-card-foreground shadow-sm transition ${
        selected ? "border-primary ring-2 ring-primary/30" : "border-border"
      } ${isStart || isEnd ? "opacity-90" : ""}`}
    >
      {!isStart && <Handle type="target" position={Position.Left} className={handleClass} />}

      <div className="flex items-center gap-2">
        <span className={`flex size-8 shrink-0 items-center justify-center rounded-md ${TONES[data.kind]}`}>
          <Icon className="size-4" />
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{t(`graph.kind.${data.kind}`)}</div>
          <div className="truncate text-[10px] tracking-wide text-muted-foreground uppercase">
            {data.kind}
          </div>
        </div>
      </div>

      {summary && (
        <div className="mt-2 line-clamp-2 text-[11px] leading-snug text-muted-foreground">
          {summary}
        </div>
      )}

      {isAgent && (
        <>
          <Handle
            id="respond"
            type="source"
            position={Position.Right}
            style={{ top: "35%" }}
            className={`${handleClass} !bg-emerald-500`}
            title={t("graph.condition.respond")}
          />
          <Handle
            id="tool_call"
            type="source"
            position={Position.Right}
            style={{ top: "72%" }}
            className={`${handleClass} !bg-amber-500`}
            title={t("graph.condition.tool_call")}
          />
        </>
      )}

      {isReview && (
        <>
          <Handle
            id="pass"
            type="source"
            position={Position.Right}
            style={{ top: "35%" }}
            className={`${handleClass} !bg-emerald-500`}
            title={t("graph.condition.pass")}
          />
          <Handle
            id="block"
            type="source"
            position={Position.Right}
            style={{ top: "72%" }}
            className={`${handleClass} !bg-destructive`}
            title={t("graph.condition.block")}
          />
        </>
      )}

      {!isEnd && !isAgent && !isReview && (
        <Handle type="source" position={Position.Right} className={handleClass} />
      )}
    </div>
  );
}
