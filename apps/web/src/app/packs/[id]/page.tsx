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

type TabKey = "summary" | "key_takeaways" | "chapters" | "flashcards" | "quiz";

const TAB_LABELS: Record<TabKey, string> = {
  summary: "Summary",
  key_takeaways: "Key takeaways",
  chapters: "Chapters",
  flashcards: "Flashcards",
  quiz: "Quiz",
};

function byKind(materials: StudyMaterialRow[] | null, kind: TabKey): StudyMaterialRow | null {
  if (!materials?.length) return null;
  return materials.find((m) => m.kind === kind) || null;
}

function shortUrl(u?: string | null): string {
  if (!u) return "-";
  if (u.length <= 70) return u;
  return `${u.slice(0, 50)}…${u.slice(-16)}`;
}

function MetaLine({ label, value }: { label: string; value: any }) {
  return (
    <div className="kv">
      <b>{label}</b>
      <span className="muted" style={{ wordBreak: "break-word" }}>
        {value}
      </span>
    </div>
  );
}

function renderSummary(m: StudyMaterialRow) {
  const text = m.content_text || (m.content_json as any)?.text || "";
  if (!text) return <div className="muted">No summary found.</div>;
  return <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.75 }}>{text}</div>;
}

function renderTakeaways(m: StudyMaterialRow) {
  const items: string[] = ((m.content_json as any)?.items || []) as string[];
  if (!items?.length) return <div className="muted">No takeaways found.</div>;
  return (
    <ul style={{ marginTop: 0, lineHeight: 1.75 }}>
      {items.map((t, i) => (
        <li key={i} style={{ marginBottom: 8 }}>
          {t}
        </li>
      ))}
    </ul>
  );
}

