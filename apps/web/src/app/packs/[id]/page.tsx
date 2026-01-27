"use client";

// apps/web/src/app/packs/[id]/page.tsx
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
import Link from "next/link";

function toInt(v: unknown): number | null {
  const s = typeof v === "string" ? v : Array.isArray(v) ? v[0] : "";
  const n = Number.parseInt(String(s), 10);
  return Number.isFinite(n) ? n : null;
}

function MaterialSection({ title, children }: { title: string; children: any }) {
  return (
    <section style={{ marginTop: 18, padding: 14, borderRadius: 12, border: "1px solid rgba(255,255,255,0.12)" }}>
      <h2 style={{ marginTop: 0, marginBottom: 10, fontSize: 18 }}>{title}</h2>
      {children}
    </section>
  );
}

function renderMaterial(m: StudyMaterialRow) {
  const kind = m.kind;

  if (kind === "summary") {
    const text = m.content_text || (m.content_json as any)?.text || "";
    return <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{text}</div>;
  }

  if (kind === "key_takeaways") {
    const items: string[] = ((m.content_json as any)?.items || []) as string[];
    if (!items?.length) return <div style={{ opacity: 0.75 }}>No takeaways found.</div>;
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
    const items: any[] = ((m.content_json as any)?.items || []) as any[];
    if (!items?.length) return <div style={{ opacity: 0.75 }}>No chapters found.</div>;

    return (
      <div style={{ display: "grid", gap: 12 }}>
        {items.map((ch, i) => (
          <div key={i} style={{ padding: 12, borderRadius: 10, border: "1px solid rgba(255,255,255,0.12)" }}>
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
    const items: any[] = ((m.content_json as any)?.items || []) as any[];
    if (!items?.length) return <div style={{ opacity: 0.75 }}>No flashcards found.</div>;

    return (
      <div style={{ display: "grid", gap: 10 }}>
        {items.map((fc, i) => (
          <div key={i} style={{ padding: 12, borderRadius: 10, border: "1px solid rgba(255,255,255,0.12)" }}>
            <div style={{ fontWeight: 700 }}>Q{i + 1}. {fc?.q}</div>
            <div style={{ marginTop: 8, opacity: 0.9, lineHeight: 1.5 }}>A{i + 1}. {fc?.a}</div>
          </div>
        ))}
      </div>
    );
  }

  if (kind === "quiz") {
    const items: any[] = ((m.content_json as any)?.items || []) as any[];
    if (!items?.length) return <div style={{ opacity: 0.75 }}>No quiz found.</div>;

    return (
      <div style={{ display: "grid", gap: 10 }}>
        {items.map((q, i) => (
          <div key={i} style={{ padding: 12, borderRadius: 10, border: "1px solid rgba(255,255,255,0.12)" }}>
            <div style={{ fontWeight: 700, lineHeight: 1.4 }}>{i + 1}. {q?.question}</div>
            <ol style={{ marginTop: 8 }}>
              {(q?.options || []).map((opt: string, j: number) => (
                <li key={j} style={{ marginBottom: 6, lineHeight: 1.5 }}>
                  {opt}
                </li>
              ))}
            </ol>
            {typeof q?.answer_index === "number" && (
              <div style={{ marginTop: 6, opacity: 0.85 }}>
                Answer: {q.answer_index + 1}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  return <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(m.content_json, null, 2)}</pre>;
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
      const job = await pollJobUntilDone(r.job_id, { timeoutMs: 120_000, intervalMs: 1200 });
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

  if (!studyPackId) return <div style={{ padding: 24 }}>Invalid pack id.</div>;

  return (
    <main style={{ maxWidth: 820, margin: "0 auto", padding: 24 }}>
      <Link href="/" style={{ opacity: 0.85 }}>← Back</Link>
      <h1 style={{ marginTop: 10 }}>Study Pack #{studyPackId}</h1>

      <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
        <button onClick={refreshAll} disabled={loading || running}>Refresh</button>
        <button onClick={onGenerate} disabled={loading || running}>Generate Study Materials</button>
      </div>

      {err && <div style={{ marginTop: 12, color: "tomato", whiteSpace: "pre-wrap" }}>{err}</div>}

      {loading && <div style={{ marginTop: 12, opacity: 0.8 }}>Loading…</div>}

      {pack && (
        <MaterialSection title="Pack">
          <div><b>Source:</b> {pack.source_type}</div>
          <div><b>URL:</b> {pack.source_url}</div>
          <div><b>Language:</b> {pack.language || "-"}</div>
          <div><b>Status:</b> {pack.status}</div>
        </MaterialSection>
      )}

      {lastJob && (
        <MaterialSection title="Last generation job">
          <div><b>Job:</b> {lastJob.job_id}</div>
          <div><b>Status:</b> {lastJob.status}</div>
          {lastJob.error && <div style={{ color: "tomato" }}><b>Error:</b> {lastJob.error}</div>}
        </MaterialSection>
      )}

      <MaterialSection title="Materials">
        {!materials?.length ? (
          <div style={{ opacity: 0.8 }}>
            If you don’t see materials yet, click “Generate Study Materials”.
            <div style={{ marginTop: 6, opacity: 0.8 }}>No materials found for this pack.</div>
          </div>
        ) : (
          <div style={{ display: "grid", gap: 14 }}>
            {materials.map((m) => (
              <MaterialSection key={m.id} title={`${m.kind} (${m.status})`}>
                {renderMaterial(m)}
              </MaterialSection>
            ))}
          </div>
        )}
      </MaterialSection>
    </main>
  );
}