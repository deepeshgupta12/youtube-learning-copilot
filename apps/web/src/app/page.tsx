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

function isLikelyPlaylistUrl(v: string): boolean {
  const s = (v || "").trim();
  if (!s) return false;
  // covers:
  // - https://www.youtube.com/playlist?list=...
  // - https://www.youtube.com/watch?v=...&list=...
  return s.includes("list=") || s.includes("/playlist");
}

export default function HomePage() {
  const router = useRouter();

  const [url, setUrl] = useState("");
  const [language, setLanguage] = useState("en");

  const [creating, setCreating] = useState(false);
  const [createResp, setCreateResp] = useState<StudyPackFromYoutubeResponse | null>(null);
  const [job, setJob] = useState<JobGetResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const mode = useMemo(() => (isLikelyPlaylistUrl(url) ? "playlist" : "video"), [url]);
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

      // Wait for ingest job
      const finalJob = await pollJobUntilDone(resp.job_id, { intervalMs: 1200, timeoutMs: 300000 });
      setJob(finalJob);

      if (finalJob.status === "failed") {
        setErr(finalJob.error || "Job failed.");
        return;
      }

      // ✅ Better routing:
      // - video -> open pack
      // - playlist -> open Library filtered by playlist
      if ((resp as any).playlist_id) {
        router.push(`/packs?playlist=${(resp as any).playlist_id}`);
      } else {
        router.push(`/packs/${resp.study_pack_id}`);
      }
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
          <span className="muted">
            Ingest transcript → Generate study materials → Study (Flashcards / Quiz / Chapters)
          </span>
        </div>

        <h1 style={{ margin: "14px 0 8px", fontSize: 44, letterSpacing: -0.6, lineHeight: 1.05 }}>
          Turn YouTube into a study pack
        </h1>

        <p className="muted" style={{ margin: 0, maxWidth: 760, lineHeight: 1.55 }}>
          Paste a YouTube video or playlist link. I ingest captions (or fall back to STT), then generate a clean
          summary, key takeaways, chapters, flashcards, and a quiz — so you can learn faster. ⚡
        </p>
      </div>

      <div className="grid2" style={{ marginTop: 18 }}>
        <Card>
          <CardHeader
            title={`Create study pack (${mode})`}
            subtitle={
              mode === "playlist"
                ? "Playlist ingestion creates one pack per video and ingests them via a background job."
                : "Single video ingestion creates one pack and ingests captions (or STT fallback)."
            }
            right={<Badge>API: localhost</Badge>}
          />
          <CardBody>
            <div style={{ display: "grid", gap: 12 }}>
              <Input
                label="YouTube URL"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=... or https://www.youtube.com/playlist?list=..."
              />

              <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 12 }}>
                <Input
                  label="Language"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  placeholder="en"
                />
                <div className="muted" style={{ alignSelf: "end", fontSize: 13, lineHeight: 1.5 }}>
                  Tip: keep language = <b>en</b> unless captions are in another language. If captions are missing,
                  the system can fall back to STT (yt-dlp → ffmpeg → faster-whisper). 🎧
                </div>
              </div>

              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <Button onClick={onCreate} disabled={!canSubmit} variant="primary">
                  {creating ? "Creating + ingesting..." : mode === "playlist" ? "Create playlist packs" : "Create study pack"}
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

                <Button variant="secondary" onClick={() => router.push("/packs")} disabled={creating}>
                  Open library
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
                  <div style={{ fontWeight: 800, marginBottom: 8 }}>Created ✅</div>
                  <div className="muted" style={{ display: "grid", gap: 4 }}>
                    <div>Study Pack ID: {createResp.study_pack_id}</div>

                    {(createResp as any).playlist_id ? (
                      <>
                        <div>Playlist ID: {(createResp as any).playlist_id}</div>
                        {(createResp as any).playlist_title ? <div>Playlist Title: {(createResp as any).playlist_title}</div> : null}
                        {typeof (createResp as any).playlist_count === "number" ? (
                          <div>Playlist Videos: {(createResp as any).playlist_count}</div>
                        ) : null}
                        {typeof (createResp as any).playlist_created_count === "number" ? (
                          <div>New packs created: {(createResp as any).playlist_created_count}</div>
                        ) : null}
                        {typeof (createResp as any).playlist_reused_count === "number" ? (
                          <div>Existing packs reused: {(createResp as any).playlist_reused_count}</div>
                        ) : null}
                      </>
                    ) : (
                      <div>Video ID: {createResp.video_id}</div>
                    )}

                    <div>Job ID: {createResp.job_id}</div>
                    <div>Task ID: {createResp.task_id}</div>
                  </div>

                  <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
                    {(createResp as any).playlist_id ? (
                      <Button
                        variant="secondary"
                        onClick={() => router.push(`/packs?playlist=${(createResp as any).playlist_id}`)}
                      >
                        Open playlist in library
                      </Button>
                    ) : (
                      <Button variant="secondary" onClick={() => router.push(`/packs/${createResp.study_pack_id}`)}>
                        Open pack
                      </Button>
                    )}
                  </div>
                </div>
              ) : null}

              {job ? (
                <div className="card" style={{ padding: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                    <div>
                      <div style={{ fontWeight: 800 }}>Ingestion job 🧩</div>
                      <div className="muted" style={{ marginTop: 6 }}>
                        Status: <span style={{ color: "rgba(255,255,255,0.86)" }}>{job.status}</span>
                      </div>
                      {job.error ? (
                        <div style={{ marginTop: 6, color: "rgba(255,120,120,0.9)" }}>{job.error}</div>
                      ) : null}
                    </div>

                    {createResp && job.status === "done" ? (
                      (createResp as any).playlist_id ? (
                        <Button onClick={() => router.push(`/packs?playlist=${(createResp as any).playlist_id}`)} variant="secondary">
                          Open playlist
                        </Button>
                      ) : (
                        <Button onClick={() => router.push(`/packs/${createResp.study_pack_id}`)} variant="secondary">
                          Open pack
                        </Button>
                      )
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="What you get" subtitle="Everything is structured so you can skim fast and retain more. 🧠" />
          <CardBody>
            <div style={{ display: "grid", gap: 10 }}>
              <div className="card" style={{ padding: 12 }}>
                <div style={{ fontWeight: 800 }}>Summary</div>
                <div className="muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
                  A clean synthesis of the video — not a transcript dump.
                </div>
              </div>

              <div className="card" style={{ padding: 12 }}>
                <div style={{ fontWeight: 800 }}>Key takeaways</div>
                <div className="muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
                  High-signal bullets you can copy into notes.
                </div>
              </div>

              <div className="card" style={{ padding: 12 }}>
                <div style={{ fontWeight: 800 }}>Chapters</div>
                <div className="muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
                  A structured learning path with chapter summaries.
                </div>
              </div>

              <div className="card" style={{ padding: 12 }}>
                <div style={{ fontWeight: 800 }}>Flashcards + quiz</div>
                <div className="muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
                  Memory reinforcement + quick self-test (with progress tracking).
                </div>
              </div>

              <div className="muted" style={{ marginTop: 6, fontSize: 13 }}>
                Playlist tip: when you paste a playlist, I’ll create one pack per video and you can study them from the Library. 📚
              </div>
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="muted" style={{ marginTop: 18, fontSize: 12 }}>
        Built for fast learning — locally. 🚀
      </div>
    </main>
  );
}