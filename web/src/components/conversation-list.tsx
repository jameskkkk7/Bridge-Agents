import { MessageSquarePlus, MessagesSquare } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SessionRecord } from "@/api";
import { useLanguage } from "@/i18n";
import { cn } from "@/lib/utils";

function formatTime(value: string, locale: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString(locale, { month: "2-digit", day: "2-digit" });
}

export default function ConversationList({
  sessions,
  activeId,
  onSelect,
  onNew,
  variant = "sidebar",
}: {
  sessions: SessionRecord[];
  activeId?: string;
  onSelect: (session: SessionRecord) => void;
  onNew: () => void;
  variant?: "sidebar" | "strip";
}) {
  const { t, language } = useLanguage();
  const locale = language === "zh" ? "zh-CN" : "en-US";
  const sidebar = variant === "sidebar";

  return (
    <div className={cn("flex gap-2", sidebar ? "h-full min-h-0 flex-col" : "items-center")}>
      <Button
        variant="default"
        size="sm"
        className={cn("shrink-0 rounded-full", sidebar ? "w-full justify-start" : "text-xs")}
        onClick={onNew}
      >
        <MessageSquarePlus />
        {t("chat.newConversation")}
      </Button>
      {sidebar && <div className="my-0.5 border-t border-border" aria-hidden />}
      <div
        className={cn(
          sidebar
            ? "scrollbar-thin flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto pt-1"
            : "flex gap-2 overflow-x-auto pb-1",
        )}
      >
        {sidebar && sessions.length === 0 && (
          <p className="px-2 py-4 text-xs text-muted-foreground">{t("chat.noConversations")}</p>
        )}
        {sessions.map((session) => {
          const selected = session.id === activeId;
          return (
            <button
              key={session.id}
              type="button"
              title={session.title}
              onClick={() => onSelect(session)}
              className={cn(
                "flex items-center gap-2 rounded-xl text-left transition-colors",
                sidebar
                  ? "w-full px-2.5 py-2 hover:bg-muted/70"
                  : "shrink-0 border border-border px-3 py-1.5 hover:bg-muted/70",
                selected && (sidebar ? "bg-muted" : "border-primary/40 bg-primary/5"),
              )}
            >
              {sidebar && <MessagesSquare className="size-3.5 shrink-0 opacity-60" />}
              <span
                className={cn(
                  "truncate text-sm",
                  sidebar ? "min-w-0 flex-1" : "max-w-[42vw] text-xs",
                  selected && "font-medium",
                )}
              >
                {session.title}
              </span>
              <span className="ml-auto flex shrink-0 items-center gap-1 text-[10px] text-muted-foreground">
                {session.unread_count > 0 && (
                  <span className="size-1.5 rounded-full bg-primary" aria-hidden />
                )}
                {formatTime(session.updated_at || session.created_at, locale)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
