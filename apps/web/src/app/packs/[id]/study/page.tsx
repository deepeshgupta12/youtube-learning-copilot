"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  getMaterials,
  getFlashcardProgress,
  getQuizProgress,
  getChapterProgress,
  type StudyMaterialsResponse,
  type FlashcardProgressResponse,
  type QuizProgressResponse,
  type ChapterProgressResponse,
} from "../../../../lib/api";

function toInt(v: unknown): number | null {
  const s = typeof v === "string" ? v : Array.isArray(v) ? v[0] : "";
  const n = Number.parseInt(String(s), 10);
  return Number.isFinite(n) ? n : null;
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
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

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="text-xs text-white/50">{label}</div>
      <div className="mt-1 text-lg text-white">{value}</div>
      {sub ? <div className="mt-1 text-xs text-white/55">{sub}</div> : null}
    </div>
  );
}

export default function StudyHubPage() {
  const params = useParams();
  const studyPackId = useMemo(() => toInt((params as any)?.id), [params]);

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const [materialsTotal, setMaterialsTotal] = useState<number | null>(null);

  const [flash, setFlash] = useState<FlashcardProgressResponse | null>(null);
  const [quiz, setQuiz] = useState<QuizProgressResponse | null>(null);
  const [chap, setChap] = useState<ChapterProgressResponse | null>(null);

  async function refresh() {
    if (!studyPackId) return;
    setErr(null);
    setLoading(true);
    try {
      const m: StudyMaterialsResponse = await getMaterials(studyPackId);
      setMaterialsTotal((m.materials || []).length);

      const [f, q, c] = await Promise.all([
        getFlashcardProgress(studyPackId),
        getQuizProgress(studyPackId),
        getChapterProgress(studyPackId),
      ]);

      setFlash(f);
      setQuiz(q);
      setChap(c);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyPackId]);

  const flashTotal = flash?.total_cards ?? 0;
  const flashKnown = flash?.known_cards ?? 0;
  const flashReviewLater = flash?.review_later_cards ?? 0;

  const quizTotal = quiz?.total_questions ?? 0;
  const quizSeen = quiz?.seen_questions ?? 0;
  const quizCorrect = quiz?.correct_questions ?? 0;
  const quizWrong = quiz?.wrong_questions ?? 0;
  const quizAccuracy = quizSeen > 0 ? `${Math.round((quizCorrect / quizSeen) * 100)}%` : "-";

  const chaptersTotal = chap?.total_chapters ?? 0;
  const chaptersCompleted = chap?.completed_chapters ?? 0;
  const resumeChapterIndex = chap?.resume_chapter_index ?? 0;

  // Resume heuristics for flashcards/quiz (since backend doesn't return resume idx)
  const resumeFlashIdx = useMemo(() => {
    const items = flash?.items || [];
    if (!items.length) return 0;
    const i = items.findIndex((it) => it.status !== "known");
    return i >= 0 ? i : 0;
  }, [flash]);

  const resumeQuizIdx = useMemo(() => {
    const items = quiz?.items || [];
    if (!items.length) return 0;
    const i = items.findIndex((it) => it.status === null);
    return i >= 0 ? i : 0;
  }, [quiz]);

  if (!studyPackId) {
    return <div className="p-6 text-white/80">Invalid pack id.</div>;
  }

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-10">
      <div className="flex items-center justify-between gap-4">
        <Link href={`/packs/${studyPackId}`} className="text-sm text-white/70 hover:text-white">
          ← Back to pack
        </Link>

        <button
          onClick={refresh}
          disabled={loading}
          className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
        >
          Refresh
        </button>
      </div>

      <div className="mt-6">
        <h1 className="text-3xl font-semibold text-white">Study</h1>
        <p className="mt-2 text-sm text-white/60">One place to resume chapters, flashcards, and quizzes.</p>
      </div>

      {err && (
        <div className="mt-4 rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-100 whitespace-pre-wrap">
          {err}
        </div>
      )}

      <div className="mt-6 grid gap-4">
        <GlassCard title="Overview" right={materialsTotal !== null ? `Materials: ${materialsTotal}` : undefined}>
          {loading ? (
            <div className="text-sm text-white/60">Loading…</div>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <Stat
                label="Chapters"
                value={`${chaptersCompleted}/${chaptersTotal}`}
                sub={
                  chaptersTotal
                    ? `Resume at: Chapter ${clamp(resumeChapterIndex + 1, 1, chaptersTotal)}`
                    : "No chapters"
                }
              />

              <Stat
                label="Flashcards"
                value={`${flashKnown}/${flashTotal}`}
                sub={
                  flashTotal
                    ? `Review later: ${flashReviewLater} • Resume at card ${clamp(resumeFlashIdx + 1, 1, flashTotal)}`
                    : "No flashcards"
                }
              />

              <Stat
                label="Quiz"
                value={`${quizCorrect}/${quizSeen || 0}`}
                sub={
                  quizTotal
                    ? `Wrong: ${quizWrong} • Accuracy: ${quizAccuracy} • Resume at Q${clamp(resumeQuizIdx + 1, 1, quizTotal)}`
                    : "No quiz"
                }
              />
            </div>
          )}
        </GlassCard>

        <div className="grid gap-4 md:grid-cols-3">
          <GlassCard title="Chapters" right={chap ? `${chaptersCompleted}/${chaptersTotal}` : ""}>
            <div className="grid gap-3">
              <div className="text-sm text-white/70">
                Read chapter summaries and mark chapters completed. Resume uses the first not-completed chapter.
              </div>
              <Link
                href={`/packs/${studyPackId}/study/chapters`}
                className="inline-flex items-center justify-center rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs text-white hover:bg-white/15"
              >
                Resume chapters
              </Link>
            </div>
          </GlassCard>

          <GlassCard title="Flashcards" right={flash ? `${flashKnown}/${flashTotal}` : ""}>
            <div className="grid gap-3">
              <div className="text-sm text-white/70">
                Flip cards, then mark them Known or Review later. Resume picks the first non-known card.
              </div>
              <Link
                href={`/packs/${studyPackId}/study/flashcards`}
                className="inline-flex items-center justify-center rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs text-white hover:bg-white/15"
              >
                Continue flashcards
              </Link>
            </div>
          </GlassCard>

          <GlassCard title="Quiz" right={quiz ? `${quizCorrect}/${quizSeen || 0}` : ""}>
            <div className="grid gap-3">
              <div className="text-sm text-white/70">
                Attempt questions and track correct/wrong. Resume picks the first unanswered question.
              </div>
              <Link
                href={`/packs/${studyPackId}/study/quiz`}
                className="inline-flex items-center justify-center rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs text-white hover:bg-white/15"
              >
                Continue quiz
              </Link>
            </div>
          </GlassCard>
        </div>
      </div>
    </main>
  );
}