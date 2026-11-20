import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
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
import SelectMenu from "@/components/ui/select-menu";
import { Textarea } from "@/components/ui/textarea";
import { deleteJson, errorText, getJson, putJson } from "@/api";
import { useLanguage } from "@/i18n";
import ModelPicker from "./ModelPicker";
import { MODEL_PROVIDERS, providerPreset } from "./model-presets";

interface ModelConfig {
  provider: string;
  base_url: string;
  model: string;
  api_version: string;
  temperature: number;
  timeout: number;
  max_retries: number;
  thinking_enabled: boolean;
  api_key_configured: boolean;
  api_key_source: "runtime" | "environment" | "none";
  source: "runtime" | "environment";
}

interface PromptView {
  system_prompt: string;
  source: "saved_graph" | "default_graph";
}

export default function SettingsPanel({
  token,
  onError,
}: {
  token: string;
  onError: (message: string) => void;
}) {
  const { t } = useLanguage();
  const [config, setConfig] = useState<ModelConfig | null>(null);
  const [provider, setProvider] = useState("openai");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiVersion, setApiVersion] = useState("2024-10-21");
  const [model, setModel] = useState("");
  const [temperature, setTemperature] = useState(1);
  const [timeout, setTimeout] = useState(60);
  const [maxRetries, setMaxRetries] = useState(3);
  const [thinking, setThinking] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [promptSource, setPromptSource] = useState<PromptView["source"]>("default_graph");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  const applyConfig = (value: ModelConfig) => {
    setConfig(value);
    setProvider(value.provider);
    setBaseUrl(value.base_url);
    setApiVersion(value.api_version || "2024-10-21");
    setModel(value.model);
    setTemperature(value.temperature);
    setTimeout(value.timeout);
    setMaxRetries(value.max_retries);
    setThinking(value.thinking_enabled);
    setApiKey("");
    setClearKey(false);
  };

  const load = async () => {
    const [modelConfig, promptView] = await Promise.all([
      getJson<ModelConfig>("/admin/runtime-config/model-config", token),
      getJson<PromptView>("/admin/runtime-config/agent-prompt", token),
    ]);
    applyConfig(modelConfig);
    setPrompt(promptView.system_prompt);
    setPromptSource(promptView.source);
  };

  useEffect(() => {
    void load().catch((caught) => onError(errorText(caught)));
  }, [token]);

  const chooseProvider = (id: string) => {
    setProvider(id);
    const preset = providerPreset(id);
    if (!preset || id === "custom") return;
    setBaseUrl(preset.baseUrl);
    setModel("");
    if (preset.apiVersion) setApiVersion(preset.apiVersion);
  };

  const saveModel = async () => {
    if (!model.trim()) {
      onError(t("settings.modelRequired"));
      return;
    }
    onError("");
    setNotice("");
    setBusy("model");
    try {
      const updated = await putJson<ModelConfig>(
        "/admin/runtime-config/model-config",
        {
          provider,
          base_url: baseUrl,
          model,
          api_version: apiVersion,
          temperature,
          timeout,
          max_retries: maxRetries,
          thinking_enabled: thinking,
          api_key: apiKey.trim() ? apiKey.trim() : null,
          clear_api_key: clearKey,
        },
        token,
      );
      applyConfig(updated);
      setNotice(t("settings.modelSaved"));
    } catch (caught) {
      onError(errorText(caught));
    } finally {
      setBusy("");
    }
  };

  const resetModel = async () => {
    onError("");
    setNotice("");
    setBusy("model");
    try {
      const reset = await deleteJson<ModelConfig>("/admin/runtime-config/model-config", token);
      applyConfig(reset);
      setNotice(t("settings.modelReset"));
    } catch (caught) {
      onError(errorText(caught));
    } finally {
      setBusy("");
    }
  };

  const savePrompt = async () => {
    if (!prompt.trim()) return;
    onError("");
    setNotice("");
    setBusy("prompt");
    try {
      const updated = await putJson<PromptView>(
        "/admin/runtime-config/agent-prompt",
        { system_prompt: prompt },
        token,
      );
      setPrompt(updated.system_prompt);
      setPromptSource(updated.source);
      setNotice(t("settings.promptSaved"));
    } catch (caught) {
      onError(errorText(caught));
    } finally {
      setBusy("");
    }
  };

  const keyPlaceholder =
    config?.api_key_configured && config.api_key_source === "runtime"
      ? t("settings.apiKeyPlaceholderSet")
      : t("settings.apiKeyPlaceholderEmpty");

  return (
    <div className="flex flex-col gap-3">
      {notice && (
        <div className="rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
          {notice}
        </div>
      )}
      <div className="grid items-start gap-3 lg:grid-cols-[1.05fr_1fr]">
        <Card>
          <CardHeader className="flex-row items-start justify-between gap-2">
            <div>
              <CardTitle>{t("settings.modelTitle")}</CardTitle>
              <CardDescription className="mt-1">{t("settings.modelHelp")}</CardDescription>
            </div>
            {config && (
              <Badge variant={config.source === "runtime" ? "accent" : "secondary"}>
                {config.source === "runtime"
                  ? t("settings.sourceRuntime")
                  : t("settings.sourceEnvironment")}
              </Badge>
            )}
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="model-provider">{t("settings.provider")}</Label>
              <SelectMenu
                id="model-provider"
                value={provider}
                onChange={chooseProvider}
                options={MODEL_PROVIDERS.map((preset) => ({
                  value: preset.id,
                  label: t(`settings.provider.${preset.id}`),
                }))}
              />
              <span className="text-xs text-muted-foreground">{t("settings.providerHelp")}</span>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="model-base-url">
                {provider === "azure" ? t("settings.azureEndpoint") : t("settings.baseUrl")}
              </Label>
              <Input
                id="model-base-url"
                value={baseUrl}
                placeholder={
                  provider === "azure"
                    ? "https://<resource>.openai.azure.com"
                    : "https://api.openai.com/v1"
                }
                onChange={(event) => setBaseUrl(event.target.value)}
              />
              {provider === "anthropic" && (
                <span className="text-xs text-warning">{t("settings.providerGatewayHint")}</span>
              )}
            </div>
            {provider === "azure" && (
              <div className="grid gap-1.5">
                <Label htmlFor="model-api-version">{t("settings.apiVersion")}</Label>
                <Input
                  id="model-api-version"
                  value={apiVersion}
                  placeholder="2024-10-21"
                  onChange={(event) => setApiVersion(event.target.value)}
                />
              </div>
            )}
            <ModelPicker
              token={token}
              provider={provider}
              baseUrl={baseUrl}
              apiVersion={apiVersion}
              apiKey={apiKey}
              apiKeyConfigured={config?.api_key_configured ?? false}
              model={model}
              onChange={setModel}
            />
            <div className="grid gap-1.5">
              <Label htmlFor="model-key">{t("settings.apiKey")}</Label>
              <Input
                id="model-key"
                type="password"
                autoComplete="new-password"
                value={apiKey}
                placeholder={keyPlaceholder}
                onChange={(event) => setApiKey(event.target.value)}
              />
              <span className="text-xs text-muted-foreground">
                {config?.api_key_source === "runtime"
                  ? t("settings.keySourceRuntime")
                  : config?.api_key_source === "environment"
                    ? t("settings.keySourceEnvironment")
                    : t("settings.keySourceNone")}
                {" · "}
                {t("settings.keyEncryptedHint")}
              </span>
              {config?.api_key_source === "runtime" && (
                <Label className="mt-1 gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={clearKey}
                    onChange={(event) => setClearKey(event.target.checked)}
                    className="size-4 accent-[var(--primary)]"
                  />
                  {t("settings.clearKey")}
                </Label>
              )}
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <div className="grid gap-1.5">
                <Label htmlFor="model-temperature">{t("settings.temperature")}</Label>
                <Input
                  id="model-temperature"
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  value={temperature}
                  onChange={(event) => setTemperature(Number(event.target.value))}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="model-timeout">{t("settings.timeout")}</Label>
                <Input
                  id="model-timeout"
                  type="number"
                  min={1}
                  max={300}
                  value={timeout}
                  onChange={(event) => setTimeout(Number(event.target.value))}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="model-retries">{t("settings.maxRetries")}</Label>
                <Input
                  id="model-retries"
                  type="number"
                  min={0}
                  max={10}
                  value={maxRetries}
                  onChange={(event) => setMaxRetries(Number(event.target.value))}
                />
              </div>
            </div>
            <Label className="gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={thinking}
                onChange={(event) => setThinking(event.target.checked)}
                className="size-4 accent-[var(--primary)]"
              />
              {t("settings.thinking")}
            </Label>
            <div className="flex justify-end gap-2">
              <Button variant="outline" disabled={busy === "model"} onClick={() => void resetModel()}>
                {t("settings.resetModel")}
              </Button>
              <Button disabled={busy === "model"} onClick={() => void saveModel()}>
                {t("settings.saveModel")}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-start justify-between gap-2">
            <div>
              <CardTitle>{t("settings.promptTitle")}</CardTitle>
              <CardDescription className="mt-1">{t("settings.promptHelp")}</CardDescription>
            </div>
            <Badge variant={promptSource === "saved_graph" ? "accent" : "secondary"}>
              {promptSource === "saved_graph"
                ? t("settings.promptSourceSaved")
                : t("settings.promptSourceDefault")}
            </Badge>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Textarea
              spellCheck={false}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              className="min-h-[280px] resize-y rounded-xl [field-sizing:fixed] leading-relaxed"
            />
            <div className="flex justify-end">
              <Button
                disabled={busy === "prompt" || !prompt.trim()}
                onClick={() => void savePrompt()}
              >
                {t("settings.savePrompt")}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
