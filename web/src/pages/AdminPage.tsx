import { useEffect, useRef, useState } from "react";
import { RefreshCw, Send } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  AdminSession,
  AdminSessionList,
  errorText,
  getJson,
  MessageList,
  MessageRecord,
  putJson,
  tokenFor,
} from "@/api";
import { useLanguage } from "@/i18n";
import { ChatSocket, ConnState } from "@/ws";

function toRecord(event: Record<string, unknown>): MessageRecord {
  return {
    id: String(event.id ?? ""),
    session_id: String(event.session_id ?? ""),
    sender_id: String(event.sender_id ?? ""),
    sender_type: String(event.sender_type ?? "agent"),
    content: String(event.content ?? ""),
    message_type: String(event.message_type ?? "text"),
    created_at: String(event.created_at ?? ""),
  };
}

const STATUS_VARIANT: Record<ConnState, "success" | "warning" | "destructive" | "secondary"> = {
  connecting: "warning",
  online: "success",
  reconnecting: "warning",
  offline: "destructive",
};

export default function AdminPage() {
  const { t, systemText, language } = useLanguage();
  const [sessions, setSessions] = useState<AdminSession[]>([]);
  const [selected, setSelected] = useState<AdminSession | null>(null);
  const [messages, setMessages] = useState<MessageRecord[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draft, setDraft] = useState("");
  const [connection, setConnection] = useState<ConnState>("offline");
  const tokenRef = useRef("");
  const socketRef = useRef<ChatSocket | null>(null);
  const selectedRef = useRef<AdminSession | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const languageRef = useRef(language);

  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  const closeSocket = () => {
    socketRef.current?.close();
    socketRef.current = null;
    setConnection("offline");
  };

  const appendMessage = (record: MessageRecord) => {
    if (!record.id) return;
    setMessages((previous) =>
      previous.some((message) => message.id === record.id)
        ? previous.map((message) => (message.id === record.id ? record : message))
        : [...previous, record],
    );
  };

  const loadSessions = async (token: string) => {
    const list = await getJson<AdminSessionList>("/admin/sessions?limit=50", token);
    setSessions(list.items);
  };

  useEffect(() => {
    void (async () => {
      try {
        tokenRef.current = await tokenFor("agent");
        await loadSessions(tokenRef.current);
      } catch (caught) {
        setError(errorText(caught));
      }
    })();
    return () => closeSocket();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const connect = (session: AdminSession) => {
    closeSocket();
    const socket = new ChatSocket({
      onState: setConnection,
      onEvent: (event) => {
        if (event.type === "message") {
          appendMessage(toRecord(event));
        } else if (event.type === "image") {
          appendMessage({
            id: String(event.id ?? event.image_id ?? ""),
            session_id: String(event.session_id ?? session.id),
            sender_id: String(event.sender_id ?? ""),
            sender_type: "user",
            content: "[image]",
            message_type: "image",
            created_at: String(event.created_at ?? ""),
          });
        } else if (event.type === "error") {
          setError(String(event.message ?? t("admin.error")));
        }
      },
    });
    socketRef.current = socket;
    socket.connect(tokenRef.current, session.id);
  };

  const open = async (session: AdminSession) => {
    setError("");
    setNotice("");
    setSelected(session);
    selectedRef.current = session;
    setMessages([]);
    try {
      const history = await getJson<MessageList>(
        `/admin/sessions/${session.id}/messages?limit=50`,
        tokenRef.current,
      );
      setMessages(history.items.slice().reverse());
      connect(session);
      if (window.innerWidth <= 900) {
        window.setTimeout(() => {
          document
            .querySelector("[data-conversation-panel]")
            ?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 80);
      }
    } catch (caught) {
      setError(errorText(caught));
    }
  };

  const takeover = async () => {
    if (!selected) return;
    setError("");
    setNotice("");
    try {
      const updated = await putJson<AdminSession>(
        `/admin/sessions/${selected.id}/takeover`,
        { enabled: !selected.human_takeover },
        tokenRef.current,
      );
      setSelected(updated);
      selectedRef.current = updated;
      setNotice(
        updated.human_takeover ? t("admin.noticeTakeoverOn") : t("admin.noticeTakeoverOff"),
      );
      await loadSessions(tokenRef.current);
    } catch (caught) {
      setError(errorText(caught));
    }
  };

  const send = () => {
    const text = draft.trim();
    const active = selectedRef.current;
    if (!active || !text) return;
    if (!active.human_takeover) {
      setError(t("admin.needTakeover"));
      return;
    }
    if (!socketRef.current) {
      setError(t("admin.socketNotReady"));
      return;
    }
    socketRef.current.sendMessage(text);
    setDraft("");
    setError("");
  };

  const close = async () => {
    if (!selected) return;
    setError("");
    try {
      const updated = await putJson<AdminSession>(
        `/admin/sessions/${selected.id}/status`,
        { status: "closed" },
        tokenRef.current,
      );
      setSelected(updated);
      selectedRef.current = updated;
      setNotice(t("admin.noticeClosed"));
      await loadSessions(tokenRef.current);
    } catch (caught) {
      setError(errorText(caught));
    }
  };

  const statusVariant = (status: string) =>
    status === "active" ? "success" : status === "archived" ? "warning" : "secondary";
  const composerEnabled = Boolean(selected?.human_takeover && selected?.status !== "closed");

  return (
    <div className="flex flex-col gap-3">
      <Card className="flex flex-row flex-wrap items-center justify-between gap-3 px-5 py-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t("admin.title")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t("admin.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          {selected && (
            <Badge variant={STATUS_VARIANT[connection]}>{t(`status.${connection}`)}</Badge>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              void loadSessions(tokenRef.current).catch((caught) => setError(errorText(caught)))
            }
          >
            <RefreshCw />
            {t("common.refresh")}
          </Button>
        </div>
      </Card>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {notice && (
        <div className="rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
          {notice}
        </div>
      )}

      <div className="grid items-start gap-3 lg:grid-cols-[1.05fr_1fr]">
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between gap-3 px-5 pt-5 pb-3">
            <h2 className="text-sm font-semibold">{t("admin.conversations")}</h2>
            <span className="text-xs text-muted-foreground">
              {t("admin.shown", { count: sessions.length })}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted-foreground uppercase">
                  <th className="px-5 py-2 font-medium">{t("admin.colCustomer")}</th>
                  <th className="px-2 py-2 font-medium">{t("admin.colStatus")}</th>
                  <th className="hidden px-2 py-2 font-medium sm:table-cell">
                    {t("admin.colAI")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {sessions.map((session) => (
                  <tr
                    key={session.id}
                    onClick={() => void open(session)}
                    className={
                      selected?.id === session.id
                        ? "cursor-pointer bg-primary/5"
                        : "cursor-pointer hover:bg-muted/60"
                    }
                  >
                    <td className="max-w-[220px] px-5 py-3">
                      <strong className="block truncate text-sm font-medium">
                        {session.user_email ?? session.user_id.slice(0, 8)}
                      </strong>
                      <span className="block truncate text-xs text-muted-foreground">
                        {session.title}
                      </span>
                    </td>
                    <td className="px-2 py-3">
                      <Badge variant={statusVariant(session.status)}>
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
        </Card>

        <Card data-conversation-panel className="flex flex-col gap-3 px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="min-w-0 truncate text-sm font-semibold">
              {selected
                ? t("admin.conversation", {
                    name: (selected.user_email ?? selected.id).slice(0, 22),
                  })
                : t("admin.pick")}
            </h2>
            {selected && (
              <div className="flex items-center gap-2">
                <Button
                  variant={selected.human_takeover ? "outline" : "default"}
                  size="sm"
                  onClick={() => void takeover()}
                >
                  {selected.human_takeover ? t("admin.release") : t("admin.takeOver")}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={selected.status === "closed"}
                  onClick={() => void close()}
                >
                  {t("common.close")}
                </Button>
              </div>
            )}
          </div>

          {!selected && (
            <p className="py-8 text-center text-sm text-muted-foreground">{t("admin.pickHint")}</p>
          )}

          {selected && (
            <>
              <div className="scrollbar-thin max-h-[46dvh] overflow-y-auto lg:max-h-[58vh]">
                {messages.length === 0 && (
                  <p className="py-6 text-sm text-muted-foreground">{t("admin.noMessages")}</p>
                )}
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className="grid grid-cols-[46px_1fr] gap-2 border-b border-border py-2 text-sm last:border-0 sm:grid-cols-[74px_1fr] sm:gap-3"
                  >
                    <span
                      className={
                        message.sender_type === "agent"
                          ? "text-[11px] tracking-wider text-primary uppercase"
                          : message.message_type === "system"
                            ? "text-[11px] tracking-wider text-warning uppercase"
                            : "text-[11px] tracking-wider text-muted-foreground uppercase"
                      }
                    >
                      {message.message_type === "system"
                        ? t("admin.system")
                        : message.sender_type === "user"
                          ? t("admin.user")
                          : t("admin.agent")}
                    </span>
                    <span className="leading-relaxed break-words whitespace-pre-wrap">
                      {message.message_type === "image"
                        ? `[${t("common.image")}]`
                        : message.message_type === "system"
                          ? systemText(message.content)
                          : message.content}
                    </span>
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>

              <div className="flex flex-col gap-2 border-t border-border pt-3 sm:flex-row sm:items-end">
                <Textarea
                  value={draft}
                  rows={2}
                  placeholder={
                    composerEnabled ? t("admin.placeholderEnabled") : t("admin.placeholderDisabled")
                  }
                  disabled={!composerEnabled}
                  className="min-h-12 resize-none rounded-xl"
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      send();
                    }
                  }}
                />
                <Button
                  className="shrink-0"
                  disabled={!composerEnabled}
                  onClick={send}
                  aria-label={t("admin.sendReply")}
                >
                  <Send />
                  <span className="hidden sm:inline">{t("admin.sendReply")}</span>
                </Button>
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