function renderChapters(m: StudyMaterialRow) {
  const items: any[] = ((m.content_json as any)?.items || []) as any[];
  if (!items?.length) return <div className="muted">No chapters found.</div>;

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {items.map((ch, i) => (
        <div key={i} className="glass card" style={{ background: "rgba(255,255,255,0.05)", boxShadow: "var(--shadow2)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "baseline" }}>
            <div style={{ fontWeight: 800, letterSpacing: "-0.01em" }}>{ch?.title || `Chapter ${i + 1}`}</div>
            <span className="badge subtle">
              <span className="muted2">#{i + 1}</span>
            </span>
          </div>
          {ch?.summary && <div className="muted" style={{ marginTop: 8, lineHeight: 1.75 }}>{ch.summary}</div>}

          {Array.isArray(ch?.sentences) && ch.sentences.length > 0 && (
            <details style={{ marginTop: 10 }}>
              <summary style={{ cursor: "pointer" }} className="muted">
                Show transcript snippets
              </summary>
              <ul style={{ marginTop: 10, lineHeight: 1.75 }}>
                {ch.sentences.map((s: string, j: number) => (
                  <li key={j} style={{ marginBottom: 8 }}>
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

function renderFlashcards(m: StudyMaterialRow) {
  const items: any[] = ((m.content_json as any)?.items || []) as any[];
  if (!items?.length) return <div className="muted">No flashcards found.</div>;

  return (
    <div style={{ display: "grid", gap: 10 }}>
      {items.map((fc, i) => (
        <div key={i} className="glass card" style={{ background: "rgba(255,255,255,0.05)", boxShadow: "var(--shadow2)" }}>
          <div style={{ fontWeight: 800, letterSpacing: "-0.01em" }}>
            Q{i + 1}. {fc?.q}
          </div>
          <div className="muted" style={{ marginTop: 10, lineHeight: 1.75 }}>
            A{i + 1}. {fc?.a}
          </div>
        </div>
      ))}
    </div>
  );
}

function renderQuiz(m: StudyMaterialRow) {
  const items: any[] = ((m.content_json as any)?.items || []) as any[];
  if (!items?.length) return <div className="muted">No quiz found.</div>;

  return (
    <div style={{ display: "grid", gap: 10 }}>
      {items.map((q, i) => (
        <div key={i} className="glass card" style={{ background: "rgba(255,255,255,0.05)", boxShadow: "var(--shadow2)" }}>
          <div style={{ fontWeight: 800, letterSpacing: "-0.01em", lineHeight: 1.45 }}>
            {i + 1}. {q?.question}
          </div>
          <ol style={{ marginTop: 10, lineHeight: 1.75 }}>
            {(q?.options || []).map((opt: string, j: number) => (
              <li key={j} style={{ marginBottom: 8 }}>
                {opt}
              </li>
            ))}
          </ol>
          {typeof q?.answer_index === "number" && (
            <div className="badge" style={{ marginTop: 10 }}>
              <span className="muted2">Answer</span>&nbsp; <span className="mono">{q.answer_index + 1}</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function renderTab(m: StudyMaterialRow | null, tab: TabKey) {
  if (!m) return <div className="muted">No material generated for this section yet.</div>;
  if (tab === "summary") return renderSummary(m);
  if (tab === "key_takeaways") return renderTakeaways(m);
  if (tab === "chapters") return renderChapters(m);
  if (tab === "flashcards") return renderFlashcards(m);
  return renderQuiz(m);
}

export default function PackPage() {
  const params = useParams();
  const studyPackId = useMemo(() => toInt((params as any)?.id), [params]);

  const [pack, setPack] = useState<StudyPackResponse["study_pack"] | null>(null);
  const [materials, setMaterials] = useState<StudyMaterialRow[] | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);

  const [lastJob, setLastJob] = useState<JobGetResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [tab, setTab] = useState<TabKey>("summary");

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
    return (
      <main style={{ marginTop: 18 }}>
        <section className="glass card">
          <div className="card-title">Invalid pack id</div>
          <Link className="btn" href="/">Go home</Link>
        </section>
      </main>
    );
  }

  const current = byKind(materials, tab);

  return (
    <main style={{ marginTop: 18 }}>
      {/* TOP BAR */}
      <section className="glass card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <Link href="/" className="muted">← Back</Link>
            <h1 style={{ margin: "8px 0 0", fontSize: 26, letterSpacing: "-0.03em" }}>
              Study Pack <span className="mono">#{studyPackId}</span>
            </h1>
            <div className="muted" style={{ marginTop: 6 }}>
              Generate and browse materials in a clean structure.
            </div>
          </div>

          <div className="row">
            <button className="btn ghost" onClick={refreshAll} disabled={loading || running}>
              {loading ? "Refreshing…" : "Refresh"}
            </button>
            <button className="btn primary" onClick={onGenerate} disabled={loading || running}>
              {running ? "Generating…" : "Generate materials"}
            </button>
          </div>
        </div>

        {err && (
          <div className="alert" style={{ marginTop: 12 }}>
            <strong>Error:</strong> {err}
          </div>
        )}

        {lastJob && (
          <div className="success" style={{ marginTop: 12 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <strong>Last generation job:</strong> <span className="mono">#{lastJob.job_id}</span>
              </div>
              <span className="badge">
                <span className="muted2">Status</span>&nbsp; <span className="mono">{lastJob.status}</span>
              </span>
            </div>
            {lastJob.error && (
              <div style={{ marginTop: 8 }}>
                <strong>Job error:</strong> {lastJob.error}
              </div>
            )}
          </div>
        )}
      </section>

      {/* PACK META */}
      <section className="glass card" style={{ marginTop: 14 }}>
        <div className="card-title">Pack details</div>
        {!pack ? (
          <div className="muted">{loading ? "Loading…" : "Not found."}</div>
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            <MetaLine label="Source" value={pack.source_type} />
            <MetaLine label="URL" value={<span className="mono">{shortUrl(pack.source_url)}</span>} />
            <MetaLine label="Language" value={<span className="mono">{pack.language || "-"}</span>} />
            <MetaLine label="Status" value={<span className="mono">{pack.status}</span>} />
          </div>
        )}
      </section>

      {/* MATERIALS */}
      <section className="glass card" style={{ marginTop: 14 }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="card-title" style={{ marginBottom: 0 }}>
            Materials
          </div>

          {materials?.length ? (
            <span className="badge">
              <span className="muted2">Items</span>&nbsp; <span className="mono">{materials.length}</span>
            </span>
          ) : (
            <span className="badge subtle">No materials yet</span>
          )}
        </div>

        <div className="tabs">
          {(Object.keys(TAB_LABELS) as TabKey[]).map((k) => (
            <button
              key={k}
              className={`tab ${tab === k ? "active" : ""}`}
              onClick={() => setTab(k)}
              disabled={loading}
            >
              {TAB_LABELS[k]}
            </button>
          ))}
        </div>

        <div className="sep" />

        {!materials?.length ? (
          <div className="muted" style={{ lineHeight: 1.75 }}>
            Click <b>Generate materials</b> to create summary, takeaways, chapters, flashcards, and quiz for this pack.
          </div>
        ) : (
          <>
            {/* Per-material error banner if present */}
            {current?.error && (
              <div className="alert" style={{ marginBottom: 12 }}>
                <strong>Note:</strong> {current.error}
              </div>
            )}
            {renderTab(current, tab)}
          </>
        )}
      </section>
    </main>
  );
}