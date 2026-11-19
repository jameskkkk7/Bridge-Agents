import { useEffect, useState } from "react";

import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { errorText, tokenFor } from "@/api";
import { useLanguage } from "@/i18n";
import FlowPanel from "@/pages/studio/FlowPanel";
import KnowledgePanel from "@/pages/studio/KnowledgePanel";
import SettingsPanel from "@/pages/studio/SettingsPanel";

type Panel = "flow" | "knowledge" | "settings";

export default function GraphPage() {
  const { t } = useLanguage();
  const [panel, setPanel] = useState<Panel>("flow");
  const [error, setError] = useState("");
  const [token, setToken] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        setToken(await tokenFor("agent"));
      } catch (caught) {
        setError(errorText(caught));
      }
    })();
  }, []);

  return (
    <div className="flex flex-col gap-3">
      <Card className="flex flex-col gap-4 px-5 py-4">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{t("studio.title")}</h1>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t("studio.subtitle")}</p>
          </div>
          <Tabs value={panel} onValueChange={(value) => setPanel(value as Panel)}>
            <TabsList className="w-full sm:w-fit">
              <TabsTrigger value="flow">{t("studio.flow")}</TabsTrigger>
              <TabsTrigger value="knowledge">{t("studio.knowledge")}</TabsTrigger>
              <TabsTrigger value="settings">{t("studio.settings")}</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </Card>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {token && panel === "flow" && <FlowPanel token={token} onError={setError} />}
      {token && panel === "knowledge" && <KnowledgePanel token={token} onError={setError} />}
      {token && panel === "settings" && <SettingsPanel token={token} onError={setError} />}
    </div>
  );
}
