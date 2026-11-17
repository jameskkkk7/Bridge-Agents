import { useEffect, useState } from "react";
import { useLanguage } from "./i18n";
import AdminPage from "./pages/AdminPage";
import ChatPage from "./pages/ChatPage";
import GraphPage from "./pages/GraphPage";

type Route = "chat" | "graph" | "admin";
const PATHS: Record<string, Route> = { "/": "chat", "/graph": "graph", "/admin": "admin" };
const ROUTE_KEYS: Record<Route, string> = {
  chat: "chat",
  graph: "studio",
  admin: "support",
};
const routeFromPath = (): Route => PATHS[window.location.pathname] ?? "chat";

export default function App() {
  const [route, setRoute] = useState<Route>(routeFromPath());
  const { language, setLanguage, t } = useLanguage();

  useEffect(() => {
    const sync = () => setRoute(routeFromPath());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  useEffect(() => {
    document.title = `Bridge-Agents · ${t(`title.${ROUTE_KEYS[route]}`)}`;
  }, [route, language, t]);

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
            <small>{t("app.tagline")}</small>
          </div>
        </div>
        <nav>
          {(["chat", "graph", "admin"] as Route[]).map((key) => (
            <button
              key={key}
              className={route === key ? "nav-btn active" : "nav-btn"}
              onClick={() => go(key)}
            >
              {t(`app.${ROUTE_KEYS[key]}`)}
            </button>
          ))}
        </nav>
        <div className="lang-switch" role="group" aria-label="Language">
          <button
            className={language === "en" ? "lang-btn active" : "lang-btn"}
            onClick={() => setLanguage("en")}
          >
            EN
          </button>
          <button
            className={language === "zh" ? "lang-btn active" : "lang-btn"}
            onClick={() => setLanguage("zh")}
          >
            中文
          </button>
        </div>
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
