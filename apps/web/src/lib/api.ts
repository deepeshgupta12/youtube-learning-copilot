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

  // video
  video_id?: string | null;

  // playlist (optional)
  playlist_id?: string | null;
  playlist_title?: string | null;
  playlist_count?: number | null;
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

    playlist_id?: string | null;
    playlist_title?: string | null;
    playlist_index?: number | null;
  };
};

export type FlashcardProgressItem = {
  card_index: number;
  status: "known" | "review_later" | null;
  seen_count: number;
  known_count: number;
  review_later_count: number;
  last_seen_at: string | null;
};

export type FlashcardProgressResponse = {
  ok: boolean;
  study_pack_id: number;
  total_cards: number;
  seen_cards: number;
  known_cards: number;
  review_later_cards: number;
  items: FlashcardProgressItem[];
};

export type FlashcardMarkRequest = {
  card_index: number;
  action: "known" | "review_later" | "reset" | "seen";
};

export type QuizProgressItem = {
  question_index: number;
  status: "correct" | "wrong" | null;
  seen_count: number;
  correct_count: number;
  wrong_count: number;
  last_seen_at: string | null;
};

export type QuizProgressResponse = {
  ok: boolean;
  study_pack_id: number;
  total_questions: number;
  seen_questions: number;
  correct_questions: number;
  wrong_questions: number;
  items: QuizProgressItem[];
};

export type QuizMarkRequest = {
  question_index: number;
  action: "correct" | "wrong" | "reset" | "seen";
};

export type ChapterProgressItem = {
  chapter_index: number;
  status: "in_progress" | "completed" | null;
  opened_count: number;
  completed_count: number;
  last_opened_at: string | null;
  last_completed_at: string | null;
};

export type ChapterProgressResponse = {
  ok: boolean;
  study_pack_id: number;
  total_chapters: number;
  opened_chapters: number;
  completed_chapters: number;
  resume_chapter_index: number;
  items: ChapterProgressItem[];
};

