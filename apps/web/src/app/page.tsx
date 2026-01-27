"use client";

// apps/web/src/app/page.tsx
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
        // Auto-open the pack page as soon as ingestion finishes.
        router.push(`/packs/${resp.study_pack_id}`);
      }
    } catch (e: any) {
      setErr(e?.message || "Something went wrong.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main style={{ padding: 24, maxWidth: 860, margin: "0 auto" }}>
      <h1 style={{ marginBottom: 6 }}>YouTube Learning Copilot</h1>
      <p style={{ marginTop: 0, opacity: 0.75 }}>
        Create a study pack from a YouTube video, ingest transcript, then generate study materials.
      </p>

      <div style={{ display: "grid", gap: 12, marginTop: 18 }}>
        <label style={{ display: "grid", gap: 6 }}>
          <span>YouTube URL</span>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
            style={{ padding: 10, borderRadius: 8, border: "1px solid rgba(0,0,0,0.15)" }}
          />
        </label>

        <label style={{ display: "grid", gap: 6, maxWidth: 220 }}>
          <span>Language</span>
          <input
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            placeholder="en"
            style={{ padding: 10, borderRadius: 8, border: "1px solid rgba(0,0,0,0.15)" }}
          />
        </label>

        <button
          onClick={onCreate}
          disabled={!canSubmit}
          style={{
            padding: "10px 14px",
            borderRadius: 10,
            border: "1px solid rgba(0,0,0,0.2)",
            cursor: canSubmit ? "pointer" : "not-allowed",
            width: 260,
          }}
        >
          {creating ? "Creating + Ingesting..." : "Create Study Pack"}
        </button>

        {err && (
          <div style={{ padding: 12, borderRadius: 10, border: "1px solid rgba(255,0,0,0.3)" }}>
            <strong>Error:</strong> {err}
          </div>
        )}

        {createResp && (
          <div style={{ padding: 12, borderRadius: 10, border: "1px solid rgba(0,0,0,0.12)" }}>
            <div>
              <strong>Study Pack ID:</strong> {createResp.study_pack_id}
            </div>
            <div>
              <strong>Video ID:</strong> {createResp.video_id}
            </div>
            <div>
              <strong>Job ID:</strong> {createResp.job_id}
            </div>
            <div>
              <strong>Task ID:</strong> {createResp.task_id}
            </div>
          </div>
        )}

        {job && (
          <div style={{ padding: 12, borderRadius: 10, border: "1px solid rgba(0,0,0,0.12)" }}>
            <div>
              <strong>Job Status:</strong> {job.status}
            </div>
            {job.error && (
              <div>
                <strong>Job Error:</strong> {job.error}
              </div>
            )}

            {/* fallback link (in case you want manual control) */}
            {createResp && job.status === "done" && (
              <button
                onClick={() => router.push(`/packs/${createResp.study_pack_id}`)}
                style={{
                  marginTop: 10,
                  padding: "10px 14px",
                  borderRadius: 10,
                  border: "1px solid rgba(0,0,0,0.2)",
                  cursor: "pointer",
                  width: 160,
                }}
              >
                Open Pack
              </button>
            )}
          </div>
        )}
      </div>
    </main>
  );
}