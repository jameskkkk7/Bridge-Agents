import { useEffect, useRef, useState } from "react";
import {
  errorText, getJson, imageBlobUrl, imageIdFromContent, MessageList, MessageRecord,
  postJson, SessionList, SessionRecord, tokenFor,
} from "../api";
import { ChatSocket, ConnState, ServerEvent } from "../ws";

interface ViewMessage {
  id: string;
  kind: "user" | "agent" | "system" | "image";
  content: string;
  imageId?: string;
  imageUrl?: string;
}

const QUICK: [string, string][] = [
  ["Ask about a refund", "Can you guarantee a refund?"],
  ["Try a tool call", "[[tool]] what time is it?"],
];

export default function ChatPage() {
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

  useEffect(() => {
    let cancelled = false;
    const hydrate = async (sessionId: string, imageId: string) => {
      try {
        const url = await imageBlobUrl(sessionId, imageId, tokenRef.current);
        setMessages((all) => all.map((m) => (m.imageId === imageId ? { ...m, imageUrl: url } : m)));
      } catch {
        setError("The image could not be loaded.");
      }
    };
    const view = (record: MessageRecord): ViewMessage =>
      record.message_type === "image"
        ? { id: record.id, kind: "image", content: "image", imageId: imageIdFromContent(record.content) ?? undefined }
        : {
            id: record.id,
            kind: record.message_type === "system" ? "system" : record.sender_type === "user" ? "user" : "agent",
            content: record.content,
          };
    const onEvent = (event: ServerEvent) => {
      const active = sessionRef.current;
      if (!active) return;
      if (event.type === "message") {
        const record = event as unknown as MessageRecord;
        const next = view(record);
        setMessages((all) => (all.some((m) => m.id === next.id) ? all.map((m) => (m.id === next.id ? next : m)) : [...all, next]));
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
        setMessages((all) => [...all, { id: String(event.id ?? imageId), kind: "image", content: String(event.filename ?? "image"), imageId }]);
        void hydrate(active.id, imageId);
      } else if (event.type === "error") {
        setError(String(event.message ?? "The server reported an error."));
      }
    };
    const boot = async () => {
      try {
        const token = await tokenFor("user");
        tokenRef.current = token;
        const list = await getJson<SessionList>("/sessions?limit=20", token);
        const active =
          list.items.find((item) => item.status === "active") ??
          (await postJson<SessionRecord>("/sessions", { title: "Live demo conversation" }, token));
        if (cancelled) return;
        setSession(active);
        sessionRef.current = active;
        const history = await getJson<MessageList>(`/sessions/${active.id}/messages?limit=50`, token);
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
        throw new Error(payload.message ?? "The image upload failed.");
      }
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <section className="page">
      <div className="card chat-head">
        <div>
          <h2>{session ? session.title : "Connecting to your conversation…"}</h2>
          <p className="muted small">customer view · {session ? `session ${session.id.slice(0, 8)}` : "preparing"}</p>
        </div>
        <div className="row">
          {toolNote && <span className="pill tool">tool: {toolNote}</span>}
          <span className={`status ${connection}`}>{connection}</span>
        </div>
      </div>
      {error && <div className="banner error">{error}</div>}
      <div className="card messages">
        {messages.length === 0 && !typing && (
          <div className="empty"><p>Say hello — or use a demo prompt to see the review gate and a tool call.</p></div>
        )}
        {messages.map((message) =>
          message.kind === "system" ? (
            <div key={message.id} className="system-note">{message.content}</div>
          ) : (
            <div key={message.id} className={`bubble ${message.kind}`}>
              {message.kind === "image"
                ? message.imageUrl ? <img src={message.imageUrl} alt="uploaded attachment" /> : <span className="muted">loading image…</span>
                : message.content}
            </div>
          ),
        )}
        {stream && <div className="bubble agent">{stream}<span className="caret" /></div>}
        {typing && !stream && <div className="typing"><span /><span /><span /></div>}
        <div ref={bottomRef} />
      </div>
      <div className="card composer">
        <div className="chips">
          {QUICK.map(([label, prompt]) => (
            <button key={label} className="chip" onClick={() => send(prompt)}>{label}</button>
          ))}
          <span className="hint">Enter to send · Shift+Enter for a new line</span>
        </div>
        <div className="composer-row">
          <button className="icon" onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? "…" : "+"}
          </button>
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/gif,image/webp,image/bmp" hidden
            onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); }} />
          <textarea value={draft} placeholder="Ask the assistant something…" onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(draft); } }} />
          <button className="primary" onClick={() => send(draft)}>Send</button>
        </div>
      </div>
    </section>
  );
}
