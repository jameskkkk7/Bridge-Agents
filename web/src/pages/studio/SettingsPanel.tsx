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
import { deleteJson, errorText, getJson, postJson, putJson } from "@/api";
import { useLanguage } from "@/i18n";
import ModelPicker from "./ModelPicker";
import SavedApisCard, { type SavedApiList, type SavedApiProfile } from "./SavedApisCard";
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
  const [profiles, setProfiles] = useState<SavedApiList | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [profileName, setProfileName] = useState("");
  const [editingKeyConfigured, setEditingKeyConfigured] = useState(false);

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
    const [modelConfig, promptView, profileList] = await Promise.all([
      getJson<ModelConfig>("/admin/runtime-config/model-config", token),
      getJson<PromptView>("/admin/runtime-config/agent-prompt", token),
      getJson<SavedApiList>("/admin/runtime-config/model-config/profiles", token),
    ]);
    applyConfig(modelConfig);
    setPrompt(promptView.system_prompt);
    setPromptSource(promptView.source);
    setProfiles(profileList);
    const active = profileList.profiles.find((item) => item.id === profileList.active_id);
    setProfileId(active?.id ?? null);
    setProfileName(active?.name ?? "");
    setEditingKeyConfigured(active?.api_key_configured ?? false);
  };

  const refreshProfiles = async () => {
    setProfiles(
      await getJson<SavedApiList>("/admin/runtime-config/model-config/profiles", token),
    );
  };

  useEffect(() => {
    void load().catch((caught) => onError(errorText(caught)));
  }, [token]);

  const applyProfile = (profile: SavedApiProfile) => {
    setProfileId(profile.id);
    setProfileName(profile.name);
    setProvider(profile.provider);
    setBaseUrl(profile.base_url);
    setApiVersion(profile.api_version || "2024-10-21");
    setModel(profile.model);
    setTemperature(profile.temperature);
    setTimeout(profile.timeout);
    setMaxRetries(profile.max_retries);
    setThinking(profile.thinking_enabled);
    setEditingKeyConfigured(profile.api_key_configured);
    setApiKey("");
    setClearKey(false);
  };

  const resetProfileForm = () => {
    setProfileId(null);
    setProfileName("");
    setProvider("openai");
    setBaseUrl(providerPreset("openai")?.baseUrl ?? "");
    setApiVersion("2024-10-21");
    setModel("");
    setTemperature(1);
    setTimeout(60);
    setMaxRetries(3);
    setThinking(false);
    setEditingKeyConfigured(false);
    setApiKey("");
    setClearKey(false);
  };

  const chooseProvider = (id: string) => {
    setProvider(id);
    const preset = providerPreset(id);
    if (!preset || id === "custom") return;
    setBaseUrl(preset.baseUrl);
    setModel("");
    if (preset.apiVersion) setApiVersion(preset.apiVersion);
  };

  const saveModel = async () => {
    if (!profileName.trim()) {
      onError(t("settings.profileNameRequired"));
      return;
    }
    if (!model.trim()) {
      onError(t("settings.modelRequired"));
      return;
    }
    if (!profileId && !apiKey.trim()) {
      onError(t("settings.profileKeyRequired"));
      return;
    }
    onError("");
    setNotice("");
    setBusy("model");
    try {
      const body = {
        name: profileName.trim(),
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
      };
      const saved = profileId
        ? await putJson<SavedApiProfile>(
            `/admin/runtime-config/model-config/profiles/${profileId}`,
            body,
            token,
          )
        : await postJson<SavedApiProfile>(
            "/admin/runtime-config/model-config/profiles",
            body,
            token,
          );
      setProfileId(saved.id);
      setProfileName(saved.name);
      setEditingKeyConfigured(saved.api_key_configured);
      setApiKey("");
      setClearKey(false);
      await refreshProfiles();
      setNotice(
        saved.valid
          ? t("settings.profileSaved")
          : t("settings.profileSavedInvalid", { message: saved.validation_message }),
      );
    } catch (caught) {
      onError(errorText(caught));
    } finally {
      setBusy("");
    }
  };

  const useEnvironmentDefaults = async () => {
    onError("");
    setNotice("");
    setBusy("profile:deactivate");
    try {
      await postJson<SavedApiList>(
        "/admin/runtime-config/model-config/profiles/deactivate",
        {},
        token,
      );
      await load();
      setNotice(t("settings.environmentActivated"));
    } catch (caught) {
      onError(errorText(caught));
    } finally {
      setBusy("");
    }
  };

  const activateProfile = async (id: string) => {
    onError("");
    setNotice("");
    setBusy(`profile:${id}`);
    try {
      await postJson<SavedApiProfile>(
        `/admin/runtime-config/model-config/profiles/${id}/activate`,
        {},
        token,
      );
      await load();
      setNotice(t("settings.profileActivated"));
    } catch (caught) {
      onError(errorText(caught));
    } finally {
      setBusy("");
    }
  };

  const validateProfile = async (id: string) => {
    onError("");
    setNotice("");
    setBusy(`profile:validate:${id}`);
    try {
      const result = await postJson<SavedApiProfile>(
        `/admin/runtime-config/model-config/profiles/${id}/validate`,
        {},
        token,
      );
      await refreshProfiles();
      setNotice(
        result.valid
          ? t("settings.profileValidated")
          : t("settings.profileInvalidAfterCheck", { message: result.validation_message }),
      );
    } catch (caught) {
      onError(errorText(caught));
    } finally {
      setBusy("");
    }
  };

  const deleteProfile = async (id: string) => {
    if (!window.confirm(t("settings.deleteApiConfirm"))) return;
    onError("");
    setNotice("");
    setBusy(`profile:delete:${id}`);
    try {
      const wasActive = profiles?.active_id === id;
      await deleteJson<SavedApiList>(
        `/admin/runtime-config/model-config/profiles/${id}`,
        token,
      );
      if (wasActive) {
        await load();
      } else {
        await refreshProfiles();
      }
      if (profileId === id) resetProfileForm();
      setNotice(t("settings.profileDeleted"));
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

  const keyPlaceholder = editingKeyConfigured
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
              <Label htmlFor="profile-name">{t("settings.profileName")}</Label>
              <Input
                id="profile-name"
                value={profileName}
                placeholder={t("settings.profileNamePlaceholder")}
                onChange={(event) => setProfileName(event.target.value)}
              />
            </div>
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
                {editingKeyConfigured
                  ? t("settings.keySourceRuntime")
                  : config?.api_key_source === "environment"
                    ? t("settings.keySourceEnvironment")
                    : t("settings.keySourceNone")}
                {" · "}
                {t("settings.keyEncryptedHint")}
              </span>
              {editingKeyConfigured && (
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
              <Button
                variant="outline"
                disabled={busy !== ""}
                onClick={() => void useEnvironmentDefaults()}
              >
                {t("settings.useEnvironment")}
              </Button>
              <Button disabled={busy !== ""} onClick={() => void saveModel()}>
                {t("settings.saveAndValidate")}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-3">
          <SavedApisCard
            data={profiles}
            busy={busy}
            onNew={resetProfileForm}
            onSelect={applyProfile}
            onActivate={(id) => void activateProfile(id)}
            onValidate={(id) => void validateProfile(id)}
            onDelete={(id) => void deleteProfile(id)}
            onDeactivate={() => void useEnvironmentDefaults()}
          />
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
    </div>
  );
}
