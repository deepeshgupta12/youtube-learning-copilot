"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
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

export default function PacksLibraryPage() {
  const router = useRouter();

  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [packs, setPacks] = useState<StudyPackListItem[]>([]);

  const canSearch = useMemo(() => !loading, [loading]);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const resp = await listStudyPacks({ q: q.trim() || undefined, limit: 25, offset: 0 });
      setPacks(resp.packs || []);
    } catch (e: any) {
      setErr(e?.message || "Failed to load library");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="container">
      <div style={{ marginTop: 10, display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <Badge tone="good">Library</Badge>
            <span className="muted">Recent study packs saved locally</span>
          </div>
          <h1 style={{ margin: "14px 0 8px", fontSize: 40, letterSpacing: -0.6, lineHeight: 1.05 }}>
            Your Study Packs
          </h1>
          <p className="muted" style={{ margin: 0, maxWidth: 760, lineHeight: 1.55 }}>
            Search by title, URL, or playlist. Open any pack to generate materials and study.
          </p>
        </div>

        <div style={{ alignSelf: "end", display: "flex", gap: 10 }}>
          <Button variant="secondary" onClick={() => router.push("/")}>
            Create new
          </Button>
          <Button variant="ghost" onClick={load} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh"}
          </Button>
        </div>
      </div>

      <div style={{ marginTop: 18 }}>
        <Card>
          <CardHeader
            title="Search"
            subtitle="Type any keyword (title / url / playlist)."
            right={<Badge>Local</Badge>}
          />
          <CardBody>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end" }}>
              <div style={{ flex: "1 1 520px" }}>
                <Input
                  label="Query"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="e.g. brain, playlist, youtube.com/watch?v=..."
                />
              </div>
              <Button variant="primary" onClick={load} disabled={!canSearch}>
                Search
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setQ("");
                  setTimeout(load, 0);
                }}
                disabled={loading}
              >
                Clear
              </Button>
            </div>

            {err ? (
              <div className="card" style={{ padding: 12, marginTop: 12, borderColor: "rgba(255,80,80,0.28)" }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>Error</div>
                <div className="muted" style={{ whiteSpace: "pre-wrap" }}>{err}</div>
              </div>
            ) : null}
          </CardBody>
        </Card>
      </div>

      <div style={{ marginTop: 14, display: "grid", gap: 10 }}>
        {packs.length === 0 ? (
          <div className="muted" style={{ padding: 14 }}>
            No packs found. Create one from the home page.
          </div>
        ) : null}

        {packs.map((p) => (
          <div
            key={p.id}
            className="card"
            style={{ padding: 12, cursor: "pointer" }}
            onClick={() => router.push(`/packs/${p.id}`)}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div style={{ minWidth: 320 }}>
                <div style={{ fontWeight: 800, fontSize: 16 }}>
                  {p.title || "(untitled)"}
                </div>

                <div className="muted" style={{ marginTop: 6, fontSize: 13, lineHeight: 1.4 }}>
                  {niceUrl(p.source_url)}
                </div>

                {p.playlist_id ? (
                  <div className="muted" style={{ marginTop: 6, fontSize: 13 }}>
                    Playlist:{" "}
                    <span style={{ color: "rgba(255,255,255,0.86)" }}>
                      {p.playlist_title || p.playlist_id}
                    </span>
                    {p.playlist_index ? ` · #${p.playlist_index}` : ""}
                  </div>
                ) : null}

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

      <div className="muted" style={{ marginTop: 18, fontSize: 12 }}>
        Tip: playlist packs are grouped by playlist id and index.
      </div>
    </main>
  );
}