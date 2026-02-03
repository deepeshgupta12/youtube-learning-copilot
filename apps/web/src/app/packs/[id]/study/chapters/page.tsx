"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  getMaterials,
  getChapterProgress,
  markChapterProgress,
  type ChapterProgressResponse,
  type StudyMaterialRow,
  type StudyMaterialsResponse,
} from "../../../../../lib/api";

function toInt(v: unknown): number | null {
  const s = typeof v === "string" ? v : Array.isArray(v) ? v[0] : "";
  const n = Number.parseInt(String(s), 10);
  return Number.isFinite(n) ? n : null;
}

type Chapter = { title: string; summary: string; sentences: string[] };

function extractChapters(materials: StudyMaterialRow[] | null): Chapter[] {
  const row = (materials || []).find((m) => m.kind === "chapters");
  const items = (row?.content_json as any)?.items;
  if (!Array.isArray(items)) return [];
  return items
    .filter((x: any) => x && typeof x === "object")
    .map((x: any) => ({
      title: String(x.title || ""),
      summary: String(x.summary || ""),
      sentences: Array.isArray(x.sentences) ? x.sentences.map((s: any) => String(s)) : [],
    }))
    .filter((x) => x.title.trim() || x.summary.trim() || x.sentences.length > 0);
}

export default function ChaptersStudyPage() {
  const params = useParams();
  const studyPackId = useMemo(() => toInt((params as any)?.id), [params]);

  const [materials, setMaterials] = useState<StudyMaterialRow[] | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [progress, setProgress] = useState<ChapterProgressResponse | null>(null);

  const [activeIdx, setActiveIdx] = useState(0);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    if (!studyPackId) return;
    setErr(null);
    setLoading(true);
    try {
      const m: StudyMaterialsResponse = await getMaterials(studyPackId);
      const list = m.materials || [];
      setMaterials(list);

      const extracted = extractChapters(list);
      setChapters(extracted);

      const p = await getChapterProgress(studyPackId);
      setProgress(p);

      const resume = typeof p.resume_chapter_index === "number" ? p.resume_chapter_index : 0;
      setActiveIdx((prev) => {
        if (!extracted.length) return 0;
        // If current selection still valid, keep it; else fallback to resume
        if (prev >= 0 && prev < extracted.length) return prev;
        return Math.min(resume, extracted.length - 1);
      });
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function openChapter(i: number) {
    if (!studyPackId) return;
    setErr(null);
    setBusy(true);
    try {
      const p = await markChapterProgress(studyPackId, { chapter_index: i, action: "open" });
      setProgress(p);
      setActiveIdx(i);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function markComplete() {
    if (!studyPackId) return;
    if (!chapters.length) return;
    setErr(null);
    setBusy(true);
    try {
      const p = await markChapterProgress(studyPackId, { chapter_index: activeIdx, action: "complete" });
      setProgress(p);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function resetStatus() {
    if (!studyPackId) return;
    if (!chapters.length) return;
    setErr(null);
    setBusy(true);
    try {
      const p = await markChapterProgress(studyPackId, { chapter_index: activeIdx, action: "reset" });
      setProgress(p);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyPackId]);

  const total = chapters.length;
  const cur = total ? chapters[activeIdx] : null;
  const curStatus = progress?.items?.[activeIdx]?.status ?? null;

  const opened = progress?.opened_chapters ?? 0;
  const completed = progress?.completed_chapters ?? 0;
  const resume = progress?.resume_chapter_index ?? 0;

  if (!studyPackId) {
    return <div className="p-6 text-white/80">Invalid pack id.</div>;
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-10">
      <div className="flex items-center justify-between gap-4">
        <Link href={`/packs/${studyPackId}`} className="text-sm text-white/70 hover:text-white">
          ← Back to pack
        </Link>

        <button
          onClick={refresh}
          disabled={loading || busy}
          className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
        >
          Refresh
        </button>
      </div>

      <div className="mt-6">
        <h1 className="text-3xl font-semibold text-white">Chapters</h1>
        <p className="mt-2 text-sm text-white/60">
          Resume where you left off and mark chapters completed.
        </p>
      </div>

      {err && (
        <div className="mt-4 rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-100 whitespace-pre-wrap">
          {err}
        </div>
      )}

      <div className="mt-6 grid gap-4">
        {/* Progress card */}
        <section className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_8px_40px_rgba(0,0,0,0.35)]">
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-white/10">
            <div className="text-sm font-semibold text-white/90">Progress</div>
            <div className="text-xs text-white/60">
              {total ? `Chapter ${activeIdx + 1}/${total}` : "No chapters"}
            </div>
          </div>
          <div className="p-5 grid gap-2 text-sm text-white/85">
            <div>
              Opened: <span className="font-semibold text-white">{opened}</span> / {total}
            </div>
            <div>
              Completed: <span className="font-semibold text-white">{completed}</span>
              <span className="text-white/60">{" "}•</span>{" "}
              Resume index: <span className="font-semibold text-white">{total ? resume + 1 : 0}</span>
            </div>
            <div className="text-white/60">
              Current status: <span className="text-white">{curStatus || "-"}</span>
            </div>
          </div>
        </section>

        {/* Main layout */}
        <div className="grid gap-4 md:grid-cols-[320px_1fr]">
          {/* Chapter list */}
          <section className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_8px_40px_rgba(0,0,0,0.35)]">
            <div className="px-5 py-4 border-b border-white/10">
              <div className="text-sm font-semibold text-white/90">All chapters</div>
              <div className="mt-1 text-xs text-white/60">
                Click a chapter to open (records progress).
              </div>
            </div>

            <div className="p-3">
              {loading ? (
                <div className="p-3 text-sm text-white/60">Loading…</div>
              ) : total === 0 ? (
                <div className="p-3 text-sm text-white/70">No chapters found. Generate materials first.</div>
              ) : (
                <div className="grid gap-2">
                  {chapters.map((ch, i) => {
                    const st = progress?.items?.[i]?.status ?? null;
                    const active = i === activeIdx;
                    return (
                      <button
                        key={i}
                        onClick={() => openChapter(i)}
                        disabled={busy}
                        className={[
                          "w-full rounded-xl border px-3 py-2 text-left text-sm transition",
                          active
                            ? "border-white/25 bg-white/12 text-white"
                            : "border-white/10 bg-white/5 text-white/80 hover:bg-white/8 hover:text-white",
                        ].join(" ")}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="font-semibold leading-6">
                            {i + 1}. {ch.title || `Chapter ${i + 1}`}
                          </div>
                          <div className="text-[10px] text-white/60">
                            {st === "completed" ? "✓ completed" : st === "in_progress" ? "in progress" : ""}
                          </div>
                        </div>
                        {ch.summary ? (
                          <div className="mt-1 text-xs text-white/60 line-clamp-2">{ch.summary}</div>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </section>

          {/* Chapter viewer */}
          <section className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_8px_40px_rgba(0,0,0,0.35)]">
            <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-white/10">
              <div className="text-sm font-semibold text-white/90">Reader</div>
              <div className="flex gap-2">
                <button
                  onClick={markComplete}
                  disabled={loading || busy || total === 0}
                  className="rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs text-white hover:bg-white/15 disabled:opacity-50"
                >
                  Mark Completed
                </button>
                <button
                  onClick={resetStatus}
                  disabled={loading || busy || total === 0}
                  className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
                >
                  Reset Status
                </button>
              </div>
            </div>

            <div className="p-5">
              {loading ? (
                <div className="text-sm text-white/60">Loading…</div>
              ) : total === 0 ? (
                <div className="text-sm text-white/70">No chapters available.</div>
              ) : (
                <div className="grid gap-4">
                  <div>
                    <div className="text-xs text-white/60">Title</div>
                    <div className="mt-1 text-xl font-semibold text-white">{cur?.title || `Chapter ${activeIdx + 1}`}</div>
                  </div>

                  {cur?.summary ? (
                    <div>
                      <div className="text-xs text-white/60">Summary</div>
                      <div className="mt-1 text-white/85 leading-7">{cur.summary}</div>
                    </div>
                  ) : null}

                  {Array.isArray(cur?.sentences) && cur!.sentences.length > 0 ? (
                    <div>
                      <div className="text-xs text-white/60">Key sentences</div>
                      <ul className="mt-2 list-disc pl-5 space-y-2">
                        {cur!.sentences.map((s, j) => (
                          <li key={j} className="text-white/80 leading-7">{s}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}