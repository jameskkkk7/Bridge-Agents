import { Badge } from "@/components/ui/badge";
import type { AdminSession } from "@/api";
import { useLanguage } from "@/i18n";

const STATUS_VARIANT: Record<string, "success" | "warning" | "secondary"> = {
  active: "success",
  archived: "warning",
  closed: "secondary",
};

export default function AdminSessionTable({
  sessions,
  selectedId,
  onOpen,
}: {
  sessions: AdminSession[];
  selectedId?: string;
  onOpen: (session: AdminSession) => void;
}) {
  const { t } = useLanguage();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted-foreground uppercase">
            <th className="px-5 py-2 font-medium">{t("admin.colCustomer")}</th>
            <th className="px-2 py-2 font-medium">{t("admin.colStatus")}</th>
            <th className="hidden px-2 py-2 font-medium sm:table-cell">{t("admin.colAI")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {sessions.map((session) => (
            <tr
              key={session.id}
              onClick={() => onOpen(session)}
              className={
                selectedId === session.id
                  ? "cursor-pointer bg-primary/5"
                  : "cursor-pointer hover:bg-muted/60"
              }
            >
              <td className="max-w-[220px] px-5 py-3">
                <strong className="block truncate text-sm font-medium">
                  {session.customer_name ?? session.user_email ?? session.user_id.slice(0, 8)}
                </strong>
                <span className="block truncate text-xs text-muted-foreground">
                  {session.title}
                </span>
              </td>
              <td className="px-2 py-3">
                <Badge variant={STATUS_VARIANT[session.status] ?? "secondary"}>
                  {t(`admin.status.${session.status}`)}
                </Badge>
              </td>
              <td className="hidden px-2 py-3 sm:table-cell">
                {session.human_takeover ? (
                  <Badge variant="warning">{t("admin.badgeHuman")}</Badge>
                ) : (
                  <Badge variant="accent">{t("admin.badgeAssistant")}</Badge>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
