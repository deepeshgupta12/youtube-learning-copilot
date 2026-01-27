"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Badge } from "../components/ui/Badge";
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

  const [url, setUrl] = useState("");
  const [language, setLanguage] = useState("en");

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

      router.push(`/packs/${resp.study_pack_id}`);
    } catch (e: any) {
      setErr(e?.message || "Something went wrong.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="container">
      <div style={{ marginTop: 10 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <Badge tone="good">V1 Web UI</Badge>
          <span className="muted">Ingest transcript → Generate study materials → Browse in tabs</span>
        </div>

        <h1 style={{ margin: "14px 0 8px", fontSize: 44, letterSpacing: -0.6, lineHeight: 1.05 }}>
          Turn YouTube into a study pack
        </h1>

        <p className="muted" style={{ margin: 0, maxWidth: 760, lineHeight: 1.55 }}>
          Paste a YouTube link. We ingest captions, then generate a clean summary, key takeaways, chapters,
          flashcards, and a quiz you can skim in minutes.
        </p>
      </div>

      <div className="grid2" style={{ marginTop: 18 }}>
        <Card>
          <CardHeader
            title="Create study pack"
            subtitle="Use language = en unless you ingested captions in another language."
            right={<Badge>API: localhost</Badge>}
          />
          <CardBody>
            <div style={{ display: "grid", gap: 12 }}>
              <Input
                label="YouTube URL"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
              />

              <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 12 }}>
                <Input
                  label="Language"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  placeholder="en"
                />
                <div className="muted" style={{ alignSelf: "end", fontSize: 13, lineHeight: 1.5 }}>
                  If captions are missing, ingestion may fail. Try another video or set the correct language code.
                </div>
              </div>

              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <Button onClick={onCreate} disabled={!canSubmit} variant="primary">
                  {creating ? "Creating + ingesting..." : "Create study pack"}
                </Button>
                <Button
                  onClick={() => {
                    setUrl("");
                    setLanguage("en");
                    setErr(null);
                    setCreateResp(null);
                    setJob(null);
                  }}
                  variant="ghost"
                  disabled={creating}
                >
                  Clear
                </Button>
              </div>

              {err ? (
                <div className="card" style={{ padding: 12, borderColor: "rgba(255,80,80,0.28)" }}>
                  <div style={{ fontWeight: 700, marginBottom: 6 }}>Error</div>
                  <div className="muted" style={{ whiteSpace: "pre-wrap" }}>{err}</div>
                </div>
              ) : null}

              {createResp ? (
                <div className="card" style={{ padding: 12 }}>
                  <div style={{ fontWeight: 700, marginBottom: 8 }}>Created</div>
                  <div className="muted" style={{ display: "grid", gap: 4 }}>
                    <div>Study Pack ID: {createResp.study_pack_id}</div>
                    <div>Video ID: {createResp.video_id}</div>
                    <div>Job ID: {createResp.job_id}</div>
                    <div>Task ID: {createResp.task_id}</div>
                  </div>
                </div>
              ) : null}

              {job ? (
                <div className="card" style={{ padding: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                    <div>
                      <div style={{ fontWeight: 700 }}>Ingestion job</div>
                      <div className="muted" style={{ marginTop: 6 }}>
                        Status: <span style={{ color: "rgba(255,255,255,0.86)" }}>{job.status}</span>
                      </div>
                      {job.error ? <div style={{ marginTop: 6, color: "rgba(255,120,120,0.9)" }}>{job.error}</div> : null}
                    </div>
                    {createResp && job.status === "done" ? (
                      <Button onClick={() => router.push(`/packs/${createResp.study_pack_id}`)} variant="secondary">
                        Open pack
                      </Button>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="What you get" subtitle="Everything is structured so you can skim fast and retain more." />
          <CardBody>
            <div style={{ display: "grid", gap: 10 }}>
              <div className="card" style={{ padding: 12 }}>
                <div style={{ fontWeight: 700 }}>Summary</div>
                <div className="muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
                  A clean synthesis of the video — not a transcript dump.
                </div>
              </div>

              <div className="card" style={{ padding: 12 }}>
                <div style={{ fontWeight: 700 }}>Key takeaways</div>
                <div className="muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
                  High-signal bullets you can copy into notes.
                </div>
              </div>

              <div className="card" style={{ padding: 12 }}>
                <div style={{ fontWeight: 700 }}>Chapters</div>
                <div className="muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
                  A structured learning path with chapter summaries.
                </div>
              </div>

              <div className="card" style={{ padding: 12 }}>
                <div style={{ fontWeight: 700 }}>Flashcards + quiz</div>
                <div className="muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
                  Memory reinforcement + quick self-test.
                </div>
              </div>

              <div className="muted" style={{ marginTop: 6, fontSize: 13 }}>
                Tip: Keep language = en unless captions are in another language.
              </div>
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="muted" style={{ marginTop: 18, fontSize: 12 }}>
        Built for fast learning.
      </div>
    </main>
  );
}