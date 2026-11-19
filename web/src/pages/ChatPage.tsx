import { useEffect, useRef, useState } from "react";
import { Plus, Send } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  errorText,
  getJson,
  imageBlobUrl,
  imageIdFromContent,
  MessageList,
  MessageRecord,
  postJson,
  SessionList,
  SessionRecord,
  tokenFor,
} from "@/api";
import { translate, useLanguage } from "@/i18n";
import { ChatSocket, ConnState, ServerEvent } from "@/ws";

interface ViewMessage {
  id: string;
  kind: "user" | "agent" | "system" | "image";
  content: string;
  imageId?: string;
  imageUrl?: string;
}

const QUICK_PROMPTS: [string, string][] = [
  ["chat.quickRefund", "Can you guarantee a refund?"],
  ["chat.quickTool", "[[tool]] what time is it?"],
];

const STATUS_VARIANT: Record<ConnState, "success" | "warning" | "destructive" | "secondary"> = {
  connecting: "warning",
  online: "success",
  reconnecting: "warning",
  offline: "destructive",
};

export default function ChatPage() {
  const { language, t, systemText } = useLanguage();
  const [connection, setConnection] = useState<ConnState>("connecting");
  const [session, setSession] = useState<SessionRecord | null>(null);
  const [messages, setMessages] = useState<ViewMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [stream, setStream] = useState("");
  const [typing, setTyping] = useState(false);
  const [toolNote, setToolNote] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const socketRef = useRef<ChatSocket | null>(null);
  const tokenRef = useRef("");
  const sessionRef = useRef<SessionRecord | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const languageRef = useRef(language);

  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  useEffect(() => {
    let cancelled = false;
    const hydrate = async (sessionId: string, imageId: string) => {
      try {
        const url = await imageBlobUrl(sessionId, imageId, tokenRef.current);
        setMessages((all) =>
          all.map((m) => (m.imageId === imageId ? { ...m, imageUrl: url } : m)),
        );
      } catch {
        setError(translate(languageRef.current, "chat.imageLoadFailed"));
      }
    };
    const view = (record: MessageRecord): ViewMessage =>
      record.message_type === "image"
        ? {
            id: record.id,
            kind: "image",
            content: "image",
            imageId: imageIdFromContent(record.content) ?? undefined,
          }
        : {
            id: record.id,
            kind:
              record.message_type === "system"
                ? "system"
                : record.sender_type === "user"
                  ? "user"
                  : "agent",
            content: record.content,
          };
    const onEvent = (event: ServerEvent) => {
      const active = sessionRef.current;
      if (!active) return;
      if (event.type === "message") {
        const record = event as unknown as MessageRecord;
        const next = view(record);
        setMessages((all) =>
          all.some((m) => m.id === next.id)
            ? all.map((m) => (m.id === next.id ? next : m))
            : [...all, next],
        );
        if (next.imageId) void hydrate(active.id, next.imageId);
        if (record.sender_type === "agent") {
          setTyping(false);
          setStream("");
        }
      } else if (event.type === "message_chunk") {
        setStream(String(event.content ?? ""));
        setTyping(true);
      } else if (event.type === "stream_end") {
        setTyping(false);
        setStream("");
      } else if (event.type === "tool_call") {
        setToolNote(String(event.tool_name ?? "tool"));
        window.setTimeout(() => setToolNote(""), 2500);
      } else if (event.type === "image") {
        const imageId = String(event.image_id ?? "");
        setMessages((all) => [
          ...all,
          {
            id: String(event.id ?? imageId),
            kind: "image",
            content: String(event.filename ?? "image"),
            imageId,
          },
        ]);
        void hydrate(active.id, imageId);
      } else if (event.type === "error") {
        setError(String(event.message ?? translate(languageRef.current, "chat.error")));
      }
    };
    const boot = async () => {
      try {
        const token = await tokenFor("user");
        tokenRef.current = token;
        const list = await getJson<SessionList>("/sessions?limit=20", token);
        const active =
          list.items.find((item) => item.status === "active") ??
          (await postJson<SessionRecord>(
            "/sessions",
            { title: translate(languageRef.current, "chat.demoTitle") },
            token,
          ));
        if (cancelled) return;
        setSession(active);
        sessionRef.current = active;
        const history = await getJson<MessageList>(
          `/sessions/${active.id}/messages?limit=50`,
          token,
        );
        if (cancelled) return;
        setMessages(history.items.slice().reverse().map(view));
        history.items.forEach((record) => {
          const imageId = imageIdFromContent(record.content);
          if (record.message_type === "image" && imageId) void hydrate(active.id, imageId);
        });
        const socket = new ChatSocket({ onState: setConnection, onEvent });
        socketRef.current = socket;
        socket.connect(token, active.id);
      } catch (caught) {
        if (!cancelled) {
          setError(errorText(caught));
          setConnection("offline");
        }
      }
    };
    void boot();
    return () => {
      cancelled = true;
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, stream, typing]);

  const send = (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || !socketRef.current) return;
    socketRef.current.sendMessage(trimmed);
    setDraft("");
    setError("");
    setTyping(true);
    setStream("");
  };

  const upload = async (file: File) => {
    if (!sessionRef.current) return;
    setUploading(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`/api/v1/sessions/${sessionRef.current.id}/images`, {
        method: "POST",
        headers: { Authorization: `Bearer ${tokenRef.current}` },
        body,
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { message?: string };
        throw new Error(payload.message ?? translate(languageRef.current, "chat.imageUploadFailed"));
      }
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <Card className="flex flex-row items-center justify-between gap-4 px-5 py-4">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-semibold tracking-tight">
            {session ? session.title : t("chat.connecting")}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("chat.customerView")} ·{" "}
            {session ? t("chat.session", { id: session.id.slice(0, 8) }) : t("chat.preparing")}
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

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <Card className="scrollbar-thin flex min-h-[44dvh] max-h-[56dvh] flex-col gap-3 overflow-y-auto px-4 py-4 sm:px-5 sm:py-5 md:min-h-[46vh] md:max-h-[58vh]">
        {messages.length === 0 && !typing && (
          <p className="m-auto max-w-sm text-center text-sm text-muted-foreground">
            {t("chat.empty")}
          </p>
        )}
        {messages.map((message) =>
          message.kind === "system" ? (
            <div
              key={message.id}
              className="mx-auto rounded-full border border-dashed border-border bg-muted px-3 py-1 text-xs text-muted-foreground"
            >
              {systemText(message.content)}
            </div>
          ) : (
            <div
              key={message.id}
              className={
                message.kind === "user"
                  ? "ml-auto max-w-[88%] animate-fade-in rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words text-primary-foreground sm:max-w-[78%]"
                  : "mr-auto max-w-[88%] animate-fade-in rounded-2xl rounded-bl-md border border-border bg-muted px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words sm:max-w-[78%]"
              }
            >
              {message.kind === "image" ? (
                message.imageUrl ? (
                  <img
                    src={message.imageUrl}
                    alt={t("chat.imageAlt")}
                    className="max-w-full rounded-lg"
                  />
                ) : (
                  <span className="text-muted-foreground">{t("chat.imageLoading")}</span>
                )
              ) : (
                message.content
              )}
            </div>
          ),
        )}
        {stream && (
          <div className="mr-auto max-w-[88%] rounded-2xl rounded-bl-md border border-border bg-muted px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words sm:max-w-[78%]">
            {stream}
            <span className="ml-0.5 inline-block h-4 w-1.5 animate-caret bg-primary align-[-2px]" />
          </div>
        )}
        {typing && !stream && (
          <div className="flex items-center gap-1.5 px-1 py-1.5" aria-label="assistant is typing">
            {[0, 150, 300].map((delay) => (
              <span
                key={delay}
                className="size-1.5 animate-typing rounded-full bg-muted-foreground"
                style={{ animationDelay: `${delay}ms` }}
              />
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </Card>

      <Card className="flex flex-col gap-3 px-4 py-4 sm:px-5">
        <div className="flex flex-wrap items-center gap-2">
          {QUICK_PROMPTS.map(([labelKey, prompt]) => (
            <Button
              key={labelKey}
              variant="secondary"
              size="sm"
              className="rounded-full text-xs"
              onClick={() => send(prompt)}
            >
              {t(labelKey)}
            </Button>
          ))}
          <span className="ml-auto hidden text-xs text-muted-foreground sm:inline">
            {t("chat.hint")}
          </span>
        </div>
        <div className="flex items-end gap-2">
          <Button
            variant="outline"
            size="icon"
            className="shrink-0 rounded-full"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            aria-label={t("chat.imageAlt")}
          >
            <Plus />
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/gif,image/webp,image/bmp"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
            }}
          />
          <Textarea
            value={draft}
            placeholder={t("chat.placeholder")}
            rows={1}
            className="max-h-32 min-h-11 rounded-xl"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send(draft);
              }
            }}
          />
          <Button className="shrink-0" onClick={() => send(draft)} aria-label={t("common.send")}>
            <Send />
            <span className="hidden sm:inline">{t("common.send")}</span>
          </Button>
        </div>
      </Card>
    </div>
  );
}
