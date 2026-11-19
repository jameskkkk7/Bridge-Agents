import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import SelectMenu from "@/components/ui/select-menu";
import { Textarea } from "@/components/ui/textarea";
import { useLanguage } from "@/i18n";

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function numberValue(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/**
 * Numeric field that keeps a string draft while typing.
 *
 * Converting every keystroke with ``Number("")`` stored ``0`` whenever the box
 * was cleared (and a threshold of 0 flags every reply). The draft only commits
 * a parsed value; on blur an empty or invalid draft falls back to the default
 * and out-of-range values are clamped.
 */
function NumberField({
  id,
  label,
  value,
  fallback,
  min,
  max,
  integer = false,
  onCommit,
}: {
  id: string;
  label: string;
  value: number;
  fallback: number;
  min: number;
  max: number;
  integer?: boolean;
  onCommit: (value: number) => void;
}) {
  const [draft, setDraft] = useState<string>(String(value));
  const lastValid = useRef<number>(value);

  useEffect(() => {
    lastValid.current = value;
    setDraft(String(value));
  }, [value]);

  const commit = (raw: string) => {
    const parsed = Number(raw);
    if (raw.trim() === "" || !Number.isFinite(parsed)) {
      // Do not write 0 (a threshold of 0 flags every reply): clamp the last
      // valid value and persist it so a blurred empty field cannot leave an
      // out-of-range value behind.
      const restored = integer
        ? Math.round(Math.min(max, Math.max(min, lastValid.current)))
        : Math.min(max, Math.max(min, lastValid.current));
      lastValid.current = restored;
      setDraft(String(restored));
      onCommit(restored);
      return;
    }
    const clamped = Math.min(max, Math.max(min, parsed));
    const next = integer ? Math.round(clamped) : clamped;
    lastValid.current = next;
    setDraft(String(next));
    onCommit(next);
  };

  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="text"
        inputMode={integer ? "numeric" : "decimal"}
        autoComplete="off"
        value={draft}
        onChange={(event) => {
          const next = event.target.value;
          setDraft(next);
          const parsed = Number(next);
          if (
            next.trim() !== "" &&
            Number.isFinite(parsed) &&
            (!integer || Number.isInteger(parsed))
          ) {
            onCommit(parsed);
          }
        }}
        onBlur={() => commit(draft)}
        onKeyDown={(event) => {
          if (event.key === "Enter") commit(draft);
        }}
      />
    </div>
  );
}

