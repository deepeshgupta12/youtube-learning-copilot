"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { getJob, pollJobUntilDone, type JobGetResponse } from "../../../lib/api";

function toInt(v: unknown): number | null {
  const s = typeof v === "string" ? v : Array.isArray(v) ? v[0] : "";
  const n = Number.parseInt(String(s), 10);
  return Number.isFinite(n) ? n : null;
}

function safeJsonParse(s: string): any {
  try {
    return s ? JSON.parse(s) : null;
  } catch {
    return { _parse_error: "payload_json is not valid JSON", raw: s };
  }
}

export default function JobPage() {
  const params = useParams();
  const jobId = useMemo(() => toInt((params as any)?.id), [params]);

  const [job, setJob] = useState<JobGetResponse | null>(null);
  const [payload, setPayload] = useState<any>(null);

  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function loadOnce() {
    if (!jobId) return;
    const j = await getJob(jobId);
    setJob(j);
    setPayload(safeJsonParse(j.payload_json || ""));
  }

  async function loadAndPollIfNeeded() {
    if (!jobId) return;
    setErr(null);
    setLoading(true);
    try {
      const j = await getJob(jobId);
      setJob(j);
      setPayload(safeJsonParse(j.payload_json || ""));

      if (j.status !== "done" && j.status !== "failed") {
        setPolling(true);
        const finalJob = await pollJobUntilDone(jobId, { intervalMs: 1200, timeoutMs: 240_000 });
        setJob(finalJob);
        setPayload(safeJsonParse(finalJob.payload_json || ""));
      }
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
      setPolling(false);
    }
  }

  const progress = payload?.progress || null;
  const stage = progress?.stage || "-";
  const done = typeof progress?.done === "number" ? progress.done : null;
  const total = typeof progress?.total === "number" ? progress.total : null;

  if (!jobId) {
    return <div className="p-6 text-white/80">Invalid job id.</div>;
  }

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-10">
      <div className="flex items-center justify-between gap-4">
        <Link href="/packs" className="text-sm text-white/70 hover:text-white">
          ← Back to library
        </Link>

        <div className="flex gap-2">
          <button
            onClick={loadOnce}
            disabled={loading || polling}
            className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/85 hover:bg-white/8 disabled:opacity-50"
          >
            Refresh
          </button>
          <button
            onClick={loadAndPollIfNeeded}
            disabled={loading || polling}
            className="rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-xs text-white hover:bg-white/15 disabled:opacity-50"
          >
            Poll until done
          </button>
        </div>
      </div>

      <div className="mt-6">
        <h1 className="text-3xl font-semibold text-white">Job #{jobId}</h1>
        <p className="mt-2 text-sm text-white/60">
          Track ingestion / playlist / materials generation progress.
        </p>
      </div>

      {err && (
        <div className="mt-4 rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-100 whitespace-pre-wrap">
          {err}
        </div>
      )}

      <div className="mt-6 grid gap-4">
        <section className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_8px_40px_rgba(0,0,0,0.35)]">
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-white/10">
            <div className="text-sm font-semibold text-white/90">Status</div>
            <div className="text-xs text-white/60">{job ? `Type: ${job.job_type}` : ""}</div>
          </div>
          <div className="p-5">
            {!job ? (
              <div className="text-sm text-white/60">Loading…</div>
            ) : (
              <div className="grid gap-2">
                <div className="text-sm text-white/85">
                  Status: <span className="font-semibold text-white">{job.status}</span>
                </div>
                <div className="text-sm text-white/85">
                  Stage: <span className="font-semibold text-white">{stage}</span>
                  {done !== null && total !== null ? (
                    <span className="text-white/60">{" "}({done}/{total})</span>
                  ) : null}
                </div>
                <div className="text-sm text-white/85">
                  Error: <span className="text-white/70">{job.error || "-"}</span>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_8px_40px_rgba(0,0,0,0.35)]">
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-white/10">
            <div className="text-sm font-semibold text-white/90">Payload</div>
            <div className="text-xs text-white/60">payload_json parsed</div>
          </div>
          <div className="p-5">
            <pre className="whitespace-pre-wrap text-xs text-white/70 leading-6">
              {JSON.stringify(payload, null, 2)}
            </pre>
          </div>
        </section>
      </div>
    </main>
  );
}