import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { BrandMark } from "@/components/brand-mark";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/i18n";
import AdminPage from "@/pages/AdminPage";
import ChatPage from "@/pages/ChatPage";
import GraphPage from "@/pages/GraphPage";
import { useTheme } from "@/theme";

type StaffView = "support" | "studio";

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
    <Button
      variant="outline"
      size="icon-sm"
      onClick={toggleTheme}
      title={theme === "dark" ? t("theme.toLight") : t("theme.toDark")}
      aria-label={theme === "dark" ? t("theme.toLight") : t("theme.toDark")}
      className="rounded-full"
    >
      {theme === "dark" ? <Sun /> : <Moon />}
    </Button>
  );

  const languageSwitch = (
    <div
      className="flex items-center gap-0.5 rounded-full border border-border bg-muted p-0.5"
      role="group"
      aria-label="Language"
    >
      {(
        [
          ["en", "EN"],
          ["zh", "中文"],
        ] as const
      ).map(([code, label]) => (
        <button
          key={code}
          onClick={() => setLanguage(code)}
          className={
            language === code
              ? "rounded-full bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground"
              : "rounded-full px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground"
          }
        >
          {label}
        </button>
      ))}
    </div>
  );

  if (staffView) {
    return (
      <div className="min-h-dvh pb-20">
        <div className="sticky top-0 z-40 border-b border-border/60 bg-gradient-to-b from-background/95 via-background/85 to-background/70 backdrop-blur-xl backdrop-saturate-150">
          <div className="mx-auto max-w-6xl px-3 pt-3 pb-2 sm:px-6">
            <header className="flex flex-wrap items-center gap-2 rounded-xl border border-border/80 bg-card/75 px-3 py-2.5 shadow-sm sm:gap-3 sm:px-4">
          <button
            className="flex min-w-0 items-center gap-2.5 text-left"
            onClick={() => navigate("/admin")}
          >
            <BrandMark />
            <span className="min-w-0">
              <strong className="block truncate text-sm font-semibold tracking-tight">
                Bridge-Agents
              </strong>
              <small className="hidden text-[10px] tracking-[0.14em] text-muted-foreground uppercase sm:block">
                {t("app.tagline")}
              </small>
            </span>
          </button>
          <Badge variant="outline" className="hidden sm:inline-flex">
            {t("staff.badge")}
          </Badge>
          <nav className="order-3 flex w-full items-center gap-1 sm:order-none sm:ml-auto sm:w-auto">
            <Button
              variant={staffView === "support" ? "default" : "ghost"}
              size="sm"
              className="flex-1 sm:flex-none"
              onClick={() => navigate("/admin")}
            >
              {t("app.support")}
            </Button>
            <Button
              variant={staffView === "studio" ? "default" : "ghost"}
              size="sm"
              className="flex-1 sm:flex-none"
              onClick={() => navigate("/admin/studio")}
            >
              {t("app.studio")}
            </Button>
          </nav>
          <div className="ml-auto flex items-center gap-2 sm:ml-0">
            {themeToggle}
            {languageSwitch}
            <span className="hidden text-xs text-muted-foreground sm:inline">v0.1.0</span>
          </div>
            </header>
          </div>
        </div>
        <main className="mx-auto max-w-6xl px-3 sm:px-6">
          {staffView === "support" && <AdminPage />}
          {staffView === "studio" && <GraphPage />}
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-dvh pb-16">
      <div className="sticky top-0 z-40 border-b border-border/60 bg-gradient-to-b from-background/95 via-background/85 to-background/70 backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto max-w-6xl px-3 pt-3 pb-2 sm:px-6">
          <header className="flex items-center gap-2 rounded-xl border border-border/80 bg-card/75 px-3 py-2.5 shadow-sm sm:gap-3 sm:px-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <BrandMark />
          <span className="min-w-0">
            <strong className="block truncate text-sm font-semibold tracking-tight">
              Bridge-Agents
            </strong>
            <small className="hidden text-[10px] tracking-[0.14em] text-muted-foreground uppercase sm:block">
              {t("app.tagline")}
            </small>
          </span>
        </div>
        <span className="ml-auto hidden text-xs text-muted-foreground sm:inline">
          {t("customer.areaLabel")}
        </span>
        <div className="ml-auto flex items-center gap-2 sm:ml-0">
          {themeToggle}
          {languageSwitch}
          <span className="hidden text-xs text-muted-foreground sm:inline">v0.1.0</span>
        </div>
          </header>
        </div>
      </div>
      <main className="mx-auto max-w-6xl px-3 sm:px-6">
        <ChatPage />
      </main>
    </div>
  );
}
