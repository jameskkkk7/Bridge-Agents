import { useEffect, useRef, useState } from "react";
import { deleteJson, errorText, getJson, putJson, tokenFor, uploadFile } from "../api";
import { useLanguage } from "../i18n";

type Panel = "flow" | "knowledge";

interface GraphConfig {
  nodes: unknown[];
  edges: unknown[];
}
interface Diagram {
  type: string;
  diagram: string | null;
}

interface KnowledgeDocument {
  name: string;
  bytes: number;
  modified: number;
  chunks: number;
}
interface KnowledgeStatus {
  document_count: number;
  chunk_count: number;
  term_count: number;
  dimension: number;
  embedder: string;
  built_at: string;
  directory: string;
  top_k: number;
  min_score: number;
  chunk_size: number;
  chunk_overlap: number;
  documents: KnowledgeDocument[];
}
interface KnowledgeHit {
  index: number;
  citation: string;
  document: string;
  heading: string;
  source: string;
  chunk_id: string;
  score: number;
  vector_score: number;
  lexical_score: number;
  preview: string;
}
interface KnowledgeSearch {
  query: string;
  hits: KnowledgeHit[];
  elapsed_ms: number;
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  return `${(value / 1024).toFixed(1)} KB`;
}

function FlowPanel({ token, onError }: { token: string; onError: (message: string) => void }) {
  const { t } = useLanguage();
  const [configText, setConfigText] = useState("");
  const [mermaid, setMermaid] = useState("");
  const [status, setStatus] = useState("");

  const load = async () => {
    const config = await getJson<GraphConfig>("/admin/runtime-config/agent-graph-config", token);
    setConfigText(JSON.stringify(config, null, 2));
    const diagram = await getJson<Diagram>("/admin/runtime-config/agent-graph", token);
    setMermaid(diagram.diagram ?? "");
  };

  useEffect(() => {
    void load().catch((caught) => onError(errorText(caught)));
  }, [token]);

  const save = async () => {
    onError("");
    setStatus("");
    let parsed: GraphConfig;
    try {
      parsed = JSON.parse(configText) as GraphConfig;
    } catch (caught) {
      onError(t("flow.invalidJson", { message: errorText(caught) }));
      return;
    }
    try {
      await putJson("/admin/runtime-config/agent-graph-config", parsed, token);
      await load();
      setStatus(t("flow.saved"));
    } catch (caught) {
      onError(errorText(caught));
    }
  };

  const reset = async () => {
    onError("");
    setStatus("");
    try {
      await deleteJson("/admin/runtime-config/agent-graph-config", token);
      await load();
      setStatus(t("flow.resetDone"));
    } catch (caught) {
      onError(errorText(caught));
    }
  };

  return (
    <>
      <div className="card toolbar">
        <span className="muted small">{t("flow.toolbar")}</span>
        <button className="ghost" onClick={() => void reset()}>{t("common.reset")}</button>
        <button className="primary" onClick={() => void save()}>{t("flow.save")}</button>
      </div>
      {status && <div className="banner success">{status}</div>}
      <div className="graph-grid">
        <div className="card column">
          <h3>{t("flow.configTitle")}</h3>
          <p className="muted small">{t("flow.configHelp")}</p>
          <textarea className="code" spellCheck={false} value={configText} onChange={(event) => setConfigText(event.target.value)} />
        </div>
        <div className="card column">
          <h3>{t("flow.previewTitle")}</h3>
          <p className="muted small">{t("flow.previewHelp")}</p>
          <pre className="mermaid">{mermaid || t("common.loading")}</pre>
        </div>
      </div>
    </>
  );
}

