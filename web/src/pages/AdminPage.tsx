import { useEffect, useRef, useState } from "react";
import {
  AdminSession,
  AdminSessionList,
  errorText,
  getJson,
  MessageList,
  MessageRecord,
  putJson,
  tokenFor,
} from "../api";
import { ChatSocket, ConnState } from "../ws";

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

export default function AdminPage() {
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
          setError(String(event.message ?? "The server reported an error."));
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
        updated.human_takeover
          ? "Takeover on — the AI stops and its in-flight reply was cancelled."
          : "Takeover released — the assistant answers again.",
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
      setError("Take over the conversation before replying.");
      return;
    }
    if (!socketRef.current) {
      setError("The realtime connection is not ready yet.");
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
      setNotice("Conversation closed.");
      await loadSessions(tokenRef.current);
    } catch (caught) {
      setError(errorText(caught));
    }
  };

  const composerEnabled = Boolean(selected?.human_takeover && selected?.status !== "closed");

  return (
    <section className="page">
      <div className="card page-head">
        <div>
          <h2>Support desk</h2>
          <p className="muted small">
            Watch conversations live, take over when a human should answer, and reply
            from here — the customer sees it immediately.
          </p>
        </div>
        <div className="row">
         {selected && <span className={`status ${connection}`}>{connection}</span>}
          <button
            className="ghost"
            onClick={() =>
              void loadSessions(tokenRef.current).catch((caught) => setError(errorText(caught)))
            }
          >
            Refresh
          </button>
        </div>
      </div>
      {error && <div className="banner error">{error}</div>}
      {notice && <div className="banner success">{notice}</div>}
      <div className="admin-grid">
        <div className="card column">
          <div className="table-head">
            <h3>Conversations</h3>
            <span className="muted small">{sessions.length} shown</span>
          </div>
          <table>
            <thead><tr><th>Customer</th><th>Status</th><th>AI</th></tr></thead>
            <tbody>
              {sessions.map((session) => (
                <tr
                  key={session.id}
                  className={selected?.id === session.id ? "selected" : ""}
                  onClick={() => void open(session)}
                >
                  <td>
                    <strong>{session.user_email ?? session.user_id.slice(0, 8)}</strong>
                    <span className="muted small block">{session.title}</span>
                  </td>
                  <td><span className={`pill ${session.status}`}>{session.status}</span></td>
                  <td>
                    {session.human_takeover ? (
                      <span className="pill takeover">human</span>
                    ) : (
                      <span className="pill ai">assistant</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card column">
          <div className="table-head">
            <h3>
              {selected
                ? `Conversation · ${(selected.user_email ?? selected.id).slice(0, 22)}`
                : "Pick a conversation"}
            </h3>
            {selected && (
              <div className="row">
                <button
                  className={selected.human_takeover ? "ghost" : "primary"}
                  onClick={() => void takeover()}
                >
                  {selected.human_takeover ? "Release to AI" : "Take over"}
                </button>
                <button
                  className="ghost"
                  disabled={selected.status === "closed"}
                  onClick={() => void close()}
                >
                  Close
                </button>
              </div>
            )}
          </div>
          {!selected && <p className="empty">Select a conversation to review its transcript.</p>}
          {selected && (
            <>
              <div className="transcript">
                {messages.length === 0 && <p className="muted small">No messages yet.</p>}
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`transcript-row ${message.sender_type} ${message.message_type}`}
                  >
                    <span className="who">
                      {message.message_type === "system" ? "system" : message.sender_type}
                    </span>
                    <span className="what">
                      {message.message_type === "image" ? "[image]" : message.content}
                    </span>
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>
              <div className="admin-composer">
                <textarea
                  value={draft}
                  rows={2}
                  placeholder={
                    composerEnabled
                      ? "Reply as support… Enter to send, Shift+Enter for a new line"
                      : "Take over the conversation to reply"
                  }
                  disabled={!composerEnabled}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      send();
                    }
                  }}
                />
                <button className="primary" disabled={!composerEnabled} onClick={send}>
                  Send reply
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
