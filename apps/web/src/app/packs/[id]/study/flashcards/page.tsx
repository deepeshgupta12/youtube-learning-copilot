"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  getMaterials,
  getFlashcardProgress,
  markFlashcardProgress,
  type FlashcardProgressResponse,
  type StudyMaterialRow,
  type StudyMaterialsResponse,
} from "../../../../../lib/api";

function toInt(v: unknown): number | null {
  const s = typeof v === "string" ? v : Array.isArray(v) ? v[0] : "";
  const n = Number.parseInt(String(s), 10);
  return Number.isFinite(n) ? n : null;
}

function extractFlashcards(materials: StudyMaterialRow[] | null): { q: string; a: string }[] {
  const row = (materials || []).find((m) => m.kind === "flashcards");
  const items = (row?.content_json as any)?.items;
  if (!Array.isArray(items)) return [];
  return items
    .filter((x: any) => x && typeof x === "object")
    .map((x: any) => ({ q: String(x.q || ""), a: String(x.a || "") }))
    .filter((x) => x.q.trim() || x.a.trim());
}

export default function FlashcardsStudyPage() {
  const params = useParams();
  const studyPackId = useMemo(() => toInt((params as any)?.id), [params]);

  const [materials, setMaterials] = useState<StudyMaterialRow[] | null>(null);
  const [cards, setCards] = useState<{ q: string; a: string }[]>([]);
  const [progress, setProgress] = useState<FlashcardProgressResponse | null>(null);

  const [idx, setIdx] = useState(0);
  const [flipped, setFlipped] = useState(false);

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

      const extracted = extractFlashcards(list);
      setCards(extracted);

      const p = await getFlashcardProgress(studyPackId);
      setProgress(p);

      setIdx((prev) => {
        if (!extracted.length) return 0;
        return Math.min(prev, extracted.length - 1);
      });
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

  const total = cards.length;
  const cur = total ? cards[idx] : null;
  const curStatus = progress?.items?.[idx]?.status ?? null;

  function prev() {
    if (!total) return;
    setFlipped(false);
    setIdx((x) => Math.max(0, x - 1));
  }

  function next() {
    if (!total) return;
    setFlipped(false);
    setIdx((x) => Math.min(total - 1, x + 1));
  }

  async function act(action: "known" | "review_later" | "reset") {
    if (!studyPackId || !total) return;
    setErr(null);
    setBusy(true);
    try {
      const p = await markFlashcardProgress(studyPackId, { card_index: idx, action });
      setProgress(p);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  const seen = progress?.seen_cards ?? 0;
  const known = progress?.known_cards ?? 0;
  const reviewLater = progress?.review_later_cards ?? 0;

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
        <h1 className="text-3xl font-semibold text-white">Flashcards</h1>
        <p className="mt-2 text-sm text-white/60">
          Flip the card, then mark it as Known or Review later.
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
              {total ? `Card ${idx + 1}/${total}` : "No cards"}
            </div>
          </div>
          <div className="p-5 grid gap-2 text-sm text-white/85">
            <div>
              Seen: <span className="font-semibold text-white">{seen}</span> / {total}
            </div>
            <div>
              Known: <span className="font-semibold text-white">{known}</span>
              <span className="text-white/60">{" "}•</span>{" "}
              Review later: <span className="font-semibold text-white">{reviewLater}</span>
            </div>
            <div className="text-white/60">
              Current status: <span className="text-white">{curStatus || "-"}</span>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_8px_40px_rgba(0,0,0,0.35)]">
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-white/10">
            <div className="text-sm font-semibold text-white/90">Card</div>
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
                No flashcards found for this pack yet. Generate materials first.
              </div>
            ) : (
              <div className="grid gap-4">
                <button
                  onClick={() => setFlipped((x) => !x)}
                  className="w-full rounded-2xl border border-white/10 bg-white/5 px-5 py-6 text-left hover:bg-white/8"
                >
                  {!flipped ? (
                    <>
                      <div className="text-xs text-white/60">Question</div>
                      <div className="mt-2 text-lg text-white leading-relaxed">
                        {cur?.q || "(empty)"}
                      </div>
                      <div className="mt-4 text-xs text-white/50">Click to reveal answer</div>
                    </>
                  ) : (
                    <>
                      <div className="text-xs text-white/60">Answer</div>
                      <div className="mt-2 text-lg text-white leading-relaxed">
                        {cur?.a || "(empty)"}
                      </div>
                      <div className="mt-4 text-xs text-white/50">Click to go back</div>
                    </>
                  )}
                </button>

                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => act("known")}
                    disabled={busy}
                    className="rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs text-white hover:bg-white/15 disabled:opacity-50"
                  >
                    Mark Known
                  </button>
                  <button
                    onClick={() => act("review_later")}
                    disabled={busy}
                    className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
                  >
                    Review Later
                  </button>
                  <button
                    onClick={() => act("reset")}
                    disabled={busy}
                    className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
                  >
                    Reset Status
                  </button>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}