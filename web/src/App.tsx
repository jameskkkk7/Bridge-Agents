import { useEffect, useState } from "react";
import AdminPage from "./pages/AdminPage";
import ChatPage from "./pages/ChatPage";
import GraphPage from "./pages/GraphPage";

type Route = "chat" | "graph" | "admin";
const PATHS: Record<string, Route> = { "/": "chat", "/graph": "graph", "/admin": "admin" };
const routeFromPath = (): Route => PATHS[window.location.pathname] ?? "chat";

export default function App() {
  const [route, setRoute] = useState<Route>(routeFromPath());

  useEffect(() => {
    const sync = () => setRoute(routeFromPath());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  const go = (next: Route) => {
    const path = next === "chat" ? "/" : `/${next}`;
    if (window.location.pathname !== path) window.history.pushState({}, "", path);
    setRoute(next);
  };

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand" onClick={() => go("chat")}>
          <span className="brand-mark" />
          <div>
            <strong>Bridge-Agents</strong>
            <small>review-gated agent runtime</small>
          </div>
        </div>
        <nav>
          {([["chat", "Chat"], ["graph", "Studio"], ["admin", "Support"]] as [Route, string][]).map(([key, label]) => (
            <button key={key} className={route === key ? "nav-btn active" : "nav-btn"} onClick={() => go(key)}>
              {label}
            </button>
          ))}
        </nav>
        <div className="version">v0.1.0</div>
      </header>
      <main>
        {route === "chat" && <ChatPage />}
        {route === "graph" && <GraphPage />}
        {route === "admin" && <AdminPage />}
      </main>
    </div>
  );
}
