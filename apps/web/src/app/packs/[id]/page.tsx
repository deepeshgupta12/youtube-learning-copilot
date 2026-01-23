"use client";

// apps/web/src/app/packs/[id]/page.tsx
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

function toInt(v: string | string[]): number | null {
  const s = Array.isArray(v) ? v[0] : v;
  const n = Number.parseInt(String(s), 10);
  return Number.isFinite(n) ? n : null;
}

function safeString(x: any): string {
  if (x === null || x === undefined) return "";
  if (typeof x === "string") return x;
  try {
    return JSON.stringify(x, null, 2);
  } catch {
    return String(x);
  }
}

function MaterialSection({ title, children }: { title: string; children: any }) {
  return (
    <section style={{ marginTop: 18, padding: 14, borderRadius: 12, border: "1px solid rgba(0,0,0,0.12)" }}>
      <h2 style={{ marginTop: 0, marginBottom: 10, fontSize: 18 }}>{title}</h2>
      {children}
    </section>
  );
}

function renderMaterial(m: StudyMaterialRow) {
  const kind = m.kind;

  if (kind === "summary") {
    const text = m.content_text || m.content_json?.text || "";
    return <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{text}</div>;
  }

  if (kind === "key_takeaways") {
    const items: string[] = m.content_json?.items || [];
    if (!items?.length) {
      return <div style={{ opacity: 0.75 }}>No takeaways found.</div>;
    }
    return (
      <ul style={{ marginTop: 0 }}>
        {items.map((t, i) => (
          <li key={i} style={{ marginBottom: 6, lineHeight: 1.5 }}>
            {t}
          </li>
        ))}
      </ul>
    );
  }

  if (kind === "chapters") {
    const items: any[] = m.content_json?.items || [];
    if (!items?.length) return <div style={{ opacity: 0.75 }}>No chapters found.</div>;

    return (
      <div style={{ display: "grid", gap: 12 }}>
        {items.map((ch, i) => (
          <div key={i} style={{ padding: 12, borderRadius: 10, border: "1px solid rgba(0,0,0,0.12)" }}>
            <div style={{ fontWeight: 700 }}>{ch?.title || `Chapter ${i + 1}`}</div>
            {ch?.summary && <div style={{ marginTop: 6, opacity: 0.85, lineHeight: 1.5 }}>{ch.summary}</div>}
            {Array.isArray(ch?.sentences) && ch.sentences.length > 0 && (
              <details style={{ marginTop: 10 }}>
                <summary style={{ cursor: "pointer" }}>Sentences</summary>
                <ul>
                  {ch.sentences.map((s: string, j: number) => (
                    <li key={j} style={{ marginBottom: 6, lineHeight: 1.5 }}>
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
    const items: any[] = m.content_json?.items || [];
    if (!items?.length) return <div style={{ opacity: 0.75 }}>No flashcards found.</div>;

    return (
      <div style={{ display: "grid", gap: 12 }}>
        {items.map((fc, i) => (
          <div key={i} style={{ padding: 12, borderRadius: 10, border: "1px solid rgba(0,0,0,0.12)" }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>{fc?.q || `Q${i + 1}`}</div>
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{fc?.a || ""}</div>
          </div>
        ))}
      </div>
    );
  }

  if (kind === "quiz") {
    const items: any[] = m.content_json?.items || [];
    if (!items?.length) return <div style={{ opacity: 0.75 }}>No quiz items found.</div>;

    return (
      <div style={{ display: "grid", gap: 12 }}>
        {items.map((q, i) => {
          const opts: string[] = q?.options || [];
          const ansIdx: number | null = Number.isInteger(q?.answer_index) ? q.answer_index : null;
          return (
            <div key={i} style={{ padding: 12, borderRadius: 10, border: "1px solid rgba(0,0,0,0.12)" }}>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>{q?.question || `Question ${i + 1}`}</div>
              <ol style={{ marginTop: 0 }}>
                {opts.map((o, j) => (
                  <li key={j} style={{ marginBottom: 6, lineHeight: 1.5 }}>
                    {o}
                  </li>
                ))}
              </ol>
              {ansIdx !== null && ansIdx >= 0 && ansIdx < opts.length && (
                <div style={{ marginTop: 8, opacity: 0.85 }}>
                  <strong>Answer:</strong> {ansIdx + 1}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  // fallback
  return (
    <pre style={{ whiteSpace: "pre-wrap", lineHeight: 1.4 }}>
      {safeString(m.content_json)}
    </pre>
  );
}

export default function PackPage({ params }: { params: { id: string } }) {
  const studyPackId = useMemo(() => toInt(params.id), [params.id]);

  const [pack, setPack] = useState<StudyPackResponse["study_pack"] | null>(null);
  const [materials, setMaterials] = useState<StudyMaterialRow[] | null>(null);

  const [loading, setLoading] = useState(false);
  const [job, setJob] = useState<JobGetResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refreshAll() {
    if (!studyPackId) return;
    setErr(null);
    setLoading(true);
    try {
      const sp = await getStudyPack(studyPackId);
      setPack(sp.study_pack);

      const mats = await getMaterials(studyPackId);
      setMaterials(mats.materials || []);
    } catch (e: any) {
      setErr(e?.message || "Failed to load pack/materials.");
    } finally {
      setLoading(false);
    }
  }

  async function onGenerate() {
    if (!studyPackId) return;
    setErr(null);
    setJob(null);
    setLoading(true);
    try {
      const resp = await generateMaterials(studyPackId);
      const finalJob = await pollJobUntilDone(resp.job_id, { intervalMs: 1200, timeoutMs: 180000 });
      setJob(finalJob);

      if (finalJob.status === "failed") {
        setErr(finalJob.error || "Generation job failed.");
      } else {
        const mats: StudyMaterialsResponse = await getMaterials(studyPackId);
        setMaterials(mats.materials || []);
      }
    } catch (e: any) {
      setErr(e?.message || "Failed to generate materials.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyPackId]);

  if (!studyPackId) {
    return (
      <main style={{ padding: 24, maxWidth: 960, margin: "0 auto" }}>
        <h1>Pack</h1>
        <p>Invalid pack id.</p>
      </main>
    );
  }

  // Group materials by kind for deterministic display order
  const byKind = useMemo(() => {
    const map = new Map<string, StudyMaterialRow>();
    (materials || []).forEach((m) => map.set(m.kind, m));
    return map;
  }, [materials]);

  return (
    <main style={{ padding: 24, maxWidth: 960, margin: "0 auto" }}>
      <a href="/" style={{ textDecoration: "none" }}>← Back</a>

      <h1 style={{ marginBottom: 6 }}>Study Pack #{studyPackId}</h1>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
        <button
          onClick={refreshAll}
          disabled={loading}
          style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid rgba(0,0,0,0.2)" }}
        >
          {loading ? "Loading..." : "Refresh"}
        </button>

        <button
          onClick={onGenerate}
          disabled={loading}
          style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid rgba(0,0,0,0.2)" }}
        >
          {loading ? "Working..." : "Generate Study Materials"}
        </button>
      </div>

      {err && (
        <div style={{ marginTop: 14, padding: 12, borderRadius: 10, border: "1px solid rgba(255,0,0,0.3)" }}>
          <strong>Error:</strong> {err}
        </div>
      )}

      {pack && (
        <section style={{ marginTop: 16, padding: 14, borderRadius: 12, border: "1px solid rgba(0,0,0,0.12)" }}>
          <div><strong>Source:</strong> {pack.source_type}</div>
          <div style={{ marginTop: 6 }}><strong>URL:</strong> <a href={pack.source_url} target="_blank" rel="noreferrer">{pack.source_url}</a></div>
          <div style={{ marginTop: 6 }}><strong>Language:</strong> {pack.language || "-"}</div>
          <div style={{ marginTop: 6 }}><strong>Status:</strong> {pack.status}</div>
          {pack.error && <div style={{ marginTop: 6 }}><strong>Pack Error:</strong> {pack.error}</div>}
        </section>
      )}

      {job && (
        <section style={{ marginTop: 16, padding: 14, borderRadius: 12, border: "1px solid rgba(0,0,0,0.12)" }}>
          <div><strong>Last job status:</strong> {job.status}</div>
          {job.error && <div style={{ marginTop: 6 }}><strong>Job error:</strong> {job.error}</div>}
        </section>
      )}

      <div style={{ marginTop: 18 }}>
        <h2 style={{ marginBottom: 6 }}>Materials</h2>
        <p style={{ marginTop: 0, opacity: 0.75 }}>
          If you don’t see materials yet, click “Generate Study Materials”.
        </p>

        {!materials && <div style={{ opacity: 0.75 }}>Loading materials...</div>}

        {materials && materials.length === 0 && (
          <div style={{ opacity: 0.75 }}>No materials found for this pack.</div>
        )}

        {materials && materials.length > 0 && (
          <>
            <MaterialSection title="Summary">
              {byKind.get("summary") ? renderMaterial(byKind.get("summary")!) : <div style={{ opacity: 0.75 }}>Missing</div>}
            </MaterialSection>

            <MaterialSection title="Key takeaways">
              {byKind.get("key_takeaways") ? renderMaterial(byKind.get("key_takeaways")!) : <div style={{ opacity: 0.75 }}>Missing</div>}
            </MaterialSection>

            <MaterialSection title="Chapters">
              {byKind.get("chapters") ? renderMaterial(byKind.get("chapters")!) : <div style={{ opacity: 0.75 }}>Missing</div>}
            </MaterialSection>

            <MaterialSection title="Flashcards">
              {byKind.get("flashcards") ? renderMaterial(byKind.get("flashcards")!) : <div style={{ opacity: 0.75 }}>Missing</div>}
            </MaterialSection>

            <MaterialSection title="Quiz">
              {byKind.get("quiz") ? renderMaterial(byKind.get("quiz")!) : <div style={{ opacity: 0.75 }}>Missing</div>}
            </MaterialSection>
          </>
        )}
      </div>
    </main>
  );
}