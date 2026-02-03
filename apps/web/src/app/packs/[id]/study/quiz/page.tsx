"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  getMaterials,
  getQuizProgress,
  markQuizProgress,
  type QuizProgressResponse,
  type StudyMaterialRow,
  type StudyMaterialsResponse,
} from "../../../../../lib/api";

function toInt(v: unknown): number | null {
  const s = typeof v === "string" ? v : Array.isArray(v) ? v[0] : "";
  const n = Number.parseInt(String(s), 10);
  return Number.isFinite(n) ? n : null;
}

type QuizQ = {
  question: string;
  options: string[];
  answer_index: number | null;
};

function extractQuiz(materials: StudyMaterialRow[] | null): QuizQ[] {
  const row = (materials || []).find((m) => m.kind === "quiz");
  const items = (row?.content_json as any)?.items;
  if (!Array.isArray(items)) return [];

  return items
    .filter((x: any) => x && typeof x === "object")
    .map((x: any) => {
      const question = String(x.question || "");
      const options = Array.isArray(x.options) ? x.options.map((o: any) => String(o)) : [];
      const ans = typeof x.answer_index === "number" ? x.answer_index : null;
      return { question, options, answer_index: ans };
    })
    .filter((q) => q.question.trim() && q.options.length >= 2);
}

