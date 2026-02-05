"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  getStudyPack,
  getTranscript,
  kbAsk,
  listTranscriptChunks,
  type KBAskResponse,
  type StudyPackResponse,
  type TranscriptChunkItem,
  type TranscriptGetResponse,
} from "../../../../../lib/api";

function toInt(v: unknown): number | null {
  const s = typeof v === "string" ? v : Array.isArray(v) ? v[0] : "";
  const n = Number.parseInt(String(s), 10);
  return Number.isFinite(n) ? n : null;
}

function fmtTime(sec: number): string {
  const s = Math.max(0, Math.floor(sec || 0));
  const hh = Math.floor(s / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  if (hh > 0) return `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
  return `${mm}:${String(ss).padStart(2, "0")}`;
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // ignore
  }
}

function GlassCard({
  title,
  right,
  children,
}: {
  title?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_8px_40px_rgba(0,0,0,0.35)]">
      {(title || right) && (
        <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-white/10">
          <div className="text-sm font-semibold text-white/90">{title}</div>
          <div className="text-xs text-white/60">{right}</div>
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export default function TranscriptStudyPage() {
  const params = useParams();
  const studyPackId = useMemo(() => toInt((params as any)?.id), [params]);

  const [pack, setPack] = useState<StudyPackResponse["study_pack"] | null>(null);
  const [t, setT] = useState<TranscriptGetResponse | null>(null);

  // Transcript search
  const [q, setQ] = useState("");
  const [items, setItems] = useState<TranscriptChunkItem[]>([]);
  const [total, setTotal] = useState(0);

  const [loading, setLoading] = useState(true);
  const [loadingChunks, setLoadingChunks] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const limit = 60;
  const [offset, setOffset] = useState(0);

  // KB Ask (V2.4)
  const [askQ, setAskQ] = useState("");
  const [askLoading, setAskLoading] = useState(false);
  const [askErr, setAskErr] = useState<string | null>(null);
  const [askResp, setAskResp] = useState<KBAskResponse | null>(null);

  const [askLimit, setAskLimit] = useState(6);
  const [askHybrid, setAskHybrid] = useState(true);
  const [embedModel, setEmbedModel] = useState("sentence-transformers/all-MiniLM-L6-v2");

  const durationSec = useMemo(() => {
    if (!items?.length) return 0;
    const last = items[items.length - 1];
    return Math.floor(last?.end_sec || 0);
  }, [items]);

  async function loadAll() {
    if (!studyPackId) return;
    setErr(null);
    setLoading(true);
    try {
      const p = await getStudyPack(studyPackId);
      setPack(p.study_pack);

      const tr = await getTranscript(studyPackId);
      setT(tr);

      setOffset(0);
      await loadChunks(0, q);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadChunks(nextOffset: number, query: string) {
    if (!studyPackId) return;
    setLoadingChunks(true);
    try {
      const resp = await listTranscriptChunks({
        studyPackId,
        q: query?.trim() || undefined,
        limit,
        offset: nextOffset,
      });
      setItems(resp.items || []);
      setTotal(resp.total || 0);
      setOffset(resp.offset || 0);
    } finally {
      setLoadingChunks(false);
    }
  }

  async function onAsk() {
    if (!studyPackId) return;
    const question = askQ.trim();
    if (!question) {
      setAskErr("Please enter a question.");
      return;
    }

    setAskErr(null);
    setAskLoading(true);
    try {
      const resp = await kbAsk(studyPackId, {
        question,
        limit: askLimit,
        hybrid: askHybrid,
        embed_model: embedModel || null,
      });
      setAskResp(resp);
    } catch (e: any) {
      setAskErr(e?.message || String(e));
    } finally {
      setAskLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyPackId]);

  if (!studyPackId) {
    return <div className="p-6 text-white/80">Invalid pack id.</div>;
  }

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-10">
      <div className="flex items-center justify-between gap-4">
        <Link href={`/packs/${studyPackId}`} className="text-sm text-white/70 hover:text-white">
          ← Back to pack
        </Link>

        <div className="flex gap-2">
          <Link
            href={`/packs/${studyPackId}/study/flashcards`}
            className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8"
          >
            Flashcards
          </Link>
          <Link
            href={`/packs/${studyPackId}/study/chapters`}
            className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8"
          >
            Chapters
          </Link>

          <button
            onClick={() => loadAll()}
            disabled={loading || loadingChunks}
            className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="mt-6">
        <h1 className="text-3xl font-semibold text-white">Transcript</h1>
        <p className="mt-2 text-sm text-white/60">Searchable, timestamped transcript chunks + grounded Q&A.</p>
      </div>

      {err && (
        <div className="mt-4 rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-100 whitespace-pre-wrap">
          {err}
        </div>
      )}

      <div className="mt-6 grid gap-4">
        {/* V2.4 — Ask from transcript */}
        <GlassCard
          title="Ask from transcript"
          right={
            pack?.source_url ? (
              <a
                href={pack.source_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-white/70 underline underline-offset-4 hover:text-white"
              >
                Open source
              </a>
            ) : null
          }
        >
          <div className="grid gap-3">
            <div className="text-sm text-white/70">
              Ask a question. The answer will only use retrieved transcript excerpts and include timestamped citations.
            </div>

            <textarea
              value={askQ}
              onChange={(e) => setAskQ(e.target.value)}
              placeholder="Example: What is the difference between brain structure and function?"
              className="min-h-[92px] w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 outline-none focus:border-white/20"
            />

            <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
              <div className="flex flex-wrap gap-3">
                <div>
                  <div className="text-xs text-white/50">Limit</div>
                  <input
                    value={String(askLimit)}
                    onChange={(e) => setAskLimit(Math.max(1, Math.min(12, Number(e.target.value || 6))))}
                    className="mt-2 w-[110px] rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/90 outline-none focus:border-white/20"
                    inputMode="numeric"
                  />
                  <div className="mt-1 text-[11px] text-white/45">1–12</div>
                </div>

                <div>
                  <div className="text-xs text-white/50">Hybrid retrieval</div>
                  <button
                    onClick={() => setAskHybrid((v) => !v)}
                    className="mt-2 rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8"
                  >
                    {askHybrid ? "On" : "Off"}
                  </button>
                </div>

                <div className="min-w-[280px]">
                  <div className="text-xs text-white/50">Embed model</div>
                  <input
                    value={embedModel}
                    onChange={(e) => setEmbedModel(e.target.value)}
                    className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/90 outline-none focus:border-white/20"
                  />
                  <div className="mt-1 text-[11px] text-white/45">Sent as embed_model</div>
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={onAsk}
                  disabled={askLoading}
                  className="rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs text-white hover:bg-white/15 disabled:opacity-50"
                >
                  {askLoading ? "Asking…" : "Ask"}
                </button>

                <button
                  onClick={() => {
                    setAskQ("");
                    setAskResp(null);
                    setAskErr(null);
                  }}
                  disabled={askLoading}
                  className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
                >
                  Clear
                </button>
              </div>
            </div>

            {askErr && (
              <div className="rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-100 whitespace-pre-wrap">
                {askErr}
              </div>
            )}

            {askResp && (
              <div className="grid gap-3">
                {askResp.refused ? (
                  <div className="rounded-xl border border-yellow-400/25 bg-yellow-400/10 px-4 py-3 text-sm text-yellow-50 whitespace-pre-wrap">
                    {askResp.answer}
                  </div>
                ) : (
                  <div className="rounded-xl border border-white/10 bg-white/5 p-4">
                    <div className="text-xs text-white/50">Answer</div>
                    <div className="mt-2 whitespace-pre-wrap leading-7 text-white/90">{askResp.answer}</div>
                  </div>
                )}

                <div className="rounded-xl border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-xs text-white/50">Citations</div>
                    <div className="text-[11px] text-white/45">
                      model: {askResp.model}
                      {askResp.embed_model ? ` · embed: ${askResp.embed_model}` : ""}
                    </div>
                  </div>

                  {askResp.citations?.length ? (
                    <div className="mt-3 grid gap-2">
                      {askResp.citations.map((c, i) => (
                        <div key={`${c.chunk_id}-${i}`} className="rounded-xl border border-white/10 bg-white/5 p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="text-xs text-white/60">
                              [{i + 1}] chunk #{c.idx} · {fmtTime(c.start_sec)} → {fmtTime(c.end_sec)} · score{" "}
                              {c.score?.toFixed ? c.score.toFixed(3) : c.score}
                            </div>

                            <div className="flex gap-2">
                              {c.url ? (
                                <a
                                  href={c.url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/80 hover:bg-white/10"
                                >
                                  Watch
                                </a>
                              ) : null}

                              <button
                                onClick={() => copyToClipboard(c.text)}
                                className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/75 hover:bg-white/10"
                              >
                                Copy
                              </button>
                            </div>
                          </div>

                          <div className="mt-2 whitespace-pre-wrap leading-7 text-white/85">{c.text}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-2 text-sm text-white/60">No citations returned.</div>
                  )}

                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs text-white/60 hover:text-white/80">
                      View retrieval debug
                    </summary>
                    <pre className="mt-2 whitespace-pre-wrap text-[11px] text-white/65">
                      {JSON.stringify(askResp.retrieval, null, 2)}
                    </pre>
                  </details>
                </div>
              </div>
            )}
          </div>
        </GlassCard>

        <GlassCard title="Pack info" right={pack ? <span>#{pack.id}</span> : null}>
          {loading && <div className="text-sm text-white/60">Loading…</div>}
          {pack && (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <div className="text-xs text-white/50">Title</div>
                <div className="mt-1 text-sm text-white/90">{pack.title || "(untitled)"}</div>
              </div>
              <div>
                <div className="text-xs text-white/50">Status</div>
                <div className="mt-1 text-sm text-white/90">{pack.status}</div>
              </div>
              <div className="md:col-span-2">
                <div className="text-xs text-white/50">URL</div>
                <div className="mt-1 text-sm text-white/85 break-all">{pack.source_url}</div>
              </div>
            </div>
          )}
        </GlassCard>

        <GlassCard
          title="Transcript chunks"
          right={
            <span>
              Total: {total} {durationSec ? `· ~${fmtTime(durationSec)}` : ""}
            </span>
          }
        >
          <div className="flex flex-col gap-3 md:flex-row md:items-end">
            <div className="flex-1">
              <div className="text-xs text-white/50">Search</div>
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search inside transcript…"
                className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/90 outline-none focus:border-white/20"
              />
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => loadChunks(0, q)}
                disabled={loadingChunks}
                className="rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs text-white hover:bg-white/15 disabled:opacity-50"
              >
                Search
              </button>
              <button
                onClick={() => {
                  setQ("");
                  loadChunks(0, "");
                }}
                disabled={loadingChunks}
                className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
              >
                Clear
              </button>
            </div>
          </div>

          <div className="mt-4">
            {loadingChunks ? (
              <div className="text-sm text-white/60">Loading chunks…</div>
            ) : items.length === 0 ? (
              <div className="text-sm text-white/60">No chunks found{q.trim() ? " for this search." : "."}</div>
            ) : (
              <div className="grid gap-3">
                {items.map((c) => (
                  <div key={c.id} className="rounded-xl border border-white/10 bg-white/5 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="text-xs text-white/60">
                        #{c.idx} · {fmtTime(c.start_sec)} → {fmtTime(c.end_sec)}
                      </div>
                      <button
                        onClick={() => copyToClipboard(c.text)}
                        className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/75 hover:bg-white/10"
                      >
                        Copy
                      </button>
                    </div>

                    <div className="mt-2 whitespace-pre-wrap leading-7 text-white/85">{c.text}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mt-5 flex items-center justify-between gap-2">
            <button
              onClick={() => loadChunks(Math.max(0, offset - limit), q)}
              disabled={loadingChunks || offset <= 0}
              className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
            >
              Prev
            </button>

            <div className="text-xs text-white/50">
              Offset: {offset} · Showing {items.length} / {total}
            </div>

            <button
              onClick={() => loadChunks(offset + limit, q)}
              disabled={loadingChunks || offset + limit >= total}
              className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </GlassCard>

        <GlassCard title="Raw transcript text (fallback)">
          <div className="text-sm text-white/70">
            {t?.transcript_text ? (
              <pre className="whitespace-pre-wrap leading-7">{t.transcript_text}</pre>
            ) : (
              "No transcript_text found. (This usually means ingestion failed or transcript wasn’t stored.)"
            )}
          </div>
        </GlassCard>
      </div>
    </main>
  );
}