"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  generateMaterials,
  getMaterials,
  getStudyPack,
  pollJobUntilDone,
  type JobGetResponse,
  type StudyMaterialRow,
  type StudyMaterialsResponse,
  type StudyPackResponse,
} from "../../../lib/api";

function toInt(v: unknown): number | null {
  const s = typeof v === "string" ? v : Array.isArray(v) ? v[0] : "";
  const n = Number.parseInt(String(s), 10);
  return Number.isFinite(n) ? n : null;
}

const KINDS = ["summary", "key_takeaways", "chapters", "flashcards", "quiz"] as const;
type Kind = (typeof KINDS)[number];

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

function PillTabs({
  active,
  onChange,
  counts,
}: {
  active: Kind;
  onChange: (k: Kind) => void;
  counts: Record<string, number>;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {KINDS.map((k) => {
        const isActive = active === k;
        return (
          <button
            key={k}
            onClick={() => onChange(k)}
            className={[
              "rounded-full px-3 py-1.5 text-xs border transition",
              isActive
                ? "bg-white/12 border-white/20 text-white"
                : "bg-white/5 border-white/10 text-white/70 hover:text-white hover:bg-white/8",
            ].join(" ")}
          >
            {k === "key_takeaways" ? "Key takeaways" : k[0].toUpperCase() + k.slice(1)}
            <span className="ml-2 text-[10px] text-white/50">{counts[k] ?? 0}</span>
          </button>
        );
      })}
    </div>
  );
}

