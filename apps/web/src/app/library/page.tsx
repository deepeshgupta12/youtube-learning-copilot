"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  createStudyPackFromYoutube,
  listStudyPacks,
  pollJobUntilDone,
  type JobGetResponse,
  type StudyPackListItem,
} from "../../lib/api";

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-[11px] text-white/80">
      {children}
    </span>
  );
}

function fmtDt(s: string | null): string {
  if (!s) return "-";
  try {
    const d = new Date(s);
    return d.toLocaleString();
  } catch {
    return s;
  }
}

export default function LibraryPage() {
  const [url, setUrl] = useState("");
  const [language, setLanguage] = useState("en");

  const [creating, setCreating] = useState(false);
  const [createErr, setCreateErr] = useState<string | null>(null);

  const [job, setJob] = useState<JobGetResponse | null>(null);

  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string>("");
  const [sourceType, setSourceType] = useState<string>("");

  const [items, setItems] = useState<StudyPackListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [limit] = useState(20);
  const [offset, setOffset] = useState(0);

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  async function load(nextOffset: number) {
    setErr(null);
    setLoading(true);
    try {
      const resp = await listStudyPacks({
        q: q.trim() || undefined,
        status: status || undefined,
        source_type: sourceType || undefined,
        limit,
        offset: nextOffset,
      });
      setItems(resp.packs || []);
      setTotal(resp.total || 0);
      setOffset(resp.offset || 0);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onCreate() {
    const u = url.trim();
    if (!u) return;

    setCreateErr(null);
    setCreating(true);
    setJob(null);

    try {
      const resp = await createStudyPackFromYoutube(u, language || null);

      // start polling the ingestion job; show status here
      const j = await pollJobUntilDone(resp.job_id, { intervalMs: 1200, timeoutMs: 180000 });
      setJob(j);

      // Refresh library list after completion
      await load(0);

      // If it was a single video, jump to pack page (better UX)
      // For playlist, backend returns first pack id; we still route to it.
      window.location.href = `/packs/${resp.study_pack_id}`;
    } catch (e: any) {
      setCreateErr(e?.message || String(e));
    } finally {
      setCreating(false);
    }
  }

  const jobSummary = useMemo(() => {
    if (!job?.payload_json) return null;
    try {
      const d = JSON.parse(job.payload_json);
      return d?.summary || null;
    } catch {
      return null;
    }
  }, [job]);

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-10">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-3xl font-semibold text-white">Library</h1>
        <Link href="/" className="text-sm text-white/70 hover:text-white">
          Home
        </Link>
      </div>

      <p className="mt-2 text-sm text-white/60">
        All your ingested packs (videos and playlist items). Create new ones from YouTube.
      </p>

      {/* Create */}
      <section className="mt-6 rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_8px_40px_rgba(0,0,0,0.35)]">
        <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-white/10">
          <div className="text-sm font-semibold text-white/90">Create from YouTube</div>
          <div className="text-xs text-white/60">Video or playlist URL</div>
        </div>

        <div className="p-5">
          {createErr && (
            <div className="mb-3 rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-100 whitespace-pre-wrap">
              {createErr}
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 md:grid-cols-6">
            <div className="md:col-span-5">
              <div className="text-xs text-white/50">YouTube URL</div>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=... or https://www.youtube.com/playlist?list=..."
                className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/90 outline-none focus:border-white/20"
              />
            </div>
            <div className="md:col-span-1">
              <div className="text-xs text-white/50">Language</div>
              <input
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                placeholder="en"
                className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/90 outline-none focus:border-white/20"
              />
            </div>
          </div>

          <div className="mt-4 flex items-center gap-2">
            <button
              onClick={onCreate}
              disabled={creating || !url.trim()}
              className="rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs text-white hover:bg-white/15 disabled:opacity-50"
            >
              {creating ? "Creating…" : "Create & ingest"}
            </button>

            {job && (
              <div className="text-xs text-white/70">
                Job #{job.job_id}: <span className="text-white/90">{job.status}</span>
                {job.error ? <span className="text-red-200"> · {job.error}</span> : null}
              </div>
            )}
          </div>

          {jobSummary && (
            <div className="mt-3 text-xs text-white/65 whitespace-pre-wrap">
              Playlist summary: {JSON.stringify(jobSummary, null, 2)}
            </div>
          )}
        </div>
      </section>

      {/* Filters */}
      <section className="mt-6 rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_8px_40px_rgba(0,0,0,0.35)]">
        <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-white/10">
          <div className="text-sm font-semibold text-white/90">Study packs</div>
          <div className="text-xs text-white/60">Total: {total}</div>
        </div>

        <div className="p-5">
          {err && (
            <div className="mb-3 rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-100 whitespace-pre-wrap">
              {err}
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 md:grid-cols-6">
            <div className="md:col-span-3">
              <div className="text-xs text-white/50">Search</div>
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Title / URL / video id / playlist…"
                className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/90 outline-none focus:border-white/20"
              />
            </div>

            <div className="md:col-span-1">
              <div className="text-xs text-white/50">Status</div>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/90 outline-none focus:border-white/20"
              >
                <option value="">All</option>
                <option value="created">created</option>
                <option value="running">running</option>
                <option value="ingested">ingested</option>
                <option value="failed">failed</option>
              </select>
            </div>

            <div className="md:col-span-1">
              <div className="text-xs text-white/50">Source</div>
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/90 outline-none focus:border-white/20"
              >
                <option value="">All</option>
                <option value="youtube_video">youtube_video</option>
              </select>
            </div>

            <div className="md:col-span-1 flex items-end gap-2">
              <button
                onClick={() => load(0)}
                disabled={loading}
                className="w-full rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs text-white hover:bg-white/15 disabled:opacity-50"
              >
                {loading ? "Loading…" : "Apply"}
              </button>
            </div>
          </div>

          <div className="mt-5">
            {loading ? (
              <div className="text-sm text-white/60">Loading…</div>
            ) : items.length === 0 ? (
              <div className="text-sm text-white/60">No packs found.</div>
            ) : (
              <div className="grid gap-3">
                {items.map((sp) => (
                  <div
                    key={sp.id}
                    className="rounded-xl border border-white/10 bg-white/5 p-4"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Link
                            href={`/packs/${sp.id}`}
                            className="text-sm font-semibold text-white/90 hover:underline"
                          >
                            #{sp.id} {sp.title || "(untitled)"}
                          </Link>
                          <Badge>{sp.status}</Badge>
                          {sp.playlist_id ? <Badge>playlist</Badge> : <Badge>video</Badge>}
                        </div>

                        <div className="mt-1 text-xs text-white/60 break-all">
                          {sp.source_url}
                        </div>

                        <div className="mt-2 flex flex-wrap gap-2 text-xs text-white/55">
                          <span>created: {fmtDt(sp.created_at)}</span>
                          <span>updated: {fmtDt(sp.updated_at)}</span>
                          {sp.playlist_title ? <span>playlist: {sp.playlist_title}</span> : null}
                          {sp.playlist_index !== null && sp.playlist_index !== undefined ? (
                            <span>index: {sp.playlist_index}</span>
                          ) : null}
                        </div>

                        {sp.error ? (
                          <div className="mt-2 text-xs text-red-200 whitespace-pre-wrap">
                            {sp.error}
                          </div>
                        ) : null}
                      </div>

                      <div className="shrink-0 flex items-center gap-2">
                        <Link
                          href={`/packs/${sp.id}/study/transcript`}
                          className="rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-xs text-white/85 hover:bg-white/8"
                        >
                          Transcript
                        </Link>
                        <Link
                          href={`/packs/${sp.id}`}
                          className="rounded-xl border border-white/15 bg-white/10 px-3 py-2 text-xs text-white hover:bg-white/15"
                        >
                          Open
                        </Link>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mt-5 flex items-center justify-between gap-2">
            <button
              onClick={() => load(Math.max(0, offset - limit))}
              disabled={loading || !canPrev}
              className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
            >
              Prev
            </button>

            <div className="text-xs text-white/50">
              Offset: {offset} · Showing {items.length} / {total}
            </div>

            <button
              onClick={() => load(offset + limit)}
              disabled={loading || !canNext}
              className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}