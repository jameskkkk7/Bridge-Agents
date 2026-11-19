import { useState } from "react";

import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useLanguage } from "@/i18n";

const MAX_NICKNAME_LENGTH = 20;

export default function NicknameGate({ onStart }: { onStart: (name: string) => void }) {
  const { t } = useLanguage();
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const submit = () => {
    const cleaned = name.replace(/\s+/g, " ").trim();
    if (!cleaned || cleaned.length > MAX_NICKNAME_LENGTH) {
      setError(t("chat.nicknameError"));
      return;
    }
    setError("");
    onStart(cleaned);
  };

  return (
    <div className="mx-auto flex min-h-[70dvh] w-full max-w-md items-center">
      <Card className="w-full px-6 py-8 sm:px-8">
        <div className="flex items-center gap-3">
          <BrandMark />
          <div>
            <p className="text-sm font-semibold tracking-tight">Bridge-Agents</p>
            <p className="text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
              {t("chat.demoMode")}
            </p>
          </div>
        </div>
        <h1 className="mt-6 text-xl font-semibold tracking-tight">{t("chat.nicknameTitle")}</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {t("chat.nicknameHelp")}
        </p>
        <div className="mt-5 grid gap-2">
          <label htmlFor="chat-nickname" className="text-sm font-medium">
            {t("chat.nicknameLabel")}
          </label>
          <Input
            id="chat-nickname"
            value={name}
            maxLength={MAX_NICKNAME_LENGTH}
            autoFocus
            autoComplete="nickname"
            placeholder={t("chat.nicknamePlaceholder")}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                submit();
              }
            }}
          />
          {error && <span className="text-xs text-destructive">{error}</span>}
          <Button className="mt-2 w-full" onClick={submit} disabled={!name.trim()}>
            {t("chat.nicknameStart")}
          </Button>
        </div>
      </Card>
    </div>
  );
}
