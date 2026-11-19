import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { en } from "./en";
import { zh } from "./zh";

export type Language = "en" | "zh";
export type Vars = Record<string, string | number>;

const STORAGE_KEY = "bridge-agents.language";
const dictionaries: Record<Language, Record<string, string>> = { en, zh };

if (import.meta.env.DEV) {
  const missing = Object.keys(en).filter((key) => !(key in zh));
  if (missing.length) console.warn("i18n: missing zh keys", missing);
}

export function translate(language: Language, key: string, vars?: Vars): string {
  let value = dictionaries[language][key] ?? en[key] ?? key;
  if (vars) {
    for (const [name, replacement] of Object.entries(vars)) {
      value = value.replaceAll(`{${name}}`, String(replacement));
    }
  }
  return value;
}

const SYSTEM_KEYS: Record<string, string> = {
  "A teammate has taken over this conversation.": "system.takeover",
  "The conversation is back with the assistant.": "system.release",
};

export function localizeSystemMessage(language: Language, content: string): string {
  const key = SYSTEM_KEYS[content.trim()];
  return key ? translate(language, key) : content;
}

export function detectLanguage(): Language {
  if (typeof window === "undefined") return "en";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "zh") return stored;
  return window.navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

interface LanguageContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string, vars?: Vars) => string;
  systemText: (content: string) => string;
}

const LanguageContext = createContext<LanguageContextValue>({
  language: "en",
  setLanguage: () => undefined,
  t: (key, vars) => translate("en", key, vars),
  systemText: (content) => content,
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(detectLanguage);

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
    window.localStorage.setItem(STORAGE_KEY, language);
  }, [language]);

  const value = useMemo<LanguageContextValue>(
    () => ({
      language,
      setLanguage: setLanguageState,
      t: (key, vars) => translate(language, key, vars),
      systemText: (content) => localizeSystemMessage(language, content),
    }),
    [language],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  return useContext(LanguageContext);
}
