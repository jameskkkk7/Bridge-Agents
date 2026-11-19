import { useEffect, useState } from "react";
import { useLanguage } from "./i18n";
import { useTheme } from "./theme";
import AdminPage from "./pages/AdminPage";
import ChatPage from "./pages/ChatPage";
import GraphPage from "./pages/GraphPage";

type StaffView = "support" | "studio";


function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" />
    </svg>
  );
}


const STAFF_PATHS: Record<string, StaffView> = {
  "/admin": "support",
  "/admin/studio": "studio",
};

function currentPath(): string {
  const path = window.location.pathname.replace(/\/+$/, "");
  return path || "/";
}

/** Normalize legacy and unknown paths onto the two entry points. */
function normalizePath(path: string): string {
  if (path === "/graph") return "/admin/studio";
  if (path === "/chat") return "/";
  if (path in STAFF_PATHS) return path;
  if (path.startsWith("/admin")) return "/admin";
  return "/";
}

export default function App() {
  const { language, setLanguage, t } = useLanguage();
  const { theme, toggleTheme } = useTheme();
  const [path, setPath] = useState(() => normalizePath(currentPath()));
  const staffView = STAFF_PATHS[path];

  useEffect(() => {
    if (normalizePath(currentPath()) !== currentPath()) {
      window.history.replaceState({}, "", normalizePath(currentPath()));
    }
    const sync = () => setPath(normalizePath(currentPath()));
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  useEffect(() => {
    const titleKey = staffView
      ? staffView === "studio"
        ? "title.studio"
        : "title.support"
      : "title.customer";
    document.title = `Bridge-Agents · ${t(titleKey)}`;
  }, [path, language, t, staffView]);

  const navigate = (target: string) => {
    if (currentPath() !== target) window.history.pushState({}, "", target);
    setPath(target);
  };

  const themeToggle = (
    <button
      className="theme-btn"
      onClick={toggleTheme}
      title={theme === "dark" ? t("theme.toLight") : t("theme.toDark")}
      aria-label={theme === "dark" ? t("theme.toLight") : t("theme.toDark")}
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );

  const languageSwitch = (
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
  );

  if (staffView) {
    return (
      <div className="shell staff-shell">
        <header className="topbar">
          <div className="brand" onClick={() => navigate("/admin")}>
            <span className="brand-mark" />
            <div>
              <strong>Bridge-Agents</strong>
              <small>{t("app.tagline")}</small>
            </div>
          </div>
          <span className="pill staff">{t("staff.badge")}</span>
          <nav>
            <button
              className={staffView === "support" ? "nav-btn active" : "nav-btn"}
              onClick={() => navigate("/admin")}
            >
              {t("app.support")}
            </button>
            <button
              className={staffView === "studio" ? "nav-btn active" : "nav-btn"}
              onClick={() => navigate("/admin/studio")}
            >
              {t("app.studio")}
            </button>
          </nav>
          {themeToggle}
          {languageSwitch}
          <div className="version">v0.1.0</div>
        </header>
        <main>
          {staffView === "support" && <AdminPage />}
          {staffView === "studio" && <GraphPage />}
        </main>
      </div>
    );
  }

  return (
    <div className="shell customer-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" />
          <div>
            <strong>Bridge-Agents</strong>
            <small>{t("app.tagline")}</small>
          </div>
        </div>
        <span className="customer-label muted small">{t("customer.areaLabel")}</span>
        {themeToggle}
        {languageSwitch}
        <div className="version">v0.1.0</div>
      </header>
      <main>
        <ChatPage />
      </main>
    </div>
  );
}