function RenderMaterial({ m }: { m: StudyMaterialRow }) {
  const kind = m.kind as Kind;

  if (kind === "summary") {
    const text = m.content_text || (m.content_json as any)?.text || "";
    return <div className="whitespace-pre-wrap leading-7 text-white/85">{text}</div>;
  }

  if (kind === "key_takeaways") {
    const items: string[] = ((m.content_json as any)?.items || []) as string[];
    if (!items?.length) return <div className="text-white/60">No takeaways found.</div>;
    return (
      <ul className="list-disc pl-5 space-y-2">
        {items.map((t, i) => (
          <li key={i} className="leading-7 text-white/85">
            {t}
          </li>
        ))}
      </ul>
    );
  }

  if (kind === "chapters") {
    const items: any[] = ((m.content_json as any)?.items || []) as any[];
    if (!items?.length) return <div className="text-white/60">No chapters found.</div>;
    return (
      <div className="grid gap-3">
        {items.map((ch, i) => (
          <div key={i} className="rounded-xl border border-white/10 bg-white/5 p-4">
            <div className="font-semibold text-white/90">{ch?.title || `Chapter ${i + 1}`}</div>
            {ch?.summary && <div className="mt-2 text-white/75 leading-7">{ch.summary}</div>}

            {Array.isArray(ch?.sentences) && ch.sentences.length > 0 && (
              <details className="mt-3">
                <summary className="cursor-pointer text-xs text-white/60 hover:text-white/80">
                  View sentences
                </summary>
                <ul className="mt-2 list-disc pl-5 space-y-2">
                  {ch.sentences.map((s: string, j: number) => (
                    <li key={j} className="text-white/75 leading-7">
                      {s}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (kind === "flashcards") {
    const items: any[] = ((m.content_json as any)?.items || []) as any[];
    if (!items?.length) return <div className="text-white/60">No flashcards found.</div>;
    return (
      <div className="grid gap-3">
        {items.map((fc, i) => (
          <div key={i} className="rounded-xl border border-white/10 bg-white/5 p-4">
            <div className="font-semibold text-white/90">Q{i + 1}. {fc?.q}</div>
            <div className="mt-2 text-white/80 leading-7">A{i + 1}. {fc?.a}</div>
          </div>
        ))}
      </div>
    );
  }

  if (kind === "quiz") {
    const items: any[] = ((m.content_json as any)?.items || []) as any[];
    if (!items?.length) return <div className="text-white/60">No quiz found.</div>;
    return (
      <div className="grid gap-3">
        {items.map((q, i) => (
          <div key={i} className="rounded-xl border border-white/10 bg-white/5 p-4">
            <div className="font-semibold text-white/90 leading-6">
              {i + 1}. {q?.question}
            </div>
            <ol className="mt-3 list-decimal pl-5 space-y-2">
              {(q?.options || []).map((opt: string, j: number) => (
                <li key={j} className="text-white/80 leading-7">
                  {opt}
                </li>
              ))}
            </ol>
            {typeof q?.answer_index === "number" && (
              <div className="mt-3 text-xs text-white/60">Answer: {q.answer_index + 1}</div>
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <pre className="whitespace-pre-wrap text-xs text-white/70">
      {JSON.stringify(m.content_json, null, 2)}
    </pre>
  );
}

export default function PackPage() {
  const params = useParams();
  const studyPackId = useMemo(() => toInt((params as any)?.id), [params]);

  const [pack, setPack] = useState<StudyPackResponse["study_pack"] | null>(null);
  const [materials, setMaterials] = useState<StudyMaterialRow[] | null>(null);

  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [lastJob, setLastJob] = useState<JobGetResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [tab, setTab] = useState<Kind>("summary");

  const counts = useMemo(() => {
    const c: Record<string, number> = {
      summary: 0,
      key_takeaways: 0,
      chapters: 0,
      flashcards: 0,
      quiz: 0,
    };
    for (const m of materials || []) {
      const k = m.kind;
      if (typeof k === "string") c[k] = (c[k] || 0) + 1;
    }
    return c;
  }, [materials]);

  const currentMaterial = useMemo(() => {
    const list = materials || [];
    return list.find((m) => m.kind === tab) || null;
  }, [materials, tab]);

  async function refreshAll() {
    if (!studyPackId) return;
    setErr(null);
    setLoading(true);
    try {
      const p = await getStudyPack(studyPackId);
      setPack(p.study_pack);
      const m: StudyMaterialsResponse = await getMaterials(studyPackId);
      setMaterials(m.materials || []);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function onGenerate() {
    if (!studyPackId) return;
    setErr(null);
    setRunning(true);
    setLastJob(null);
    try {
      const r = await generateMaterials(studyPackId);
      const job = await pollJobUntilDone(r.job_id, { timeoutMs: 180_000, intervalMs: 1200 });
      setLastJob(job);
      await refreshAll();
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyPackId]);

  if (!studyPackId) {
    return <div className="p-6 text-white/80">Invalid pack id.</div>;
  }

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-10">
      <div className="flex items-center justify-between gap-4">
        <Link href="/packs" className="text-sm text-white/70 hover:text-white">
          ← Back
        </Link>

        <div className="flex gap-2 flex-wrap justify-end">
          {/* ✅ NEW: Study Hub CTA */}
          <Link
            href={`/packs/${studyPackId}/study`}
            className={[
              "rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs",
              "text-white hover:bg-white/15",
              loading ? "pointer-events-none opacity-50" : "",
            ].join(" ")}
          >
            Study
          </Link>

          {/* Existing study links (keep) */}
          <Link
            href={`/packs/${studyPackId}/study/flashcards`}
            className={[
              "rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs",
              "text-white/85 hover:bg-white/8",
              loading ? "pointer-events-none opacity-50" : "",
            ].join(" ")}
          >
            Study Flashcards
          </Link>

          <Link
            href={`/packs/${studyPackId}/study/transcript`}
            className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8"
          >
            Study transcript
          </Link>

          <Link
            href={`/packs/${studyPackId}/study/chapters`}
            className={[
              "rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs",
              "text-white/85 hover:bg-white/8",
              loading ? "pointer-events-none opacity-50" : "",
            ].join(" ")}
          >
            Study chapters
          </Link>

          <Link
            href={`/packs/${studyPackId}/study/quiz`}
            className={[
              "rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs",
              "text-white/85 hover:bg-white/8",
              loading ? "pointer-events-none opacity-50" : "",
            ].join(" ")}
          >
            Study quiz
          </Link>

          <button
            onClick={refreshAll}
            disabled={loading || running}
            className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
          >
            Refresh
          </button>

          <button
            onClick={onGenerate}
            disabled={loading || running}
            className="rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs text-white hover:bg-white/15 disabled:opacity-50"
          >
            Generate materials
          </button>
        </div>
      </div>

      <div className="mt-6">
        <h1 className="text-3xl font-semibold text-white">Study Pack #{studyPackId}</h1>
        <p className="mt-2 text-sm text-white/60">Generate and browse materials in a clean structure.</p>
      </div>

      {err && (
        <div className="mt-4 rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-100 whitespace-pre-wrap">
          {err}
        </div>
      )}

      <div className="mt-6 grid gap-4">
        {lastJob && (
          <GlassCard title="Last generation job" right={<span className="text-white/60">Job #{lastJob.job_id}</span>}>
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="text-sm text-white/80">
                Status: <span className="font-semibold text-white">{lastJob.status}</span>
              </div>

              <div className="flex items-center gap-3">
                {lastJob.error ? (
                  <div className="text-xs text-red-200">{lastJob.error}</div>
                ) : (
                  <div className="text-xs text-white/50">OK</div>
                )}

                <Link
                  href={`/jobs/${lastJob.job_id}`}
                  className="text-xs text-white/80 underline underline-offset-4 hover:text-white"
                >
                  Open job
                </Link>
              </div>
            </div>
          </GlassCard>
        )}

        <GlassCard title="Pack details">
          {loading && <div className="text-sm text-white/60">Loading…</div>}

          {pack && (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="space-y-2">
                <div className="text-xs text-white/50">Source</div>
                <div className="text-sm text-white/90">{pack.source_type}</div>
              </div>

              <div className="space-y-2">
                <div className="text-xs text-white/50">Language</div>
                <div className="text-sm text-white/90">{pack.language || "-"}</div>
              </div>

              <div className="space-y-2 md:col-span-2">
                <div className="text-xs text-white/50">URL</div>
                <div className="text-sm text-white/85 break-all">{pack.source_url}</div>
              </div>

              <div className="space-y-2">
                <div className="text-xs text-white/50">Status</div>
                <div className="text-sm text-white/90">{pack.status}</div>
              </div>
            </div>
          )}
        </GlassCard>

        <GlassCard title="Materials" right={<span className="text-white/60">Items: {(materials || []).length}</span>}>
          {!materials?.length ? (
            <div className="text-sm text-white/70">
              No materials found for this pack yet. Click{" "}
              <span className="text-white font-semibold">Generate materials</span>.
            </div>
          ) : (
            <div className="space-y-4">
              <PillTabs active={tab} onChange={setTab} counts={counts} />

              <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
                {currentMaterial ? (
                  <RenderMaterial m={currentMaterial} />
                ) : (
                  <div className="text-sm text-white/60">No data for this tab.</div>
                )}
              </div>
            </div>
          )}
        </GlassCard>
      </div>
    </main>
  );
}