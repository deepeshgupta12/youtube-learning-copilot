"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { listStudyPacks, type StudyPackListItem } from "../../lib/api";

function niceUrl(u: string): string {
  try {
    const url = new URL(u);
    return `${url.hostname}${url.pathname}${url.search ? url.search : ""}`;
  } catch {
    return u;
  }
}

function isDefined<T>(v: T | null | undefined): v is T {
  return v !== null && v !== undefined;
}

export default function PacksLibraryPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // If opened with /packs?playlist=PLxxxx, auto-filter the library
  const playlistParam = searchParams.get("playlist")?.trim() || "";

  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [packs, setPacks] = useState<StudyPackListItem[]>([]);
  const [expandedPlaylists, setExpandedPlaylists] = useState<Record<string, boolean>>({});

  const canSearch = useMemo(() => !loading, [loading]);

  async function load(nextQ?: string) {
    setLoading(true);
    setErr(null);
    try {
      const query = (typeof nextQ === "string" ? nextQ : q).trim();

      // We keep compatibility with current api.ts types,
      // but we DO support the backend playlist_id filter via "as any".
      const resp = await listStudyPacks({
        q: query || undefined,
        limit: 50,
        offset: 0,
        ...(playlistParam ? ({ playlist_id: playlistParam } as any) : {}),
      } as any);

      const rows = (resp.packs || []) as StudyPackListItem[];
      setPacks(rows);

      // auto-expand the playlist section if we came via ?playlist=
      if (playlistParam) {
        setExpandedPlaylists((prev) => ({ ...prev, [playlistParam]: true }));
      }
    } catch (e: any) {
      setErr(e?.message || "Failed to load library");
    } finally {
      setLoading(false);
    }
  }

  // initial load + playlist param binding
  useEffect(() => {
    if (playlistParam) {
      setQ(playlistParam);
      load(playlistParam);
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playlistParam]);

  // Group packs by playlist_id (and keep non-playlist as a separate list)
  const grouped = useMemo(() => {
    const byPlaylist: Record<string, StudyPackListItem[]> = {};
    const singles: StudyPackListItem[] = [];

    for (const p of packs) {
      if (p.playlist_id) {
        if (!byPlaylist[p.playlist_id]) byPlaylist[p.playlist_id] = [];
        byPlaylist[p.playlist_id].push(p);
      } else {
        singles.push(p);
      }
    }

    // sort each playlist by playlist_index (stable)
    for (const pid of Object.keys(byPlaylist)) {
      byPlaylist[pid].sort((a, b) => {
        const ai = isDefined(a.playlist_index) ? a.playlist_index : 1e9;
        const bi = isDefined(b.playlist_index) ? b.playlist_index : 1e9;
        return ai - bi;
      });
    }

    return { byPlaylist, singles };
  }, [packs]);

  function togglePlaylist(pid: string) {
    setExpandedPlaylists((prev) => ({ ...prev, [pid]: !prev[pid] }));
  }

  return (
    <main className="container">
      <div style={{ marginTop: 10, display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <Badge tone="good">Library</Badge>
            <span className="muted">
              Recent study packs saved locally {playlistParam ? "· playlist view" : ""}
            </span>
          </div>

          <h1 style={{ margin: "14px 0 8px", fontSize: 40, letterSpacing: -0.6, lineHeight: 1.05 }}>
            Your Study Packs 📚
          </h1>

          <p className="muted" style={{ margin: 0, maxWidth: 820, lineHeight: 1.55 }}>
            Search by title, URL, video id, or playlist. Open any pack to generate materials and study.
            {playlistParam ? (
              <>
                {" "}
                <span style={{ color: "rgba(255,255,255,0.86)" }}>
                  (Filtered by playlist: {playlistParam})
                </span>
              </>
            ) : null}
          </p>
        </div>

        <div style={{ alignSelf: "end", display: "flex", gap: 10 }}>
          <Button variant="secondary" onClick={() => router.push("/")}>
            Create new
          </Button>

          <Button
            variant="ghost"
            onClick={() => load()}
            disabled={loading}
          >
            {loading ? "Refreshing..." : "Refresh"}
          </Button>
        </div>
      </div>

      <div style={{ marginTop: 18 }}>
        <Card>
          <CardHeader
            title="Search"
            subtitle="Type any keyword (title / url / playlist id / video id)."
            right={<Badge>Local</Badge>}
          />
          <CardBody>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end" }}>
              <div style={{ flex: "1 1 520px" }}>
                <Input
                  label="Query"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="e.g. brain, playlist id, youtube.com/watch?v=..."
                />
              </div>

              <Button variant="primary" onClick={() => load()} disabled={!canSearch}>
                Search
              </Button>

              <Button
                variant="ghost"
                onClick={() => {
                  setQ("");
                  // Clear playlist param view by routing to /packs without query
                  if (playlistParam) router.push("/packs");
                  setTimeout(() => load(""), 0);
                }}
                disabled={loading}
              >
                Clear
              </Button>
            </div>

            {err ? (
              <div className="card" style={{ padding: 12, marginTop: 12, borderColor: "rgba(255,80,80,0.28)" }}>
                <div style={{ fontWeight: 800, marginBottom: 6 }}>Error</div>
                <div className="muted" style={{ whiteSpace: "pre-wrap" }}>{err}</div>
              </div>
            ) : null}
          </CardBody>
        </Card>
      </div>

      <div style={{ marginTop: 14, display: "grid", gap: 12 }}>
        {packs.length === 0 ? (
          <div className="muted" style={{ padding: 14 }}>
            No packs found. Create one from the home page.
          </div>
        ) : null}

        {/* Playlist groups */}
        {Object.keys(grouped.byPlaylist).length > 0 ? (
          <div style={{ display: "grid", gap: 10 }}>
            {Object.entries(grouped.byPlaylist).map(([pid, items]) => {
              const title = items.find((x) => x.playlist_title)?.playlist_title || pid;
              const expanded = expandedPlaylists[pid] ?? false;

              const ingested = items.filter((x) => x.status === "ingested").length;
              const failed = items.filter((x) => x.status === "failed").length;

              return (
                <div key={pid} className="card" style={{ padding: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                    <div style={{ minWidth: 320 }}>
                      <div style={{ fontWeight: 900, fontSize: 16 }}>
                        🎬 Playlist: {title}
                      </div>
                      <div className="muted" style={{ marginTop: 6, fontSize: 13 }}>
                        Playlist ID: <span style={{ color: "rgba(255,255,255,0.86)" }}>{pid}</span>
                      </div>
                      <div className="muted" style={{ marginTop: 6, fontSize: 13 }}>
                        Videos: <span style={{ color: "rgba(255,255,255,0.86)" }}>{items.length}</span> ·
                        Ingested: <span style={{ color: "rgba(255,255,255,0.86)" }}>{ingested}</span> ·
                        Failed: <span style={{ color: failed ? "rgba(255,120,120,0.9)" : "rgba(255,255,255,0.86)" }}>{failed}</span>
                      </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          // Open the first pack in this playlist
                          const first = items[0];
                          router.push(`/packs/${first.id}`);
                        }}
                      >
                        Open first pack
                      </Button>

                      <Button variant="ghost" onClick={() => togglePlaylist(pid)}>
                        {expanded ? "Hide videos" : "Show videos"}
                      </Button>
                    </div>
                  </div>

                  {expanded ? (
                    <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
                      {items.map((p) => (
                        <div
                          key={p.id}
                          className="card"
                          style={{ padding: 12, cursor: "pointer" }}
                          onClick={() => router.push(`/packs/${p.id}`)}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                            <div style={{ minWidth: 320 }}>
                              <div style={{ fontWeight: 800, fontSize: 15 }}>
                                {(isDefined(p.playlist_index) ? `#${p.playlist_index} · ` : "")}
                                {p.title || "(untitled)"}
                              </div>

                              <div className="muted" style={{ marginTop: 6, fontSize: 13, lineHeight: 1.4 }}>
                                {niceUrl(p.source_url)}
                              </div>

                              {p.error ? (
                                <div style={{ marginTop: 8, color: "rgba(255,120,120,0.9)", fontSize: 13 }}>
                                  {p.error}
                                </div>
                              ) : null}
                            </div>

                            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                              <Badge tone={p.status === "ingested" ? "good" : p.status === "failed" ? "bad" : "neutral"}>
                                {p.status}
                              </Badge>
                              <Button
                                variant="secondary"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  router.push(`/packs/${p.id}`);
                                }}
                              >
                                Open
                              </Button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : null}

        {/* Non-playlist packs */}
        {grouped.singles.length > 0 ? (
          <div style={{ display: "grid", gap: 10 }}>
            <div className="muted" style={{ padding: "0 4px", fontSize: 13 }}>
              📌 Single videos
            </div>

            {grouped.singles.map((p) => (
              <div
                key={p.id}
                className="card"
                style={{ padding: 12, cursor: "pointer" }}
                onClick={() => router.push(`/packs/${p.id}`)}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                  <div style={{ minWidth: 320 }}>
                    <div style={{ fontWeight: 900, fontSize: 16 }}>
                      {p.title || "(untitled)"}
                    </div>

                    <div className="muted" style={{ marginTop: 6, fontSize: 13, lineHeight: 1.4 }}>
                      {niceUrl(p.source_url)}
                    </div>

                    {p.error ? (
                      <div style={{ marginTop: 8, color: "rgba(255,120,120,0.9)", fontSize: 13 }}>
                        {p.error}
                      </div>
                    ) : null}
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <Badge tone={p.status === "ingested" ? "good" : p.status === "failed" ? "bad" : "neutral"}>
                      {p.status}
                    </Badge>
                    <Button
                      variant="secondary"
                      onClick={(e) => {
                        e.stopPropagation();
                        router.push(`/packs/${p.id}`);
                      }}
                    >
                      Open
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <div className="muted" style={{ marginTop: 18, fontSize: 12 }}>
        Tip: playlists are grouped by playlist id and ordered by playlist index. ✅
      </div>
    </main>
  );
}