export type ChapterMarkRequest = {
  chapter_index: number;
  action: "open" | "complete" | "reset";
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

export type TranscriptGetResponse = {
  ok: boolean;
  study_pack_id: number;
  status: string;
  source_id: string | null;
  language: string | null;
  transcript_text: string | null;
  transcript_json: string | null;
  updated_at: string | null;
};

export type TranscriptChunkItem = {
  id: number;
  idx: number;
  start_sec: number;
  end_sec: number;
  text: string;
  created_at: string | null;
  updated_at: string | null;
};

export type TranscriptChunksResponse = {
  ok: boolean;
  study_pack_id: number;
  total: number;
  limit: number;
  offset: number;
  items: TranscriptChunkItem[];
};

/** V1 Minimal Library types */
export type StudyPackListItem = {
  id: number;
  title: string | null;
  source_type: string;
  source_url: string;
  status: string;
  source_id: string | null;
  language: string | null;

  playlist_id: string | null;
  playlist_title: string | null;
  playlist_index: number | null;

  error: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type StudyPackListResponse = {
  ok: boolean;
  total: number;
  limit: number;
  offset: number;
  packs: StudyPackListItem[];
};

/** -----------------------
 * V2.4 — KB Ask (Grounded Q&A)
 * ---------------------- */
export type KBAskCitation = {
  chunk_id: number;
  idx: number;
  start_sec: number;
  end_sec: number;
  text: string;
  score: number;
  url?: string; // timestamped citation URL (YouTube)
};

export type KBAskStudyPackInfo = {
  id: number;
  title: string | null;
  source_url: string;
  source_type: string;
  playlist_id: string | null;
  playlist_index: number | null;
};

export type KBAskRequest = {
  question: string;
  model?: string | null;
  limit?: number | null;
  hybrid?: boolean | null;
  min_best_score?: number | null;

  // V2.4: controls retrieval embedding model
  embed_model?: string | null;
};

export type KBAskResponse = {
  ok: boolean;
  study_pack_id: number;
  refused: boolean;
  answer: string;
  model: string;

  // V2.4 additions
  embed_model?: string | null;
  study_pack?: KBAskStudyPackInfo;

  citations: KBAskCitation[];
  retrieval: any;
};

function baseUrl(): string {
  const v = process.env.NEXT_PUBLIC_API_BASE_URL;
  return v && v.trim() ? v.trim().replace(/\/+$/, "") : "http://localhost:8000";
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${baseUrl()}${path.startsWith("/") ? path : `/${path}`}`;

  const method = (init?.method || "GET").toUpperCase();
  const hasBody = init?.body !== undefined && init?.body !== null;

  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
  };

  if (hasBody) {
    if (!headers["Content-Type"]) headers["Content-Type"] = "application/json";
  }

  const res = await fetch(url, {
    ...init,
    method,
    headers,
    cache: "no-store",
  });

  const raw = await res.text();

  let data: any = null;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    data = { ok: false, error: raw || `Non-JSON response from ${url}` };
  }

  if (!res.ok) {
    const msg = (data && (data.detail || data.error)) || `HTTP ${res.status} calling ${url}`;
    throw new Error(msg);
  }

  return data as T;
}

export async function createStudyPackFromYoutube(
  url: string,
  language?: string | null
): Promise<StudyPackFromYoutubeResponse> {
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
  return apiFetch<GenerateMaterialsResponse>(`/study-packs/${studyPackId}/generate`, {
    method: "POST",
  });
}

export async function getMaterials(studyPackId: number): Promise<StudyMaterialsResponse> {
  return apiFetch<StudyMaterialsResponse>(`/study-packs/${studyPackId}/materials`, { method: "GET" });
}

/** V1 Minimal Library call */
export async function listStudyPacks(params?: {
  q?: string;
  status?: string;
  source_type?: string;
  limit?: number;
  offset?: number;
}): Promise<StudyPackListResponse> {
  const qs = new URLSearchParams();
  if (params?.q) qs.set("q", params.q);
  if (params?.status) qs.set("status", params.status);
  if (params?.source_type) qs.set("source_type", params.source_type);
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));

  const path = `/study-packs${qs.toString() ? `?${qs.toString()}` : ""}`;
  return apiFetch<StudyPackListResponse>(path, { method: "GET" });
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

export async function getFlashcardProgress(studyPackId: number): Promise<FlashcardProgressResponse> {
  return apiFetch<FlashcardProgressResponse>(`/study-packs/${studyPackId}/flashcards/progress`, {
    method: "GET",
  });
}

export async function markFlashcardProgress(
  studyPackId: number,
  req: FlashcardMarkRequest
): Promise<FlashcardProgressResponse> {
  return apiFetch<FlashcardProgressResponse>(`/study-packs/${studyPackId}/flashcards/progress`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getQuizProgress(studyPackId: number): Promise<QuizProgressResponse> {
  return apiFetch<QuizProgressResponse>(`/study-packs/${studyPackId}/quiz/progress`, {
    method: "GET",
  });
}

export async function markQuizProgress(
  studyPackId: number,
  req: QuizMarkRequest
): Promise<QuizProgressResponse> {
  return apiFetch<QuizProgressResponse>(`/study-packs/${studyPackId}/quiz/progress`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getChapterProgress(studyPackId: number): Promise<ChapterProgressResponse> {
  return apiFetch<ChapterProgressResponse>(`/study-packs/${studyPackId}/chapters/progress`, {
    method: "GET",
  });
}

export async function markChapterProgress(
  studyPackId: number,
  req: ChapterMarkRequest
): Promise<ChapterProgressResponse> {
  return apiFetch<ChapterProgressResponse>(`/study-packs/${studyPackId}/chapters/progress`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getTranscript(studyPackId: number): Promise<TranscriptGetResponse> {
  return apiFetch<TranscriptGetResponse>(`/study-packs/${studyPackId}/transcript`, { method: "GET" });
}

export async function listTranscriptChunks(args: {
  studyPackId: number;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<TranscriptChunksResponse> {
  const qs = new URLSearchParams();
  if (args.q) qs.set("q", args.q);
  qs.set("limit", String(args.limit ?? 50));
  qs.set("offset", String(args.offset ?? 0));
  return apiFetch<TranscriptChunksResponse>(
    `/study-packs/${args.studyPackId}/transcript/chunks?${qs.toString()}`,
    { method: "GET" }
  );
}

/** V2.4 — KB Ask */
export async function kbAsk(studyPackId: number, req: KBAskRequest): Promise<KBAskResponse> {
  return apiFetch<KBAskResponse>(`/study-packs/${studyPackId}/kb/ask`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}