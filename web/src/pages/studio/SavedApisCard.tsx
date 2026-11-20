import { CheckCircle2, Plus, RefreshCw, Trash2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useLanguage } from "@/i18n";

export interface SavedApiProfile {
  id: string;
  name: string;
  provider: string;
  base_url: string;
  model: string;
  api_version: string;
  temperature: number;
  timeout: number;
  max_retries: number;
  thinking_enabled: boolean;
  api_key_configured: boolean;
  valid: boolean;
  validation_message: string;
  validated_at: string | null;
  created_at: string;
  updated_at: string;
  active: boolean;
}

export interface SavedApiList {
  active_id: string | null;
  profiles: SavedApiProfile[];
}

export default function SavedApisCard({
  data,
  busy,
  onNew,
  onSelect,
  onActivate,
  onValidate,
  onDelete,
  onDeactivate,
}: {
  data: SavedApiList | null;
  busy: string;
  onNew: () => void;
  onSelect: (profile: SavedApiProfile) => void;
  onActivate: (id: string) => void;
  onValidate: (id: string) => void;
  onDelete: (id: string) => void;
  onDeactivate: () => void;
}) {
  const { t } = useLanguage();
  const disabled = Boolean(busy);

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>{t("settings.savedApisTitle")}</CardTitle>
          <CardDescription className="mt-1">{t("settings.savedApisHelp")}</CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={onNew} disabled={disabled}>
          <Plus />
          {t("settings.newApi")}
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border px-3 py-2.5">
          <input
            type="radio"
            name="active-api"
            className="mt-1 size-4 accent-[var(--primary)]"
            checked={data?.active_id == null}
            disabled={disabled}
            onChange={onDeactivate}
          />
          <span className="min-w-0">
            <span className="block text-sm font-medium">{t("settings.environmentDefault")}</span>
            <span className="block text-xs text-muted-foreground">
              {t("settings.environmentDefaultHelp")}
            </span>
          </span>
        </label>

        {data?.profiles.map((profile) => (
          <div
            key={profile.id}
            className={
              "rounded-xl border px-3 py-2.5 " +
              (profile.active ? "border-primary/50 bg-primary/5" : "border-border")
            }
          >
            <div className="flex items-start gap-3">
              <input
                type="radio"
                name="active-api"
                className="mt-1 size-4 accent-[var(--primary)]"
                checked={profile.active}
                disabled={disabled || !profile.valid}
                onChange={() => onActivate(profile.id)}
                aria-label={t("settings.activateApi")}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className="max-w-full truncate text-left text-sm font-medium hover:underline"
                    title={t("settings.editApi")}
                    onClick={() => onSelect(profile)}
                  >
                    {profile.name}
                  </button>
                  {profile.active && <Badge variant="accent">{t("settings.activeApi")}</Badge>}
                  <Badge variant={profile.valid ? "success" : "destructive"}>
                    {profile.valid ? (
                      <>
                        <CheckCircle2 /> {t("settings.apiValidated")}
                      </>
                    ) : (
                      <>
                        <XCircle /> {t("settings.apiInvalid")}
                      </>
                    )}
                  </Badge>
                </div>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  {profile.provider} · {profile.model || "—"} · {profile.base_url}
                </p>
                {!profile.valid && profile.validation_message && (
                  <p className="mt-1 text-xs text-destructive">{profile.validation_message}</p>
                )}
                <div className="mt-1.5 flex flex-wrap items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={disabled}
                    onClick={() => onValidate(profile.id)}
                  >
                    <RefreshCw className={busy === `profile:validate:${profile.id}` ? "animate-spin" : undefined} />
                    {t("settings.validateApi")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground hover:text-destructive"
                    disabled={disabled}
                    onClick={() => onDelete(profile.id)}
                  >
                    <Trash2 />
                    {t("common.delete")}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        ))}

        {data && data.profiles.length === 0 && (
          <p className="px-1 py-2 text-sm text-muted-foreground">{t("settings.savedApisEmpty")}</p>
        )}
      </CardContent>
    </Card>
  );
}
