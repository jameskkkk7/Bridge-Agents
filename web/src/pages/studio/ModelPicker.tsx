import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import SelectMenu from "@/components/ui/select-menu";
import { errorText, postJson } from "@/api";
import { useLanguage } from "@/i18n";

interface ModelCatalog {
  provider: string;
  base_url: string;
  models: string[];
  api_key_source: "request" | "runtime" | "environment" | "none";
}

export default function ModelPicker({
  token,
  provider,
  baseUrl,
  apiVersion,
  apiKey,
  apiKeyConfigured,
  model,
  onChange,
}: {
  token: string;
  provider: string;
  baseUrl: string;
  apiVersion: string;
  apiKey: string;
  apiKeyConfigured: boolean;
  model: string;
  onChange: (model: string) => void;
}) {
  const { t } = useLanguage();
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [source, setSource] = useState("");
  const requestId = useRef(0);
  const modelRef = useRef(model);
  const onChangeRef = useRef(onChange);
  modelRef.current = model;
  onChangeRef.current = onChange;

  const fetchModels = useCallback(async () => {
    if (!baseUrl.trim()) return;
    const currentRequest = ++requestId.current;
    setLoading(true);
    setError("");
    try {
      const catalog = await postJson<ModelCatalog>(
        "/admin/runtime-config/model-config/models",
        {
          provider,
          base_url: baseUrl,
          api_version: apiVersion,
          api_key: apiKey.trim() ? apiKey.trim() : null,
        },
        token,
      );
      if (currentRequest !== requestId.current) return;
      setModels(catalog.models);
      setSource(catalog.base_url);
      const current = modelRef.current;
      if (catalog.models.length > 0 && !catalog.models.includes(current)) {
        onChangeRef.current(catalog.models[0]);
      }
    } catch (caught) {
      if (currentRequest === requestId.current) setError(errorText(caught));
    } finally {
      if (currentRequest === requestId.current) setLoading(false);
    }
  }, [token, provider, baseUrl, apiVersion, apiKey]);

  useEffect(() => {
    if (!baseUrl.trim() || (!apiKeyConfigured && !apiKey.trim())) return;
    const timer = window.setTimeout(() => void fetchModels(), 500);
    return () => window.clearTimeout(timer);
  }, [fetchModels, apiKeyConfigured, apiKey]);

  const options = models.length > 0 ? [...models] : model ? [model] : [];
  if (model && !options.includes(model)) {
    options.unshift(model);
  }
  const modelOptions = options.map((value) => ({
    value,
    label:
      models.length > 0 && !models.includes(value)
        ? `${value} (${t("settings.modelCurrent")})`
        : value,
  }));

  return (
    <div className="grid gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor="model-name">{t("settings.model")}</Label>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={loading || !baseUrl.trim()}
          onClick={() => void fetchModels()}
        >
          <RefreshCw className={loading ? "animate-spin" : undefined} />
          {loading ? t("settings.fetchingModels") : t("settings.fetchModels")}
        </Button>
      </div>
      <SelectMenu
        id="model-name"
        value={model}
        options={modelOptions}
        onChange={onChange}
        disabled={loading || modelOptions.length === 0}
      />
      {error ? (
        <span className="text-xs text-destructive">{error}</span>
      ) : models.length > 0 ? (
        <span className="text-xs text-muted-foreground">
          {t("settings.modelSource", { url: source })}
        </span>
      ) : (
        <span className="text-xs text-muted-foreground">{t("settings.modelHint")}</span>
      )}
    </div>
  );
}
