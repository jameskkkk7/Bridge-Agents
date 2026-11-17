import { useEffect, useState } from "react";
import { deleteJson, errorText, getJson, putJson } from "../api";
import { useLanguage } from "../i18n";

interface ModelConfig {
  base_url: string;
  model: string;
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
  const [baseUrl, setBaseUrl] = useState("");
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
    setBaseUrl(value.base_url);
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

  const saveModel = async () => {
    onError("");
    setNotice("");
    setBusy("model");
    try {
      const updated = await putJson<ModelConfig>(
        "/admin/runtime-config/model-config",
        {
          base_url: baseUrl,
          model,
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
    <>
      {notice && <div className="banner success">{notice}</div>}
      <div className="settings-grid">
        <div className="card column">
          <div className="table-head">
            <h3>{t("settings.modelTitle")}</h3>
            {config && (
              <span className="pill ai">
                {config.source === "runtime" ? t("settings.sourceRuntime") : t("settings.sourceEnvironment")}
              </span>
            )}
          </div>
          <p className="muted small">{t("settings.modelHelp")}</p>

          <div className="field">
            <label htmlFor="model-base-url">{t("settings.baseUrl")}</label>
            <input
              id="model-base-url"
              value={baseUrl}
              placeholder="https://api.openai.com/v1"
              onChange={(event) => setBaseUrl(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="model-name">{t("settings.model")}</label>
            <input
              id="model-name"
              value={model}
              placeholder="gpt-4o-mini"
              onChange={(event) => setModel(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="model-key">{t("settings.apiKey")}</label>
            <input
              id="model-key"
              type="password"
              autoComplete="new-password"
              value={apiKey}
              placeholder={keyPlaceholder}
              onChange={(event) => setApiKey(event.target.value)}
            />
            <span className="muted small">
              {config?.api_key_source === "runtime"
                ? t("settings.keySourceRuntime")
                : config?.api_key_source === "environment"
                  ? t("settings.keySourceEnvironment")
                  : t("settings.keySourceNone")}
              {" · "}
              {t("settings.keyEncryptedHint")}
            </span>
            {config?.api_key_source === "runtime" && (
              <label className="toggle-row small">
                <input
                  type="checkbox"
                  checked={clearKey}
                  onChange={(event) => setClearKey(event.target.checked)}
                />
                {t("settings.clearKey")}
              </label>
            )}
          </div>

          <div className="settings-row">
            <div className="field">
              <label htmlFor="model-temperature">{t("settings.temperature")}</label>
              <input
                id="model-temperature"
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={temperature}
                onChange={(event) => setTemperature(Number(event.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="model-timeout">{t("settings.timeout")}</label>
              <input
                id="model-timeout"
                type="number"
                min={1}
                max={300}
                value={timeout}
                onChange={(event) => setTimeout(Number(event.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="model-retries">{t("settings.maxRetries")}</label>
              <input
                id="model-retries"
                type="number"
                min={0}
                max={10}
                value={maxRetries}
                onChange={(event) => setMaxRetries(Number(event.target.value))}
              />
            </div>
          </div>
          <label className="toggle-row small">
            <input
              type="checkbox"
              checked={thinking}
              onChange={(event) => setThinking(event.target.checked)}
            />
            {t("settings.thinking")}
          </label>

          <div className="row actions-end">
            <button className="ghost" disabled={busy === "model"} onClick={() => void resetModel()}>
              {t("settings.resetModel")}
            </button>
            <button className="primary" disabled={busy === "model"} onClick={() => void saveModel()}>
              {t("settings.saveModel")}
            </button>
          </div>
        </div>

        <div className="card column">
          <div className="table-head">
            <h3>{t("settings.promptTitle")}</h3>
            <span className="pill ai">
              {promptSource === "saved_graph"
                ? t("settings.promptSourceSaved")
                : t("settings.promptSourceDefault")}
            </span>
          </div>
          <p className="muted small">{t("settings.promptHelp")}</p>
          <textarea
            className="prompt-editor"
            spellCheck={false}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
          />
          <div className="row actions-end">
            <button
              className="primary"
              disabled={busy === "prompt" || !prompt.trim()}
              onClick={() => void savePrompt()}
            >
              {t("settings.savePrompt")}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
