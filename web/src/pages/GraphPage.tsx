import { useEffect, useRef, useState } from "react";
import { deleteJson, errorText, getJson, putJson, tokenFor } from "../api";

interface GraphConfig {
  nodes: unknown[];
  edges: unknown[];
}
interface Diagram {
  type: string;
  diagram: string | null;
}

export default function GraphPage() {
  const [configText, setConfigText] = useState("");
  const [mermaid, setMermaid] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const tokenRef = useRef("");

  const load = async (token: string) => {
    const config = await getJson<GraphConfig>("/admin/runtime-config/agent-graph-config", token);
    setConfigText(JSON.stringify(config, null, 2));
    const diagram = await getJson<Diagram>("/admin/runtime-config/agent-graph", token);
    setMermaid(diagram.diagram ?? "");
  };

  useEffect(() => {
    void (async () => {
      try {
        tokenRef.current = await tokenFor("agent");
        await load(tokenRef.current);
      } catch (caught) {
        setError(errorText(caught));
      }
    })();
  }, []);

  const save = async () => {
    setError("");
    setStatus("");
    let parsed: GraphConfig;
    try {
      parsed = JSON.parse(configText) as GraphConfig;
    } catch (caught) {
      setError(`Invalid JSON: ${errorText(caught)}`);
      return;
    }
    try {
      await putJson("/admin/runtime-config/agent-graph-config", parsed, tokenRef.current);
      await load(tokenRef.current);
      setStatus("Flow saved and recompiled.");
    } catch (caught) {
      setError(errorText(caught));
    }
  };

  const reset = async () => {
    setError("");
    setStatus("");
    try {
      await deleteJson("/admin/runtime-config/agent-graph-config", tokenRef.current);
      await load(tokenRef.current);
      setStatus("Saved flow removed — the built-in graph is active again.");
    } catch (caught) {
      setError(errorText(caught));
    }
  };

  return (
    <section className="page">
      <div className="card page-head">
        <div>
          <h2>Conversation flow</h2>
          <p className="muted small">
            Edit the graph as JSON. Saving compiles it before it goes live, so a broken route is rejected instead of shipped.
          </p>
        </div>
        <div className="row">
          <button className="ghost" onClick={() => void reset()}>Reset</button>
          <button className="primary" onClick={() => void save()}>Save &amp; compile</button>
        </div>
      </div>
      {error && <div className="banner error">{error}</div>}
      {status && <div className="banner success">{status}</div>}
      <div className="graph-grid">
        <div className="card column">
          <h3>Graph configuration</h3>
          <textarea className="code" spellCheck={false} value={configText} onChange={(event) => setConfigText(event.target.value)} />
        </div>
        <div className="card column">
          <h3>Compiled preview</h3>
          <p className="muted small">Mermaid source of the live graph. Paste it into mermaid.live to explore it.</p>
          <pre className="mermaid">{mermaid || "Loading…"}</pre>
        </div>
      </div>
    </section>
  );
}
