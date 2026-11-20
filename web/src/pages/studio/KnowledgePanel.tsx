import { useEffect, useRef, useState } from "react";
import { Eye, RefreshCw, Search, Trash2, Upload, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { deleteJson, errorText, getJson, uploadFile } from "@/api";
import { useLanguage } from "@/i18n";

interface KnowledgeDocument {
  name: string;
  bytes: number;
  modified: number;
  chunks: number;
}
interface KnowledgeDocumentContent extends KnowledgeDocument {
  content: string;
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

export default function KnowledgePanel({
  token,
  onError,
}: {
  token: string;
  onError: (message: string) => void;
}) {
  const { t } = useLanguage();
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [query, setQuery] = useState("How do I activate Widget Pro?");
  const [result, setResult] = useState<KnowledgeSearch | null>(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [previewName, setPreviewName] = useState("");
  const [preview, setPreview] = useState<KnowledgeDocumentContent | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadStatus = async () => {
    setStatus(await getJson<KnowledgeStatus>("/admin/knowledge/status", token));
  };

  useEffect(() => {
    void loadStatus().catch((caught) => onError(errorText(caught)));
  }, [token]);

  useEffect(() => {
    if (!previewName) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPreviewName("");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [previewName]);

  const runSearch = async () => {
    if (!query.trim()) return;
    onError("");
    setBusy("search");
    try {
      setResult(
        await getJson<KnowledgeSearch>(
          `/admin/knowledge/search?query=${encodeURIComponent(query)}&top_k=4`,
          token,
        ),
      );
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

  const openDocument = async (name: string) => {
    onError("");
    setPreviewName(name);
    setPreview(null);
    setPreviewError("");
    setPreviewLoading(true);
    try {
      setPreview(
        await getJson<KnowledgeDocumentContent>(
          `/admin/knowledge/documents/${encodeURIComponent(name)}`,
          token,
        ),
      );
    } catch (caught) {
      setPreviewError(t("knowledge.documentLoadFailed"));
      onError(errorText(caught));
    } finally {
      setPreviewLoading(false);
    }
  };

  const closePreview = () => {
    setPreviewName("");
    setPreview(null);
    setPreviewError("");
  };

  const stats = [
    { value: status?.document_count ?? 0, label: t("knowledge.statsDocuments") },
    { value: status?.chunk_count ?? 0, label: t("knowledge.statsPassages") },
    {
      value: status?.dimension ?? 0,
      label: t("knowledge.statsDims", { embedder: status?.embedder ?? "" }),
    },
    { value: status?.top_k ?? 0, label: t("knowledge.statsTopK") },
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-auto hidden text-xs text-muted-foreground sm:inline">
          {t("knowledge.toolbar")}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={busy === "reindex" || busy === "upload"}
          onClick={() => void reindex()}
        >
          <RefreshCw />
          {t("knowledge.reindex")}
        </Button>
        <Button
          size="sm"
          disabled={busy === "upload" || busy === "reindex"}
          onClick={() => fileRef.current?.click()}
        >
          <Upload />
          {busy === "upload" ? t("knowledge.uploading") : t("knowledge.upload")}
        </Button>
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
      {notice && (
        <div className="rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
          {notice}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((item) => (
          <Card key={item.label} className="px-4 py-3">
            <strong className="block text-2xl font-semibold tracking-tight tabular-nums">
              {item.value}
            </strong>
            <span className="text-xs text-muted-foreground">{item.label}</span>
          </Card>
        ))}
      </div>

      <div className="grid items-start gap-3 lg:grid-cols-[1.15fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>{t("knowledge.previewTitle")}</CardTitle>
            <CardDescription>{t("knowledge.previewHelp")}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                value={query}
                placeholder={t("knowledge.searchPlaceholder")}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void runSearch();
                }}
              />
              <Button
                variant="outline"
                disabled={busy === "search"}
                onClick={() => void runSearch()}
              >
                <Search />
                {t("common.search")}
              </Button>
            </div>
            {result && (
              <p className="text-xs text-muted-foreground">
                {t("knowledge.results", { count: result.hits.length, ms: result.elapsed_ms })}
              </p>
            )}
            <div className="scrollbar-thin flex max-h-[52vh] flex-col gap-2 overflow-y-auto">
              {result?.hits.map((hit) => (
                <div key={hit.chunk_id} className="rounded-lg border border-border bg-muted/40 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <Badge variant="accent">
                      [{hit.index}] {hit.citation}
                    </Badge>
                    <span className="text-xs font-medium text-success tabular-nums">
                      {hit.score.toFixed(3)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-foreground/90">{hit.preview}…</p>
                  <span className="text-xs text-muted-foreground">
                    {hit.source} · {t("knowledge.vector")} {hit.vector_score.toFixed(2)} ·{" "}
                    {t("knowledge.lexical")} {hit.lexical_score.toFixed(2)}
                  </span>
                </div>
              ))}
              {result && result.hits.length === 0 && (
                <p className="text-sm text-muted-foreground">{t("knowledge.noResults")}</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("knowledge.documentsTitle")}</CardTitle>
            <CardDescription>{status?.directory}</CardDescription>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted-foreground uppercase">
                  <th className="py-2 font-medium">{t("knowledge.colDocument")}</th>
                  <th className="hidden py-2 font-medium sm:table-cell">
                    {t("knowledge.colSize")}
                  </th>
                  <th className="py-2 font-medium">{t("knowledge.colPassages")}</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {status?.documents.map((document) => (
                  <tr key={document.name}>
                    <td className="max-w-[180px] py-2.5">
                      <button
                        type="button"
                        className="block max-w-full truncate text-left font-medium hover:text-primary hover:underline"
                        title={t("knowledge.viewDocument")}
                        onClick={() => void openDocument(document.name)}
                      >
                        {document.name}
                      </button>
                    </td>
                    <td className="hidden py-2.5 text-xs text-muted-foreground sm:table-cell">
                      {formatBytes(document.bytes)}
                    </td>
                    <td className="py-2.5 text-xs text-muted-foreground tabular-nums">
                      {document.chunks}
                    </td>
                    <td className="py-2.5 text-right">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="text-muted-foreground hover:text-foreground"
                        onClick={() => void openDocument(document.name)}
                        aria-label={t("knowledge.viewDocument")}
                        title={t("knowledge.viewDocument")}
                      >
                        <Eye />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="text-muted-foreground hover:text-destructive"
                        disabled={busy === document.name}
                        onClick={() => void remove(document.name)}
                        aria-label={t("common.delete")}
                      >
                        <Trash2 />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {status && status.documents.length === 0 && (
              <p className="py-2 text-sm text-muted-foreground">{t("knowledge.empty")}</p>
            )}
          </CardContent>
        </Card>
      </div>

      {previewName && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="presentation"
          onClick={closePreview}
        >
          <Card
            role="dialog"
            aria-modal="true"
            aria-labelledby="knowledge-preview-title"
            className="flex max-h-[85vh] w-full max-w-3xl overflow-hidden"
            onClick={(event) => event.stopPropagation()}
          >
            <CardHeader className="flex-row items-start justify-between gap-3 border-b border-border pb-4">
              <div className="min-w-0">
                <CardTitle id="knowledge-preview-title" className="truncate text-base">
                  {previewName}
                </CardTitle>
                <CardDescription>
                  {preview
                    ? `${formatBytes(preview.bytes)} · ${preview.chunks} ${t("knowledge.colPassages")}`
                    : t("knowledge.documentHelp")}
                </CardDescription>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={closePreview}
                aria-label={t("common.close")}
              >
                <X />
              </Button>
            </CardHeader>
            <CardContent className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {previewLoading && (
                <p className="text-sm text-muted-foreground">{t("knowledge.loadingDocument")}</p>
              )}
              {previewError && <p className="text-sm text-destructive">{previewError}</p>}
              {preview && (
                <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-foreground/90">
                  {preview.content}
                </pre>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
