import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useLanguage } from "@/i18n";
import type { GraphFlowNode, GraphNodeKind, ToolInfo } from "./model";

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function numberValue(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export default function NodeInspector({
  node,
  tools,
  onChange,
  onDelete,
}: {
  node: GraphFlowNode | null;
  tools: ToolInfo[];
  onChange: (id: string, patch: Record<string, unknown>) => void;
  onDelete: (id: string) => void;
}) {
  const { t } = useLanguage();
  if (!node) {
    return (
      <Card className="min-h-[200px]">
        <CardHeader>
          <CardTitle>{t("graph.inspector")}</CardTitle>
        </CardHeader>
        <CardContent className="flex min-h-[120px] flex-1 items-center justify-center text-sm text-muted-foreground">
          {t("graph.selectHint")}
        </CardContent>
      </Card>
    );
  }

  const kind = node.data.kind as GraphNodeKind;
  const config = node.data.config;
  const update = (patch: Record<string, unknown>) => onChange(node.id, patch);
  const reserved = kind === "start" || kind === "end";
  const selectedTools = Array.isArray(config.tools) ? (config.tools as string[]) : [];

  return (
    <Card className="min-h-[200px]">
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>{t(`graph.kind.${kind}`)}</CardTitle>
          <CardDescription className="mt-1 font-mono text-[11px]">{node.id}</CardDescription>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          disabled={reserved}
          onClick={() => onDelete(node.id)}
          aria-label={t("graph.deleteNode")}
          className="text-muted-foreground hover:text-destructive"
        >
          <Trash2 />
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {(kind === "system" || kind === "custom") && (
          <div className="grid gap-1.5">
            <Label htmlFor="node-prompt">{t("graph.field.systemPrompt")}</Label>
            <Textarea
              id="node-prompt"
              value={stringValue(config.system_prompt)}
              onChange={(event) => update({ system_prompt: event.target.value })}
              className="min-h-32 leading-relaxed"
            />
          </div>
        )}

        {kind === "retrieval" && (
          <div className="grid grid-cols-2 gap-2">
            <div className="grid gap-1.5">
              <Label htmlFor="node-top-k">{t("graph.field.topK")}</Label>
              <Input
                id="node-top-k"
                type="number"
                min={1}
                max={20}
                value={numberValue(config.top_k, 4)}
                onChange={(event) => update({ top_k: Number(event.target.value) })}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="node-min-score">{t("graph.field.minScore")}</Label>
              <Input
                id="node-min-score"
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={numberValue(config.min_score, 0.12)}
                onChange={(event) => update({ min_score: Number(event.target.value) })}
              />
            </div>
          </div>
        )}

        {kind === "tools" && (
          <div className="grid gap-2">
            <Label>{t("graph.field.tools")}</Label>
            {tools.length === 0 && (
              <p className="text-xs text-muted-foreground">{t("graph.toolsEmpty")}</p>
            )}
            {tools.map((tool) => (
              <label
                key={tool.name}
                className="flex items-start gap-2 rounded-lg border border-border px-3 py-2 text-sm"
              >
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-[var(--primary)]"
                  checked={selectedTools.includes(tool.name)}
                  onChange={(event) => {
                    const next = event.target.checked
                      ? [...selectedTools, tool.name]
                      : selectedTools.filter((name) => name !== tool.name);
                    update({ tools: next });
                  }}
                />
                <span>
                  <span className="block font-mono text-xs">{tool.name}</span>
                  <span className="block text-xs text-muted-foreground">{tool.description}</span>
                </span>
              </label>
            ))}
          </div>
        )}

        {kind === "sanitize" && (
          <>
            <div className="grid gap-1.5">
              <Label htmlFor="node-banned">{t("graph.field.bannedWords")}</Label>
              <Input
                id="node-banned"
                value={stringValue(config.banned_words)}
                placeholder={t("graph.field.bannedWordsHint")}
                onChange={(event) => update({ banned_words: event.target.value })}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="node-replacement">{t("graph.field.replacement")}</Label>
              <Input
                id="node-replacement"
                value={stringValue(config.replacement) || "***"}
                onChange={(event) => update({ replacement: event.target.value })}
              />
            </div>

            <div className="grid gap-3 border-t border-border pt-4">
              <div className="text-xs font-semibold text-foreground">
                {t("graph.field.providerSection")}
              </div>
              <Label className="gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={config.provider_enabled === true}
                  onChange={(event) => update({ provider_enabled: event.target.checked })}
                  className="size-4 accent-[var(--primary)]"
                />
                {t("graph.field.providerEnabled")}
              </Label>

              {config.provider_enabled === true && (
                <>
                  <div className="grid gap-1.5">
                    <Label htmlFor="node-provider-url">{t("graph.field.providerBaseUrl")}</Label>
                    <Input
                      id="node-provider-url"
                      value={stringValue(config.provider_base_url)}
                      placeholder="https://api.openai.com/v1"
                      onChange={(event) => update({ provider_base_url: event.target.value })}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="grid gap-1.5">
                      <Label htmlFor="node-provider-model">{t("graph.field.providerModel")}</Label>
                      <Input
                        id="node-provider-model"
                        value={stringValue(config.provider_model)}
                        placeholder="omni-moderation-latest"
                        onChange={(event) => update({ provider_model: event.target.value })}
                      />
                    </div>
                    <div className="grid gap-1.5">
                      <Label htmlFor="node-provider-timeout">
                        {t("graph.field.providerTimeout")}
                      </Label>
                      <Input
                        id="node-provider-timeout"
                        type="number"
                        min={0.5}
                        max={30}
                        step={0.5}
                        value={numberValue(config.provider_timeout, 5)}
                        onChange={(event) =>
                          update({ provider_timeout: Number(event.target.value) })
                        }
                      />
                    </div>
                  </div>
                  <div className="grid gap-1.5">
                    <Label htmlFor="node-provider-fallback">
                      {t("graph.field.providerFallback")}
                    </Label>
                    <Textarea
                      id="node-provider-fallback"
                      value={stringValue(config.provider_fallback)}
                      onChange={(event) => update({ provider_fallback: event.target.value })}
                      className="min-h-16"
                    />
                  </div>
                  <Label className="gap-2 text-xs text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={config.provider_fail_open !== false}
                      onChange={(event) =>
                        update({ provider_fail_open: event.target.checked })
                      }
                      className="size-4 accent-[var(--primary)]"
                    />
                    {t("graph.field.providerFailOpen")}
                  </Label>
                  <p className="text-[11px] leading-relaxed text-muted-foreground">
                    {t("graph.field.providerHint")}
                  </p>
                </>
              )}
            </div>
          </>
        )}

        {kind === "review" && (
          <>
            <div className="grid gap-1.5">
              <Label htmlFor="node-review-prompt">{t("graph.field.reviewPrompt")}</Label>
              <Textarea
                id="node-review-prompt"
                value={stringValue(config.system_prompt)}
                onChange={(event) => update({ system_prompt: event.target.value })}
                className="min-h-24"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="grid gap-1.5">
                <Label htmlFor="node-on-block">{t("graph.field.onBlock")}</Label>
                <select
                  id="node-on-block"
                  value={stringValue(config.on_block) || "fallback"}
                  onChange={(event) => update({ on_block: event.target.value })}
                  className="h-9 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  <option value="fallback">{t("graph.onBlock.fallback")}</option>
                  <option value="pass_through">{t("graph.onBlock.pass_through")}</option>
                </select>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="node-max-retries">{t("graph.field.maxRetries")}</Label>
                <Input
                  id="node-max-retries"
                  type="number"
                  min={0}
                  max={10}
                  value={numberValue(config.max_retries, 0)}
                  onChange={(event) => update({ max_retries: Number(event.target.value) })}
                />
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="node-fallback">{t("graph.field.fallbackMessage")}</Label>
              <Textarea
                id="node-fallback"
                value={stringValue(config.fallback_message)}
                onChange={(event) => update({ fallback_message: event.target.value })}
                className="min-h-20"
              />
            </div>
          </>
        )}

        {(kind === "start" || kind === "end" || kind === "agent") && (
          <p className="text-xs text-muted-foreground">{t("graph.field.noConfig")}</p>
        )}

        <p className="text-[11px] text-muted-foreground">{t("graph.deleteEdgeHint")}</p>
      </CardContent>
    </Card>
  );
}