export default function ProviderModerationFields({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (patch: Record<string, unknown>) => void;
}) {
  const { t } = useLanguage();
  const update = onChange;
  const provider = stringValue(config.provider) || "openai";
  const placeholder =
    provider === "azure"
      ? "https://<resource>.cognitiveservices.azure.com"
      : provider === "perspective"
        ? "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
        : provider === "aliyun"
          ? "https://green-cip.cn-shanghai.aliyuncs.com"
          : provider === "tencent"
            ? "https://tms.tencentcloudapi.com"
            : "https://api.openai.com/v1";

  return (
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
            <Label htmlFor="node-provider-type">{t("graph.field.providerType")}</Label>
            <SelectMenu
              id="node-provider-type"
              value={provider}
              onChange={(value) => update({ provider: value })}
              options={[
                { value: "openai", label: t("graph.provider.openai") },
                { value: "azure", label: t("graph.provider.azure") },
                { value: "perspective", label: t("graph.provider.perspective") },
                { value: "aliyun", label: t("graph.provider.aliyun") },
                { value: "tencent", label: t("graph.provider.tencent") },
              ]}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="node-provider-url">{t("graph.field.providerBaseUrl")}</Label>
            <Input
              id="node-provider-url"
              value={stringValue(config.provider_base_url)}
              placeholder={placeholder}
              onChange={(event) => update({ provider_base_url: event.target.value })}
            />
          </div>

          {provider === "openai" && (
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
              <NumberField
                id="node-provider-timeout"
                label={t("graph.field.providerTimeout")}
                value={numberValue(config.provider_timeout, 5)}
                fallback={5}
                min={0.5}
                max={30}
                onCommit={(value) => update({ provider_timeout: value })}
              />
            </div>
          )}

          {provider === "azure" && (
            <div className="grid grid-cols-3 gap-2">
              <div className="grid gap-1.5">
                <Label htmlFor="node-provider-version">{t("graph.field.azureApiVersion")}</Label>
                <Input
                  id="node-provider-version"
                  value={stringValue(config.provider_api_version)}
                  placeholder="2024-09-01"
                  onChange={(event) => update({ provider_api_version: event.target.value })}
                />
              </div>
              <NumberField
                id="node-provider-severity"
                label={t("graph.field.azureSeverity")}
                value={numberValue(config.provider_severity, 2)}
                fallback={2}
                min={1}
                max={7}
                integer
                onCommit={(value) => update({ provider_severity: value })}
              />
              <NumberField
                id="node-provider-timeout"
                label={t("graph.field.providerTimeout")}
                value={numberValue(config.provider_timeout, 5)}
                fallback={5}
                min={0.5}
                max={30}
                onCommit={(value) => update({ provider_timeout: value })}
              />
            </div>
          )}

          {provider === "aliyun" && (
            <div className="grid grid-cols-3 gap-2">
              <div className="grid gap-1.5">
                <Label htmlFor="node-provider-region">{t("graph.field.aliyunRegion")}</Label>
                <Input
                  id="node-provider-region"
                  value={stringValue(config.provider_region)}
                  placeholder="cn-shanghai"
                  onChange={(event) => update({ provider_region: event.target.value })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="node-provider-service">{t("graph.field.aliyunService")}</Label>
                <Input
                  id="node-provider-service"
                  value={stringValue(config.provider_service)}
                  placeholder="comment_detection"
                  onChange={(event) => update({ provider_service: event.target.value })}
                />
              </div>
              <NumberField
                id="node-provider-timeout"
                label={t("graph.field.providerTimeout")}
                value={numberValue(config.provider_timeout, 5)}
                fallback={5}
                min={0.5}
                max={30}
                onCommit={(value) => update({ provider_timeout: value })}
              />
            </div>
          )}

          {provider === "tencent" && (
            <div className="grid grid-cols-3 gap-2">
              <div className="grid gap-1.5">
                <Label htmlFor="node-provider-region">{t("graph.field.tencentRegion")}</Label>
                <Input
                  id="node-provider-region"
                  value={stringValue(config.provider_region)}
                  placeholder="ap-guangzhou"
                  onChange={(event) => update({ provider_region: event.target.value })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="node-provider-biz-type">{t("graph.field.tencentBizType")}</Label>
                <Input
                  id="node-provider-biz-type"
                  value={stringValue(config.provider_biz_type)}
                  placeholder="TencentCloudDefault"
                  onChange={(event) => update({ provider_biz_type: event.target.value })}
                />
              </div>
              <NumberField
                id="node-provider-timeout"
                label={t("graph.field.providerTimeout")}
                value={numberValue(config.provider_timeout, 5)}
                fallback={5}
                min={0.5}
                max={30}
                onCommit={(value) => update({ provider_timeout: value })}
              />
            </div>
          )}

          {provider === "perspective" && (
            <div className="grid grid-cols-3 gap-2">
              <NumberField
                id="node-provider-threshold"
                label={t("graph.field.perspectiveThreshold")}
                value={numberValue(config.provider_threshold, 0.7)}
                fallback={0.7}
                min={0.01}
                max={1}
                onCommit={(value) => update({ provider_threshold: value })}
              />
              <div className="grid gap-1.5">
                <Label htmlFor="node-provider-language">
                  {t("graph.field.perspectiveLanguage")}
                </Label>
                <Input
                  id="node-provider-language"
                  value={stringValue(config.provider_language) || "en"}
                  onChange={(event) => update({ provider_language: event.target.value })}
                />
              </div>
              <NumberField
                id="node-provider-timeout"
                label={t("graph.field.providerTimeout")}
                value={numberValue(config.provider_timeout, 5)}
                fallback={5}
                min={0.5}
                max={30}
                onCommit={(value) => update({ provider_timeout: value })}
              />
            </div>
          )}

          <div className="grid gap-1.5">
            <Label htmlFor="node-provider-fallback">{t("graph.field.providerFallback")}</Label>
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
              onChange={(event) => update({ provider_fail_open: event.target.checked })}
              className="size-4 accent-[var(--primary)]"
            />
            {t("graph.field.providerFailOpen")}
          </Label>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {provider === "azure"
              ? t("graph.field.providerHintAzure")
              : provider === "perspective"
                ? t("graph.field.providerHintPerspective")
                : provider === "aliyun"
                  ? t("graph.field.providerHintAliyun")
                  : provider === "tencent"
                    ? t("graph.field.providerHintTencent")
                    : t("graph.field.providerHint")}
          </p>
        </>
      )}
    </div>
  );
}
