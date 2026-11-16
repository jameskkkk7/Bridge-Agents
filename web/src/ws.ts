export type ConnState = "connecting" | "online" | "reconnecting" | "offline";
export interface ServerEvent {
  type: string;
  [key: string]: unknown;
}
export interface SocketHandlers {
  onState: (state: ConnState) => void;
  onEvent: (event: ServerEvent) => void;
}

export class ChatSocket {
  private socket: WebSocket | null = null;
  private token = "";
  private sessionId = "";
  private closed = false;
  private retryTimer: number | null = null;
  private pingTimer: number | null = null;
  constructor(private handlers: SocketHandlers) {}

  connect(token: string, sessionId: string): void {
    Object.assign(this, { token, sessionId, closed: false });
    this.open("connecting");
  }

  private open(state: ConnState): void {
    this.handlers.onState(state);
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${scheme}://${window.location.host}/ws/v1/chat?token=${encodeURIComponent(this.token)}`);
    this.socket = socket;
    socket.onopen = () => {
      this.handlers.onState("online");
      this.send({ type: "join", session_id: this.sessionId });
      this.pingTimer = window.setInterval(() => this.send({ type: "ping" }), 25000);
    };
    socket.onmessage = (message) => {
      try {
        this.handlers.onEvent(JSON.parse(message.data as string) as ServerEvent);
      } catch {
        /* ignore malformed frames */
      }
    };
    socket.onclose = () => {
      this.clearTimers();
      this.socket = null;
      if (this.closed) return this.handlers.onState("offline");
      this.handlers.onState("reconnecting");
      this.retryTimer = window.setTimeout(() => this.open("reconnecting"), 2000);
    };
    socket.onerror = () => socket.close();
  }

  sendMessage(content: string): void {
    this.send({ type: "message", session_id: this.sessionId, content });
  }

  close(): void {
    this.closed = true;
    this.clearTimers();
    this.socket?.close();
  }

  private send(payload: unknown): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(payload));
  }

  private clearTimers(): void {
    if (this.pingTimer !== null) window.clearInterval(this.pingTimer);
    if (this.retryTimer !== null) window.clearTimeout(this.retryTimer);
    this.pingTimer = null;
    this.retryTimer = null;
  }
}
