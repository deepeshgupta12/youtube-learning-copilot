"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  createStudyPackFromYoutube,
  pollJobUntilDone,
  type JobGetResponse,
  type StudyPackFromYoutubeResponse,
} from "../lib/api";

function isLikelyYoutubeUrl(v: string): boolean {
  const s = (v || "").trim();
  if (!s) return false;
  return s.includes("youtube.com/") || s.includes("youtu.be/");
}

function shortId(id?: string | null): string {
  if (!id) return "-";
  if (id.length <= 10) return id;
  return `${id.slice(0, 6)}…${id.slice(-4)}`;
}

export default function HomePage() {
  const router = useRouter();

  const [url, setUrl] = useState<string>("");
  const [language, setLanguage] = useState<string>("en");

  const [creating, setCreating] = useState(false);
  const [createResp, setCreateResp] = useState<StudyPackFromYoutubeResponse | null>(null);

  const [job, setJob] = useState<JobGetResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const canSubmit = useMemo(() => isLikelyYoutubeUrl(url) && !creating, [url, creating]);

  async function onCreate() {
    setErr(null);
    setCreateResp(null);
    setJob(null);

    const u = url.trim();
    if (!isLikelyYoutubeUrl(u)) {
      setErr("Please enter a valid YouTube URL.");
      return;
    }

    setCreating(true);
    try {
      const resp = await createStudyPackFromYoutube(u, language?.trim() || "en");
      setCreateResp(resp);

      const finalJob = await pollJobUntilDone(resp.job_id, { intervalMs: 1200, timeoutMs: 180000 });
      setJob(finalJob);

      if (finalJob.status === "failed") {
        setErr(finalJob.error || "Job failed.");
        return;
      }

      if (finalJob.status === "done") {
        router.push(`/packs/${resp.study_pack_id}`);
      }
    } catch (e: any) {
      setErr(e?.message || "Something went wrong.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main style={{ marginTop: 18 }}>
      {/* HERO */}
      <section className="glass card">
        <div style={{ display: "grid", gap: 10 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <h1 style={{ margin: 0, fontSize: 30, letterSpacing: "-0.03em" }}>Turn YouTube into a study pack</h1>
              <p style={{ margin: "6px 0 0", color: "var(--muted)" }}>
                Ingest transcript → Generate summary, takeaways, chapters, flashcards, and quiz.
              </p>
            </div>
            <div className="row">
              <span className="badge">
                <span className="mono">/study-packs/from-youtube</span>
              </span>
              <span className="badge">
                <span className="mono">/study-packs/:id/generate</span>
              </span>
            </div>
          </div>

          <div className="sep" />

          <div className="grid-2">
            <div style={{ display: "grid", gap: 10 }}>
              <label style={{ display: "grid", gap: 6 }}>
                <span className="muted">YouTube URL</span>
                <input
                  className="input"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                />
              </label>

              <div className="row" style={{ justifyContent: "space-between" }}>
                <label style={{ display: "grid", gap: 6, width: 220 }}>
                  <span className="muted">Language</span>
                  <input
                    className="input"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    placeholder="en"
                  />
                </label>

                <div className="row">
                  <button className="btn ghost" onClick={() => setUrl("")} disabled={creating}>
                    Clear
                  </button>
                  <button className="btn primary" onClick={onCreate} disabled={!canSubmit}>
                    {creating ? "Creating + ingesting…" : "Create study pack"}
                  </button>
                </div>
              </div>

              {err && (
                <div className="alert">
                  <strong>Error:</strong> {err}
                </div>
              )}
            </div>

            <div className="glass card" style={{ background: "rgba(255,255,255,0.05)", boxShadow: "var(--shadow2)" }}>
              <div className="card-title">What you get</div>
              <div className="muted" style={{ display: "grid", gap: 10, lineHeight: 1.6 }}>
                <div>• A clean summary (not a transcript dump)</div>
                <div>• Key takeaways (high signal)</div>
                <div>• Chapters (structured learning path)</div>
                <div>• Flashcards (memory reinforcement)</div>
                <div>• Quiz (quick self-test)</div>
              </div>
              <div className="sep" />
              <div className="muted2" style={{ lineHeight: 1.6 }}>
                Tip: keep language as <span className="mono">en</span> unless you ingested captions in another language.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* STATUS */}
      {(createResp || job) && (
        <section className="glass card" style={{ marginTop: 14 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div className="card-title" style={{ marginBottom: 0 }}>
              Ingestion status
            </div>
            {createResp?.study_pack_id && (
              <button className="btn" onClick={() => router.push(`/packs/${createResp.study_pack_id}`)}>
                Open pack
              </button>
            )}
          </div>

          <div className="sep" />

          {createResp && (
            <div style={{ display: "grid", gap: 6 }}>
              <div className="kv">
                <b>Study pack</b>
                <span className="mono">#{createResp.study_pack_id}</span>
              </div>
              <div className="kv">
                <b>Video</b>
                <span className="mono">{createResp.video_id}</span>
              </div>
              <div className="kv">
                <b>Job</b>
                <span className="mono">#{createResp.job_id}</span>
              </div>
              <div className="kv">
                <b>Task</b>
                <span className="mono">{shortId(createResp.task_id)}</span>
              </div>
            </div>
          )}

          {job && (
            <>
              <div className="sep" />
              <div className="row">
                <span className="badge">
                  <span className="muted2">Status</span>&nbsp; <span className="mono">{job.status}</span>
                </span>
                {job.error && <span className="badge" style={{ borderColor: "rgba(255,120,120,0.4)" }}>{job.error}</span>}
              </div>
            </>
          )}
        </section>
      )}
    </main>
  );
}