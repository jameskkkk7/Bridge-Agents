import { useEffect, useRef, useState } from "react";

import ChatComposer from "@/components/chat-composer";
import NicknameGate from "@/components/nickname-gate";
import ChatHeader from "@/components/chat-header";
import ChatTranscript from "@/components/chat-transcript";
import type { ViewMessage } from "@/components/chat-transcript";
import ConversationList from "@/components/conversation-list";
import { Card } from "@/components/ui/card";
import {
  errorText,
  getJson,
  imageBlobUrl,
  imageIdFromContent,
  MessageList,
  MessageRecord,
  postJson,
  putJson,
  SessionList,
  SessionRecord,
  tokenFor,
} from "@/api";
import { translate, useLanguage } from "@/i18n";
import { ChatSocket, ConnState, ServerEvent } from "@/ws";

const ACTIVE_SESSION_KEY = "bridge-agents.active-session";
const CLIENT_ID_KEY = "bridge-agents.client-id";
const CUSTOMER_NAME_KEY = "bridge-agents.customer-name";
const MAX_TITLE_CHARS = 40;
const DEFAULT_TITLES = new Set([
  "新对话",
  "New chat",
  "演示会话",
  "Demo conversation",
  "New conversation",
]);

function newClientId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // crypto.randomUUID is only available in secure contexts; LAN demos run on
  // plain http, so fall back to a random demo id.
  return `demo-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function viewMessage(record: MessageRecord): ViewMessage {
  return record.message_type === "image"
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
}

export default function ChatPage() {
  const { language, t } = useLanguage();
  const [profile, setProfile] = useState<{ clientId: string; name: string } | null>(() => {
    const clientId = localStorage.getItem(CLIENT_ID_KEY);
    const name = localStorage.getItem(CUSTOMER_NAME_KEY);
    return clientId && name ? { clientId, name } : null;
  });
  const [connection, setConnection] = useState<ConnState>("connecting");
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [active, setActive] = useState<SessionRecord | null>(null);
  const [messages, setMessages] = useState<ViewMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [stream, setStream] = useState("");
  const [typing, setTyping] = useState(false);
  const [toolNote, setToolNote] = useState("");
  const [uploading, setUploading] = useState(false);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");
  const socketRef = useRef<ChatSocket | null>(null);
  const tokenRef = useRef("");
  const activeRef = useRef<SessionRecord | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const languageRef = useRef(language);
  const switchSeq = useRef(0);

  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, stream, typing]);

  useEffect(
    () => () => {
      socketRef.current?.close();
      socketRef.current = null;
    },
    [],
  );

  const hydrateImage = async (sessionId: string, imageId: string) => {
    try {
      const url = await imageBlobUrl(sessionId, imageId, tokenRef.current);
      if (activeRef.current?.id !== sessionId) return;
      setMessages((all) =>
        all.map((message) => (message.imageId === imageId ? { ...message, imageUrl: url } : message)),
      );
    } catch {
      setError(translate(languageRef.current, "chat.imageLoadFailed"));
    }
  };

  const refreshSessions = async () => {
    try {
      const list = await getJson<SessionList>("/sessions?limit=50", tokenRef.current);
      setSessions(list.items);
      const current = activeRef.current;
      const fresh = current ? list.items.find((item) => item.id === current.id) : undefined;
      if (fresh) {
        activeRef.current = fresh;
        setActive(fresh);
      }
    } catch {
      /* keep the last known list on transient failures */
    }
  };

  const markRead = async (sessionId: string) => {
    try {
      await postJson(`/sessions/${sessionId}/read`, {}, tokenRef.current);
    } catch {
      /* reading receipts are best-effort */
    }
    void refreshSessions();
  };

  const handleEvent = (event: ServerEvent) => {
    const current = activeRef.current;
    if (!current) return;
    if (typeof event.session_id === "string" && event.session_id !== current.id) return;
    if (event.type === "message") {
      const next = viewMessage(event as unknown as MessageRecord);
      setMessages((all) =>
        all.some((message) => message.id === next.id)
          ? all.map((message) => (message.id === next.id ? next : message))
          : [...all, next],
      );
      if (next.imageId) void hydrateImage(current.id, next.imageId);
      if ((event as unknown as MessageRecord).sender_type === "agent") {
        setTyping(false);
        setStream("");
      }
    } else if (event.type === "message_chunk") {
      setStream(String(event.content ?? ""));
      setTyping(true);
    } else if (event.type === "stream_end") {
      setTyping(false);
      setStream("");
      void refreshSessions();
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
      void hydrateImage(current.id, imageId);
    } else if (event.type === "error") {
      setError(String(event.message ?? translate(languageRef.current, "chat.error")));
    }
  };

  const connect = (session: SessionRecord) => {
    socketRef.current?.close();
    let socket: ChatSocket;
    socket = new ChatSocket({
      onState: (state) => {
        if (socketRef.current === socket) setConnection(state);
      },
      onEvent: handleEvent,
    });
    socketRef.current = socket;
    socket.connect(tokenRef.current, session.id);
  };

  const openSession = async (session: SessionRecord) => {
    const seq = ++switchSeq.current;
    activeRef.current = session;
    setActive(session);
    setMessages([]);
    setStream("");
    setTyping(false);
    setDraft("");
    setToolNote("");
    setError("");
    localStorage.setItem(ACTIVE_SESSION_KEY, session.id);
    try {
      const history = await getJson<MessageList>(
        `/sessions/${session.id}/messages?limit=50`,
        tokenRef.current,
      );
      if (seq !== switchSeq.current) return;
      setMessages(history.items.slice().reverse().map(viewMessage));
      history.items.forEach((record) => {
        const imageId = imageIdFromContent(record.content);
        if (record.message_type === "image" && imageId) {
          void hydrateImage(session.id, imageId);
        }
      });
      void markRead(session.id);
      connect(session);
    } catch (caught) {
      if (seq === switchSeq.current) setError(errorText(caught));
    }
  };

  const renameFromMessage = async (session: SessionRecord, text: string) => {
    const title = text.replace(/\s+/g, " ").trim().slice(0, MAX_TITLE_CHARS);
    if (!title) return;
    try {
      const updated = await putJson<SessionRecord>(
        `/sessions/${session.id}`,
        { title },
        tokenRef.current,
      );
      setSessions((all) => all.map((item) => (item.id === updated.id ? updated : item)));
      if (activeRef.current?.id === updated.id) {
        activeRef.current = updated;
        setActive(updated);
      }
    } catch {
      /* the title is cosmetic; keep the default on failure */
    }
  };

  const send = (content: string) => {
    const trimmed = content.trim();
    const current = activeRef.current;
    if (!trimmed || !current || !socketRef.current) return;
    socketRef.current.sendMessage(trimmed);
    setDraft("");
    setError("");
    setTyping(true);
    setStream("");
    if (DEFAULT_TITLES.has(current.title)) void renameFromMessage(current, trimmed);
  };

  const upload = async (file: File) => {
    const current = activeRef.current;
    if (!current) return;
    setUploading(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`/api/v1/sessions/${current.id}/images`, {
        method: "POST",
        headers: { Authorization: `Bearer ${tokenRef.current}` },
        body,
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { message?: string };
        throw new Error(
          payload.message ?? translate(languageRef.current, "chat.imageUploadFailed"),
        );
      }
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setUploading(false);
    }
  };

  const startChat = (name: string) => {
    let clientId = localStorage.getItem(CLIENT_ID_KEY);
    if (!clientId) {
      clientId = newClientId();
      localStorage.setItem(CLIENT_ID_KEY, clientId);
    }
    localStorage.setItem(CUSTOMER_NAME_KEY, name);
    setProfile({ clientId, name });
  };

  const newConversation = async () => {
    try {
      const created = await postJson<SessionRecord>(
        "/sessions",
        { title: translate(languageRef.current, "chat.newConversation") },
        tokenRef.current,
      );
      setSessions((all) => [created, ...all.filter((item) => item.id !== created.id)]);
      await openSession(created);
    } catch (caught) {
      setError(errorText(caught));
    }
  };

  useEffect(() => {
    if (!profile) return;
    let cancelled = false;
    setBooting(true);
    void (async () => {
      try {
        const token = await tokenFor("user", profile);
        tokenRef.current = token;
        const list = await getJson<SessionList>("/sessions?limit=50", token);
        if (cancelled) return;
        setSessions(list.items);
        const savedId = localStorage.getItem(ACTIVE_SESSION_KEY);
        const preferred =
          list.items.find((item) => item.id === savedId) ??
          list.items.find((item) => item.status === "active") ??
          list.items[0];
        if (preferred) {
          await openSession(preferred);
        } else {
          const created = await postJson<SessionRecord>(
            "/sessions",
            { title: translate(languageRef.current, "chat.newConversation") },
            token,
          );
          if (cancelled) return;
          setSessions((all) => [created, ...all]);
          await openSession(created);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(errorText(caught));
          setConnection("offline");
        }
      } finally {
        if (!cancelled) setBooting(false);
      }
    })();
    return () => {
      cancelled = true;
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [profile]);

  if (!profile) {
    return <NicknameGate onStart={startChat} />;
  }

  return (
    <div className="grid gap-3 md:grid-cols-[250px_minmax(0,1fr)] md:items-start">
      <Card className="sticky top-20 hidden max-h-[calc(100dvh-6.5rem)] flex-col gap-3 px-3 py-4 md:flex">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-sm font-semibold">{t("chat.conversations")}</h2>
          <span className="text-[11px] text-muted-foreground">{sessions.length}</span>
        </div>
        <ConversationList
          sessions={sessions}
          activeId={active?.id}
          onSelect={(session) => void openSession(session)}
          onNew={() => void newConversation()}
        />
      </Card>

      <div className="flex min-w-0 flex-col gap-3">
        <ChatHeader
          title={active ? active.title : t("chat.connecting")}
          customerName={profile.name}
          toolNote={toolNote}
          connection={connection}
        />

        <Card className="flex items-center gap-2 overflow-hidden px-3 py-2 md:hidden">
          <ConversationList
            sessions={sessions}
            activeId={active?.id}
            onSelect={(session) => void openSession(session)}
            onNew={() => void newConversation()}
            variant="strip"
          />
        </Card>

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <ChatTranscript
          messages={messages}
          stream={stream}
          typing={typing}
          loading={booting && !active}
          bottomRef={bottomRef}
        />

        <div className="flex flex-col gap-3">
          <ChatComposer
            value={draft}
            placeholder={t("chat.placeholder")}
            sendLabel={t("common.send")}
            attachLabel={t("common.attachImage")}
            disabled={!active}
            uploading={uploading}
            onChange={setDraft}
            onSend={() => send(draft)}
            onPickImage={(file) => void upload(file)}
          />
        </div>
      </div>
    </div>
  );
}
