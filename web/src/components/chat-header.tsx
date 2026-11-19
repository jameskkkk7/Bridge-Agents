import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useLanguage } from "@/i18n";
import type { ConnState } from "@/ws";

const STATUS_VARIANT: Record<ConnState, "success" | "warning" | "destructive" | "secondary"> = {
  connecting: "warning",
  online: "success",
  reconnecting: "warning",
  offline: "destructive",
};

export default function ChatHeader({
  title,
  customerName,
  toolNote,
  connection,
}: {
  title: string;
  customerName?: string;
  toolNote: string;
  connection: ConnState;
}) {
  const { t } = useLanguage();

  return (
    <Card className="flex flex-row items-center justify-between gap-4 px-5 py-4">
      <div className="min-w-0">
        <h1 className="truncate text-lg font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {customerName ? `${t("chat.hello", { name: customerName })} · ` : ""}
          {t("chat.demoMode")}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {toolNote && (
          <Badge variant="accent" className="animate-pulse">
            {t("chat.toolPrefix")} {toolNote}
          </Badge>
        )}
        <Badge variant={STATUS_VARIANT[connection]}>{t(`status.${connection}`)}</Badge>
      </div>
    </Card>
  );
}
