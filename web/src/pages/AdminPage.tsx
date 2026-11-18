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
import { useLanguage } from "../i18n";
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
            .querySelector(".admin-grid .card.column:last-child")
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

  const statusLabel = (status: string) =>
    t(`admin.status.${status}`) === `admin.status.${status}` ? status : t(`admin.status.${status}`);
  const composerEnabled = Boolean(selected?.human_takeover && selected?.status !== "closed");

  return (
    <section className="page">
      <div className="card page-head">
        <div>
          <h2>{t("admin.title")}</h2>
          <p className="muted small">{t("admin.subtitle")}</p>
        </div>
        <div className="row">
          {selected && <span className={`status ${connection}`}>{t(`status.${connection}`)}</span>}
          <button
            className="ghost"
            onClick={() =>
              void loadSessions(tokenRef.current).catch((caught) => setError(errorText(caught)))
            }
          >
            {t("common.refresh")}
          </button>
        </div>
      </div>
      {error && <div className="banner error">{error}</div>}
      {notice && <div className="banner success">{notice}</div>}
      <div className="admin-grid">
        <div className="card column">
          <div className="table-head">
            <h3>{t("admin.conversations")}</h3>
            <span className="muted small">{t("admin.shown", { count: sessions.length })}</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t("admin.colCustomer")}</th>
                <th>{t("admin.colStatus")}</th>
                <th>{t("admin.colAI")}</th>
              </tr>
            </thead>
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
                  <td><span className={`pill ${session.status}`}>{statusLabel(session.status)}</span></td>
                  <td>
                    {session.human_takeover ? (
                      <span className="pill takeover">{t("admin.badgeHuman")}</span>
                    ) : (
                      <span className="pill ai">{t("admin.badgeAssistant")}</span>
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
                ? t("admin.conversation", {
                    name: (selected.user_email ?? selected.id).slice(0, 22),
                  })
                : t("admin.pick")}
            </h3>
            {selected && (
              <div className="row">
                <button
                  className={selected.human_takeover ? "ghost" : "primary"}
                  onClick={() => void takeover()}
                >
                  {selected.human_takeover ? t("admin.release") : t("admin.takeOver")}
                </button>
                <button
                  className="ghost"
                  disabled={selected.status === "closed"}
                  onClick={() => void close()}
                >
                  {t("common.close")}
                </button>
              </div>
            )}
          </div>
          {!selected && <p className="empty">{t("admin.pickHint")}</p>}
          {selected && (
            <>
              <div className="transcript">
                {messages.length === 0 && <p className="muted small">{t("admin.noMessages")}</p>}
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`transcript-row ${message.sender_type} ${message.message_type}`}
                  >
                    <span className="who">
                      {message.message_type === "system"
                        ? t("admin.system")
                        : message.sender_type === "user"
                          ? t("admin.user")
                          : t("admin.agent")}
                    </span>
                    <span className="what">
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
              <div className="admin-composer">
                <textarea
                  value={draft}
                  rows={2}
                  placeholder={
                    composerEnabled ? t("admin.placeholderEnabled") : t("admin.placeholderDisabled")
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
                  {t("admin.sendReply")}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
