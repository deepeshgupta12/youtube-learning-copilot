// apps/web/src/lib/api.ts
export type JobStatus = "queued" | "running" | "done" | "failed";

export type JobGetResponse = {
  ok: boolean;
  job_id: number;
  job_type: string;
  status: JobStatus | string;
  error: string | null;
  payload_json: string;
};

export type StudyPackFromYoutubeResponse = {
  ok: boolean;
  study_pack_id: number;
  job_id: number;
  task_id: string;
  video_id: string;
};

export type StudyPackResponse = {
  ok: boolean;
  study_pack: {
    id: number;
    source_type: string;
    source_url: string;
    title: string | null;
    status: string;
    source_id: string | null;
    language: string | null;
    meta_json: string | null;
    transcript_json: string | null;
    transcript_text: string | null;
    error: string | null;
    created_at: string | null;
    updated_at: string | null;
  };
};

export type StudyMaterialRow = {
  id: number;
  kind: "summary" | "key_takeaways" | "chapters" | "flashcards" | "quiz" | string;
  status: string;
  content_json: any; // backend returns dict
  content_text: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type StudyMaterialsResponse = {
  ok: boolean;
  study_pack_id: number;
  materials: StudyMaterialRow[];
};

export type GenerateMaterialsResponse = {
  ok: boolean;
  study_pack_id: number;
  job_id: number;
  task_id: string;
};

function baseUrl(): string {
  const v = process.env.NEXT_PUBLIC_API_BASE_URL;
  return v && v.trim() ? v.trim().replace(/\/+$/, "") : "http://localhost:8000";
}

type Json = Record<string, unknown> | unknown[] | string | number | boolean | null;

function isJsonBody(body: any): boolean {
  return typeof body === "string" || typeof body === "object";
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${baseUrl()}${path.startsWith("/") ? path : `/${path}`}`;

  const method = (init?.method || "GET").toUpperCase();
  const hasBody = init?.body !== undefined && init?.body !== null;

  // Only send Content-Type when we have a JSON body.
  // This avoids unnecessary CORS preflight for GET and body-less POST.
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
  };

  if (hasBody) {
    // If caller passes string body, assume it's JSON string unless they overrode.
    if (!headers["Content-Type"]) headers["Content-Type"] = "application/json";
  }

  const res = await fetch(url, {
    ...init,
    method,
    headers,
    cache: "no-store",
  });

  // Some endpoints might return empty body (204 etc.)
  const raw = await res.text();

  let data: any = null;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    // Non-JSON response fallback
    data = { ok: false, error: raw || `Non-JSON response from ${url}` };
  }

  if (!res.ok) {
    const msg =
      (data && (data.detail || data.error)) ||
      `HTTP ${res.status} calling ${url}`;
    throw new Error(msg);
  }

  return data as T;
}

export async function createStudyPackFromYoutube(
  url: string,
  language?: string | null
): Promise<StudyPackFromYoutubeResponse> {
  // This WILL still trigger preflight because it's JSON POST (normal).
  // Backend must allow OPTIONS via CORS middleware.
  return apiFetch<StudyPackFromYoutubeResponse>("/study-packs/from-youtube", {
    method: "POST",
    body: JSON.stringify({ url, language: language || null }),
  });
}

export async function getJob(jobId: number): Promise<JobGetResponse> {
  return apiFetch<JobGetResponse>(`/jobs/${jobId}`, { method: "GET" });
}

export async function getStudyPack(studyPackId: number): Promise<StudyPackResponse> {
  return apiFetch<StudyPackResponse>(`/study-packs/${studyPackId}`, { method: "GET" });
}

export async function generateMaterials(studyPackId: number): Promise<GenerateMaterialsResponse> {
  // Keep POST with no body => no Content-Type header => avoids preflight
  return apiFetch<GenerateMaterialsResponse>(`/study-packs/${studyPackId}/generate`, {
    method: "POST",
  });
}

export async function getMaterials(studyPackId: number): Promise<StudyMaterialsResponse> {
  return apiFetch<StudyMaterialsResponse>(`/study-packs/${studyPackId}/materials`, {
    method: "GET",
  });
}

/**
 * Poll job until terminal state or timeout.
 * Returns last job payload.
 */
export async function pollJobUntilDone(
  jobId: number,
  opts?: { intervalMs?: number; timeoutMs?: number }
): Promise<JobGetResponse> {
  const intervalMs = opts?.intervalMs ?? 1200;
  const timeoutMs = opts?.timeoutMs ?? 120000;

  const start = Date.now();
  while (true) {
    const j = await getJob(jobId);
    const status = j.status;

    if (status === "done" || status === "failed") return j;

    if (Date.now() - start > timeoutMs) {
      throw new Error(`Timed out waiting for job ${jobId} to finish (last status: ${status})`);
    }

    await new Promise((r) => setTimeout(r, intervalMs));
  }
}