export default function QuizStudyPage() {
  const params = useParams();
  const studyPackId = useMemo(() => toInt((params as any)?.id), [params]);

  const [materials, setMaterials] = useState<StudyMaterialRow[] | null>(null);
  const [questions, setQuestions] = useState<QuizQ[]>([]);
  const [progress, setProgress] = useState<QuizProgressResponse | null>(null);

  const [idx, setIdx] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [checked, setChecked] = useState(false);

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

      const extracted = extractQuiz(list);
      setQuestions(extracted);

      const p = await getQuizProgress(studyPackId);
      setProgress(p);

      setIdx((prev) => {
        if (!extracted.length) return 0;
        return Math.min(prev, extracted.length - 1);
      });

      setSelected(null);
      setChecked(false);
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

  const total = questions.length;
  const cur = total ? questions[idx] : null;
  const curStatus = progress?.items?.[idx]?.status ?? null;

  const seen = progress?.seen_questions ?? 0;
  const correct = progress?.correct_questions ?? 0;
  const wrong = progress?.wrong_questions ?? 0;

  function prev() {
    if (!total) return;
    setIdx((x) => Math.max(0, x - 1));
    setSelected(null);
    setChecked(false);
  }

  function next() {
    if (!total) return;
    setIdx((x) => Math.min(total - 1, x + 1));
    setSelected(null);
    setChecked(false);
  }

  async function bumpSeen() {
    if (!studyPackId || !total) return;
    try {
      const p = await markQuizProgress(studyPackId, { question_index: idx, action: "seen" });
      setProgress(p);
    } catch {
      // seen is optional; ignore errors silently
    }
  }

  async function act(action: "correct" | "wrong" | "reset") {
    if (!studyPackId || !total) return;
    setErr(null);
    setBusy(true);
    try {
      const p = await markQuizProgress(studyPackId, { question_index: idx, action });
      setProgress(p);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onCheck() {
    if (!cur) return;
    if (selected === null) {
      setErr("Select an option first.");
      return;
    }

    setErr(null);
    setChecked(true);
    await bumpSeen();

    // If answer_index is present, auto-mark correct/wrong.
    if (typeof cur.answer_index === "number") {
      if (selected === cur.answer_index) await act("correct");
      else await act("wrong");
    }
  }

  const isCorrect =
    checked &&
    cur?.answer_index !== null &&
    selected !== null &&
    selected === cur.answer_index;

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
          disabled={loading || busy}
          className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
        >
          Refresh
        </button>
      </div>

      <div className="mt-6">
        <h1 className="text-3xl font-semibold text-white">Quiz</h1>
        <p className="mt-2 text-sm text-white/60">
          Answer questions, check instantly, and track progress.
        </p>
      </div>

      {err && (
        <div className="mt-4 rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-100 whitespace-pre-wrap">
          {err}
        </div>
      )}

      <div className="mt-6 grid gap-4">
        <section className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_8px_40px_rgba(0,0,0,0.35)]">
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-white/10">
            <div className="text-sm font-semibold text-white/90">Progress</div>
            <div className="text-xs text-white/60">
              {total ? `Q ${idx + 1}/${total}` : "No questions"}
            </div>
          </div>
          <div className="p-5 grid gap-2 text-sm text-white/85">
            <div>
              Seen: <span className="font-semibold text-white">{seen}</span> / {total}
            </div>
            <div>
              Correct: <span className="font-semibold text-white">{correct}</span>
              <span className="text-white/60">{" "}•</span>{" "}
              Wrong: <span className="font-semibold text-white">{wrong}</span>
            </div>
            <div className="text-white/60">
              Current status: <span className="text-white">{curStatus || "-"}</span>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_8px_40px_rgba(0,0,0,0.35)]">
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-white/10">
            <div className="text-sm font-semibold text-white/90">Question</div>
            <div className="flex gap-2">
              <button
                onClick={prev}
                disabled={loading || busy || idx === 0 || total === 0}
                className="rounded-xl border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
              >
                Prev
              </button>
              <button
                onClick={next}
                disabled={loading || busy || total === 0 || idx === total - 1}
                className="rounded-xl border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>

          <div className="p-5">
            {loading ? (
              <div className="text-sm text-white/60">Loading…</div>
            ) : total === 0 ? (
              <div className="text-sm text-white/70">
                No quiz found for this pack yet. Generate materials first.
              </div>
            ) : (
              <div className="grid gap-4">
                <div className="text-lg text-white leading-relaxed">
                  {cur?.question}
                </div>

                <div className="grid gap-2">
                  {cur?.options.map((opt, i) => {
                    const isSelected = selected === i;
                    const isAnswer = checked && cur.answer_index === i;
                    const isWrongPick = checked && isSelected && cur.answer_index !== null && i !== cur.answer_index;

                    return (
                      <button
                        key={i}
                        onClick={() => {
                          setSelected(i);
                          setChecked(false);
                          setErr(null);
                        }}
                        disabled={busy}
                        className={[
                          "text-left rounded-xl border px-4 py-3 text-sm transition",
                          "border-white/10 bg-white/5 hover:bg-white/8",
                          isSelected ? "border-white/25 bg-white/10" : "",
                          isAnswer ? "border-emerald-400/40 bg-emerald-400/10" : "",
                          isWrongPick ? "border-red-400/40 bg-red-400/10" : "",
                        ].join(" ")}
                      >
                        <div className="text-white/85 leading-6">{opt}</div>
                      </button>
                    );
                  })}
                </div>

                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={onCheck}
                    disabled={busy || selected === null}
                    className="rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs text-white hover:bg-white/15 disabled:opacity-50"
                  >
                    Check answer
                  </button>

                  <button
                    onClick={() => act("correct")}
                    disabled={busy}
                    className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
                  >
                    Mark Correct
                  </button>

                  <button
                    onClick={() => act("wrong")}
                    disabled={busy}
                    className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
                  >
                    Mark Wrong
                  </button>

                  <button
                    onClick={() => act("reset")}
                    disabled={busy}
                    className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
                  >
                    Reset Status
                  </button>
                </div>

                {checked && cur?.answer_index !== null && (
                  <div className="text-sm text-white/70">
                    {isCorrect ? (
                      <span className="text-emerald-200">Correct.</span>
                    ) : (
                      <span className="text-red-200">
                        Wrong. Correct answer is option {cur.answer_index + 1}.
                      </span>
                    )}
                  </div>
                )}

                {checked && cur?.answer_index === null && (
                  <div className="text-sm text-white/60">
                    This quiz does not include answer keys yet. Use Mark Correct / Mark Wrong.
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}