function KnowledgePanel({ token, onError }: { token: string; onError: (message: string) => void }) {
  const { t } = useLanguage();
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [query, setQuery] = useState("How do I activate Widget Pro?");
  const [result, setResult] = useState<KnowledgeSearch | null>(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const loadStatus = async () => {
    setStatus(await getJson<KnowledgeStatus>("/admin/knowledge/status", token));
  };

  useEffect(() => {
    void loadStatus().catch((caught) => onError(errorText(caught)));
  }, [token]);

  const runSearch = async () => {
    if (!query.trim()) return;
    onError("");
    setBusy("search");
    try {
      setResult(await getJson<KnowledgeSearch>(`/admin/knowledge/search?query=${encodeURIComponent(query)}&top_k=4`, token));
    } catch (caught) {
      onError(errorText(caught));
    } finally {
      setBusy("");
    }
  };

  const reindex = async () => {
    onError("");
    setNotice("");
    setBusy("reindex");
    try {
      setStatus(await uploadFile<KnowledgeStatus>("/admin/knowledge/reindex", null, token));
      setNotice(t("knowledge.reindexed"));
    } catch (caught) {
      onError(errorText(caught));
    } finally {
      setBusy("");
    }
  };

  const upload = async (file: File) => {
    onError("");
    setNotice("");
    setBusy("upload");
    try {
      await uploadFile("/admin/knowledge/documents", file, token);
      await loadStatus();
      setNotice(t("knowledge.uploaded", { name: file.name }));
    } catch (caught) {
      onError(errorText(caught));
    } finally {
      setBusy("");
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remove = async (name: string) => {
    onError("");
    setNotice("");
    setBusy(name);
    try {
      await deleteJson(`/admin/knowledge/documents/${encodeURIComponent(name)}`, token);
      await loadStatus();
      setNotice(t("knowledge.deleted", { name }));
    } catch (caught) {
      onError(errorText(caught));
    } finally {
      setBusy("");
    }
  };

  return (
    <>
      <div className="card toolbar">
        <span className="muted small">{t("knowledge.toolbar")}</span>
        <button className="ghost" disabled={busy === "reindex"} onClick={() => void reindex()}>
          {t("knowledge.reindex")}
        </button>
        <button className="primary" disabled={busy === "upload"} onClick={() => fileRef.current?.click()}>
          {busy === "upload" ? t("knowledge.uploading") : t("knowledge.upload")}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".md,.markdown,.txt"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
          }}
        />
      </div>
      {notice && <div className="banner success">{notice}</div>}

      {status && (
        <div className="stat-grid">
          <div className="card stat"><strong>{status.document_count}</strong><span>{t("knowledge.statsDocuments")}</span></div>
          <div className="card stat"><strong>{status.chunk_count}</strong><span>{t("knowledge.statsPassages")}</span></div>
          <div className="card stat"><strong>{status.dimension}</strong><span>{t("knowledge.statsDims", { embedder: status.embedder })}</span></div>
          <div className="card stat"><strong>{status.top_k}</strong><span>{t("knowledge.statsTopK")}</span></div>
        </div>
      )}

      <div className="knowledge-grid">
        <div className="card column">
          <h3>{t("knowledge.previewTitle")}</h3>
          <p className="muted small">{t("knowledge.previewHelp")}</p>
          <div className="search-row">
            <input
              value={query}
              placeholder={t("knowledge.searchPlaceholder")}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void runSearch();
              }}
            />
            <button className="primary" disabled={busy === "search"} onClick={() => void runSearch()}>
              {t("common.search")}
            </button>
          </div>
          {result && (
            <p className="muted small">
              {t("knowledge.results", { count: result.hits.length, ms: result.elapsed_ms })}
            </p>
          )}
          <div className="hits">
            {result?.hits.map((hit) => (
              <div key={hit.chunk_id} className="hit">
                <div className="hit-head">
                  <span className="pill ai">[{hit.index}] {hit.citation}</span>
                  <span className="score">{hit.score.toFixed(3)}</span>
                </div>
                <p>{hit.preview}…</p>
                <span className="muted small">
                  {hit.source} · {t("knowledge.vector")} {hit.vector_score.toFixed(2)} · {t("knowledge.lexical")} {hit.lexical_score.toFixed(2)}
                </span>
              </div>
            ))}
            {result && result.hits.length === 0 && <p className="muted small">{t("knowledge.noResults")}</p>}
          </div>
        </div>
        <div className="card column">
          <h3>{t("knowledge.documentsTitle")}</h3>
          <p className="muted small">{status?.directory}</p>
          <table>
            <thead>
              <tr>
                <th>{t("knowledge.colDocument")}</th>
                <th>{t("knowledge.colSize")}</th>
                <th>{t("knowledge.colPassages")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {status?.documents.map((document) => (
                <tr key={document.name}>
                  <td>{document.name}</td>
                  <td className="muted small">{formatBytes(document.bytes)}</td>
                  <td className="muted small">{document.chunks}</td>
                  <td>
                    <button className="link" disabled={busy === document.name} onClick={() => void remove(document.name)}>
                      {t("common.delete")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {status && status.documents.length === 0 && <p className="muted small">{t("knowledge.empty")}</p>}
        </div>
      </div>
    </>
  );
}

export default function GraphPage() {
  const { t } = useLanguage();
  const [panel, setPanel] = useState<Panel>("flow");
  const [error, setError] = useState("");
  const [token, setToken] = useState("");
  const tokenRef = useRef("");

  useEffect(() => {
    void (async () => {
      try {
        tokenRef.current = await tokenFor("agent");
        setToken(tokenRef.current);
      } catch (caught) {
        setError(errorText(caught));
      }
    })();
  }, []);

  return (
    <section className="page">
      <div className="card page-head">
        <div>
          <h2>{t("studio.title")}</h2>
          <p className="muted small">{t("studio.subtitle")}</p>
        </div>
        <div className="tabs">
          <button className={panel === "flow" ? "tab active" : "tab"} onClick={() => setPanel("flow")}>
            {t("studio.flow")}
          </button>
          <button className={panel === "knowledge" ? "tab active" : "tab"} onClick={() => setPanel("knowledge")}>
            {t("studio.knowledge")}
          </button>
        </div>
      </div>
      {error && <div className="banner error">{error}</div>}
      {token && panel === "flow" && <FlowPanel token={token} onError={setError} />}
      {token && panel === "knowledge" && <KnowledgePanel token={token} onError={setError} />}
    </section>
  );
}
