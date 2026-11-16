import { useEffect, useRef, useState } from "react";
import {
  AdminSession, AdminSessionList, errorText, getJson, MessageList, MessageRecord,
  putJson, tokenFor,
} from "../api";

export default function AdminPage() {
  const [sessions, setSessions] = useState<AdminSession[]>([]);
  const [selected, setSelected] = useState<AdminSession | null>(null);
  const [messages, setMessages] = useState<MessageRecord[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const tokenRef = useRef("");

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
  }, []);

  const open = async (session: AdminSession) => {
    setError("");
    setNotice("");
    setSelected(session);
    try {
      const history = await getJson<MessageList>(`/admin/sessions/${session.id}/messages?limit=50`, tokenRef.current);
      setMessages(history.items.slice().reverse());
    } catch (caught) {
      setError(errorText(caught));
    }
  };

  const takeover = async () => {
    if (!selected) return;
    setError("");
    setNotice("");
    try {
      const updated = await putJson<AdminSession>(`/admin/sessions/${selected.id}/takeover`, { enabled: !selected.human_takeover }, tokenRef.current);
      setSelected(updated);
      setNotice(updated.human_takeover ? "Takeover on — the AI stops and its in-flight reply was cancelled." : "Takeover released — the assistant answers again.");
      await loadSessions(tokenRef.current);
      await open(updated);
    } catch (caught) {
      setError(errorText(caught));
    }
  };

  const close = async () => {
    if (!selected) return;
    setError("");
    try {
      const updated = await putJson<AdminSession>(`/admin/sessions/${selected.id}/status`, { status: "closed" }, tokenRef.current);
      setSelected(updated);
      setNotice("Conversation closed.");
      await loadSessions(tokenRef.current);
    } catch (caught) {
      setError(errorText(caught));
    }
  };

  return (
    <section className="page">
      <div className="card page-head">
        <div>
          <h2>Support desk</h2>
          <p className="muted small">Watch conversations, review what the assistant said, and take over when a human should answer.</p>
        </div>
        <button className="ghost" onClick={() => void loadSessions(tokenRef.current).catch((caught) => setError(errorText(caught)))}>
          Refresh
        </button>
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
                <tr key={session.id} className={selected?.id === session.id ? "selected" : ""} onClick={() => void open(session)}>
                  <td>
                    <strong>{session.user_email ?? session.user_id.slice(0, 8)}</strong>
                    <span className="muted small block">{session.title}</span>
                  </td>
                  <td><span className={`pill ${session.status}`}>{session.status}</span></td>
                  <td>{session.human_takeover ? <span className="pill takeover">human</span> : <span className="pill ai">assistant</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card column">
          <div className="table-head">
            <h3>{selected ? `Conversation · ${(selected.user_email ?? selected.id).slice(0, 22)}` : "Pick a conversation"}</h3>
            {selected && (
              <div className="row">
                <button className={selected.human_takeover ? "ghost" : "primary"} onClick={() => void takeover()}>
                  {selected.human_takeover ? "Release to AI" : "Take over"}
                </button>
                <button className="ghost" disabled={selected.status === "closed"} onClick={() => void close()}>Close</button>
              </div>
            )}
          </div>
          {!selected && <p className="empty">Select a conversation to review its transcript.</p>}
          {selected && (
            <div className="transcript">
              {messages.length === 0 && <p className="muted small">No messages yet.</p>}
              {messages.map((message) => (
                <div key={message.id} className={`transcript-row ${message.sender_type} ${message.message_type}`}>
                  <span className="who">{message.message_type === "system" ? "system" : message.sender_type}</span>
                  <span className="what">{message.message_type === "image" ? "[image]" : message.content}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
