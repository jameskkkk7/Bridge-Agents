export type Role = "user" | "agent";

export interface User {
  id: string;
  role: string;
  email?: string | null;
  display_name?: string | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface SessionRecord {
  id: string;
  user_id: string;
  title: string;
  status: string;
  human_takeover: boolean;
  unread_count: number;
  created_at: string;
  updated_at: string;
}

export interface SessionList {
  items: SessionRecord[];
  total: number;
  page: number;
  limit: number;
}

export interface MessageRecord {
  id: string;
  session_id: string;
  sender_id: string;
  sender_type: string;
  sender_kind?: string;
  content: string;
  message_type: string;
  created_at: string;
}

export interface MessageList {
  items: MessageRecord[];
  has_more: boolean;
}

export interface AdminSession {
  id: string;
  user_id: string;
  user_email: string | null;
  customer_name?: string | null;
  title: string;
  status: string;
  human_takeover: boolean;
  created_at: string;
  updated_at: string;
}

export interface AdminSessionList {
  items: AdminSession[];
  total: number;
  page: number;
  limit: number;
}

const API = "/api/v1";
const KEYS = { user: "bridge-agents.token.user", agent: "bridge-agents.token.agent" };

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { message?: string; detail?: string };
      message = body.message ?? body.detail ?? message;
    } catch {
      /* keep status text */
    }
    throw new Error(message);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export async function tokenFor(
  role: Role,
  options?: { clientId?: string; name?: string },
): Promise<string> {
  const key = options?.clientId ? `${KEYS[role]}.${options.clientId}` : KEYS[role];
  const cached = window.sessionStorage.getItem(key);
  if (cached) return cached;
  const params = new URLSearchParams({ role });
  if (options?.clientId) params.set("client_id", options.clientId);
  if (options?.name) params.set("name", options.name);
  const auth = await request<AuthResponse>(`/auth/dev-login?${params.toString()}`, {
    method: "POST",
  });
  window.sessionStorage.setItem(key, auth.access_token);
  return auth.access_token;
}

export const getJson = <T,>(path: string, token: string) => request<T>(path, {}, token);
export const postJson = <T,>(path: string, body: unknown, token: string) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) }, token);
export const putJson = <T,>(path: string, body: unknown, token: string) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) }, token);
export const deleteJson = <T,>(path: string, token: string) =>
  request<T>(path, { method: "DELETE" }, token);

export async function uploadFile<T>(path: string, file: File | null, token: string): Promise<T> {
  const body = new FormData();
  if (file) body.append("file", file);
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { message?: string; detail?: string };
      message = payload.message ?? payload.detail ?? message;
    } catch {
      /* keep status text */
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export async function imageBlobUrl(sessionId: string, imageId: string, token: string): Promise<string> {
  const response = await fetch(`${API}/sessions/${sessionId}/images/${imageId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error("Could not load the image");
  return URL.createObjectURL(await response.blob());
}

export function imageIdFromContent(content: string): string | null {
  const match = content.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
  return match ? match[0] : null;
}

export const errorText = (error: unknown) => (error instanceof Error ? error.message : String(error));
