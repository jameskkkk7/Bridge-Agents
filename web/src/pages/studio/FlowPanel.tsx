import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { deleteJson, errorText, getJson, putJson } from "@/api";
import { useLanguage } from "@/i18n";

interface GraphConfig {
  nodes: unknown[];
  edges: unknown[];
}

interface Diagram {
  type: string;
  diagram: string | null;
}

export default function FlowPanel({
  token,
  onError,
}: {
  token: string;
  onError: (message: string) => void;
}) {
  const { t } = useLanguage();
  const [configText, setConfigText] = useState("");
  const [mermaid, setMermaid] = useState("");
  const [status, setStatus] = useState("");

  const load = async () => {
    const config = await getJson<GraphConfig>("/admin/runtime-config/agent-graph-config", token);
    setConfigText(JSON.stringify(config, null, 2));
    const diagram = await getJson<Diagram>("/admin/runtime-config/agent-graph", token);
    setMermaid(diagram.diagram ?? "");
  };

  useEffect(() => {
    void load().catch((caught) => onError(errorText(caught)));
  }, [token]);

  const save = async () => {
    onError("");
    setStatus("");
    let parsed: GraphConfig;
    try {
      parsed = JSON.parse(configText) as GraphConfig;
    } catch (caught) {
      onError(t("flow.invalidJson", { message: errorText(caught) }));
      return;
    }
    try {
      await putJson("/admin/runtime-config/agent-graph-config", parsed, token);
      await load();
      setStatus(t("flow.saved"));
    } catch (caught) {
      onError(errorText(caught));
    }
  };

  const reset = async () => {
    onError("");
    setStatus("");
    try {
      await deleteJson("/admin/runtime-config/agent-graph-config", token);
      await load();
      setStatus(t("flow.resetDone"));
    } catch (caught) {
      onError(errorText(caught));
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-auto hidden text-xs text-muted-foreground sm:inline">
          {t("flow.toolbar")}
        </span>
        <Button variant="outline" size="sm" onClick={() => void reset()}>
          {t("common.reset")}
        </Button>
        <Button size="sm" onClick={() => void save()}>
          {t("flow.save")}
        </Button>
      </div>
      {status && (
        <div className="rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
          {status}
        </div>
      )}
      <div className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("flow.configTitle")}</CardTitle>
            <CardDescription>{t("flow.configHelp")}</CardDescription>
          </CardHeader>
          <CardContent>
            <Textarea
              spellCheck={false}
              value={configText}
              onChange={(event) => setConfigText(event.target.value)}
              className="min-h-[54vh] resize-y rounded-xl [field-sizing:fixed] bg-muted/40 font-mono text-xs leading-relaxed"
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("flow.previewTitle")}</CardTitle>
            <CardDescription>{t("flow.previewHelp")}</CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="scrollbar-thin min-h-[54vh] overflow-auto rounded-xl border border-border bg-muted/40 p-4 font-mono text-xs leading-relaxed text-foreground/90">
              {mermaid || t("common.loading")}
            </pre>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
