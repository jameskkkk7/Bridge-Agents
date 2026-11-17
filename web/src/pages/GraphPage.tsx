import { useEffect, useRef, useState } from "react";
import { deleteJson, errorText, getJson, putJson, tokenFor, uploadFile } from "../api";

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
      onError(`Invalid JSON: ${errorText(caught)}`);
      return;
    }
    try {
      await putJson("/admin/runtime-config/agent-graph-config", parsed, token);
      await load();
      setStatus("Flow saved and recompiled.");
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
      setStatus("Saved flow removed — the built-in graph is active again.");
    } catch (caught) {
      onError(errorText(caught));
    }
  };

  return (
    <>
      <div className="card toolbar">
        <span className="muted small">Saving compiles the graph before it replaces the live one.</span>
        <button className="ghost" onClick={() => void reset()}>Reset</button>
        <button className="primary" onClick={() => void save()}>Save &amp; compile</button>
      </div>
      {status && <div className="banner success">{status}</div>}
      <div className="graph-grid">
        <div className="card column">
          <h3>Graph configuration</h3>
          <p className="muted small">
            The default flow is system → retrieval → agent → review → end. Saving compiles the graph before it goes live.
          </p>
          <textarea className="code" spellCheck={false} value={configText} onChange={(event) => setConfigText(event.target.value)} />
        </div>
        <div className="card column">
          <h3>Compiled preview</h3>
          <p className="muted small">Mermaid source of the live graph. Paste it into mermaid.live to explore it.</p>
          <pre className="mermaid">{mermaid || "Loading…"}</pre>
        </div>
      </div>
    </>
  );
}

function KnowledgePanel({ token, onError }: { token: string; onError: (message: string) => void }) {
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
      setNotice("Index rebuilt from the knowledge directory.");
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
      setNotice(`Uploaded ${file.name} and reindexed.`);
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
      setNotice(`Deleted ${name}.`);
    } catch (caught) {
      onError(errorText(caught));
    } finally {
      setBusy("");
    }
  };

  return (
    <>
      <div className="card toolbar">
        <span className="muted small">Uploads and deletes reindex immediately.</span>
        <button className="ghost" disabled={busy === "reindex"} onClick={() => void reindex()}>
          Reindex
        </button>
        <button className="primary" disabled={busy === "upload"} onClick={() => fileRef.current?.click()}>
          {busy === "upload" ? "Uploading…" : "Upload document"}
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
          <div className="card stat"><strong>{status.document_count}</strong><span>documents</span></div>
          <div className="card stat"><strong>{status.chunk_count}</strong><span>passages</span></div>
          <div className="card stat"><strong>{status.dimension}</strong><span>{status.embedder} dims</span></div>
          <div className="card stat"><strong>{status.top_k}</strong><span>passages per turn</span></div>
        </div>
      )}

      <div className="knowledge-grid">
        <div className="card column">
          <h3>Retrieval preview</h3>
          <p className="muted small">
            Hybrid search: {status ? `${Math.round(100 * 0.6)}% vector + ${Math.round(100 * 0.4)}% lexical` : "vector + lexical"}.
            Exactly what the retrieval node feeds the assistant.
          </p>
          <div className="search-row">
            <input
              value={query}
              placeholder="Ask the knowledge base…"
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void runSearch();
              }}
            />
            <button className="primary" disabled={busy === "search"} onClick={() => void runSearch()}>
              Search
            </button>
          </div>
          {result && (
            <p className="muted small">
              {result.hits.length} passage(s) in {result.elapsed_ms} ms
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
                  {hit.source} · vector {hit.vector_score.toFixed(2)} · lexical {hit.lexical_score.toFixed(2)}
                </span>
              </div>
            ))}
            {result && result.hits.length === 0 && <p className="muted small">No passage passed the score threshold.</p>}
          </div>
        </div>
        <div className="card column">
          <h3>Documents</h3>
          <p className="muted small">{status?.directory}</p>
          <table>
            <thead><tr><th>Document</th><th>Size</th><th>Passages</th><th /></tr></thead>
            <tbody>
              {status?.documents.map((document) => (
                <tr key={document.name}>
                  <td>{document.name}</td>
                  <td className="muted small">{formatBytes(document.bytes)}</td>
                  <td className="muted small">{document.chunks}</td>
                  <td>
                    <button className="link" disabled={busy === document.name} onClick={() => void remove(document.name)}>
                      delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {status && status.documents.length === 0 && <p className="muted small">No documents yet — upload a markdown file.</p>}
        </div>
      </div>
    </>
  );
}

export default function GraphPage() {
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
          <h2>Studio</h2>
          <p className="muted small">
            The assistant answers from this knowledge base, and every reply still passes the review gate.
          </p>
        </div>
        <div className="tabs">
          <button className={panel === "flow" ? "tab active" : "tab"} onClick={() => setPanel("flow")}>Flow</button>
          <button className={panel === "knowledge" ? "tab active" : "tab"} onClick={() => setPanel("knowledge")}>Knowledge</button>
        </div>
      </div>
      {error && <div className="banner error">{error}</div>}
      {token && panel === "flow" && <FlowPanel token={token} onError={setError} />}
      {token && panel === "knowledge" && <KnowledgePanel token={token} onError={setError} />}
    </section>
  );
}
