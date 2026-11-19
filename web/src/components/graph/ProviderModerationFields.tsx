import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useLanguage } from "@/i18n";

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function numberValue(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
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
            <select
              id="node-provider-type"
              value={provider}
              onChange={(event) => update({ provider: event.target.value })}
              className="h-9 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            >
              <option value="openai">{t("graph.provider.openai")}</option>
              <option value="azure">{t("graph.provider.azure")}</option>
              <option value="perspective">{t("graph.provider.perspective")}</option>
            </select>
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
              <div className="grid gap-1.5">
                <Label htmlFor="node-provider-timeout">{t("graph.field.providerTimeout")}</Label>
                <Input
                  id="node-provider-timeout"
                  type="number"
                  min={0.5}
                  max={30}
                  step={0.5}
                  value={numberValue(config.provider_timeout, 5)}
                  onChange={(event) => update({ provider_timeout: Number(event.target.value) })}
                />
              </div>
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
              <div className="grid gap-1.5">
                <Label htmlFor="node-provider-severity">{t("graph.field.azureSeverity")}</Label>
                <Input
                  id="node-provider-severity"
                  type="number"
                  min={0}
                  max={7}
                  value={numberValue(config.provider_severity, 2)}
                  onChange={(event) => update({ provider_severity: Number(event.target.value) })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="node-provider-timeout">{t("graph.field.providerTimeout")}</Label>
                <Input
                  id="node-provider-timeout"
                  type="number"
                  min={0.5}
                  max={30}
                  step={0.5}
                  value={numberValue(config.provider_timeout, 5)}
                  onChange={(event) => update({ provider_timeout: Number(event.target.value) })}
                />
              </div>
            </div>
          )}

          {provider === "perspective" && (
            <div className="grid grid-cols-3 gap-2">
              <div className="grid gap-1.5">
                <Label htmlFor="node-provider-threshold">
                  {t("graph.field.perspectiveThreshold")}
                </Label>
                <Input
                  id="node-provider-threshold"
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={numberValue(config.provider_threshold, 0.7)}
                  onChange={(event) => update({ provider_threshold: Number(event.target.value) })}
                />
              </div>
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
              <div className="grid gap-1.5">
                <Label htmlFor="node-provider-timeout">{t("graph.field.providerTimeout")}</Label>
                <Input
                  id="node-provider-timeout"
                  type="number"
                  min={0.5}
                  max={30}
                  step={0.5}
                  value={numberValue(config.provider_timeout, 5)}
                  onChange={(event) => update({ provider_timeout: Number(event.target.value) })}
                />
              </div>
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
                : t("graph.field.providerHint")}
          </p>
        </>
      )}
    </div>
  );
}
