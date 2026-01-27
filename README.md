# YouTube Learning Copilot

Turn any YouTube video into a **structured study pack**: ingest the transcript, then generate a **summary, key takeaways, chapters, flashcards, and a quiz**. This repo is intentionally simple and “local-first” so you can iterate quickly on both the **learning output quality** and the **UI experience**.

---

## Problem statement

When you learn from YouTube, your “study flow” is usually scattered:

- you watch long videos,
- you take notes manually,
- you forget context a week later,
- and there’s no clean way to review what mattered.

**YouTube Learning Copilot** solves this by converting a video transcript into a study pack with reusable learning materials. Instead of the transcript dump, you get **digestible learning artifacts** that are easy to read, revise, and revisit.

---

## What we’ve built so far (current scope / V0)

This is what is implemented and working end-to-end right now:

### 1) Study pack creation + transcript ingestion (async)
You provide a YouTube URL and language, and the backend starts an ingestion job. When ingestion completes, the UI automatically routes you to the study pack page.

### 2) Study material generation (async)
From the ingested transcript, the backend generates:

- **Summary**
- **Key takeaways**
- **Chapters**
- **Flashcards**
- **Quiz (MCQ)**

This runs via a Celery worker and stores results in Postgres.

### 3) Provider support: OpenAI + fallback heuristics
Study material generation supports:

- **OpenAI provider** (LLM-generated, synthesized outputs)
- **Heuristic fallback** (deterministic, non-LLM generator)

We also added **debug metadata (`_meta`)** stored in `content_json` so we can prove which provider ran and why (e.g., OpenAI failures, timeouts, model used, transcript length).

### 4) Web UI (Next.js) with “glass UI” direction
You currently have:

- A landing page for URL + language input
- A pack page with:
  - pack info
  - generation actions (refresh / generate)
  - materials rendered by kind

The UI was recently improved toward a glassmorphism style and is now stable again.

---

## Tech stack

### Backend
- **FastAPI** (API server)
- **Celery** (async job execution)
- **Postgres** (persistence)
- **SQLAlchemy** (ORM)
- **OpenAI** (optional provider for study material generation)

### Frontend
- **Next.js (App Router)** for the web UI
- Tailwind is available via `@import "tailwindcss"` (styling currently mixes inline + CSS)

---

## High-level architecture

A simple async pipeline with two phases:

1) **Ingest**
- create study pack → queue ingestion task → store transcript in DB → mark pack as `ingested`

2) **Generate**
- create “generate materials” job → queue generation task → generate + validate payload → upsert 5 material rows

---

## Key API endpoints

### Create a study pack from YouTube
```bash
curl -s -X POST "http://localhost:8000/study-packs/from-youtube"   -H "Content-Type: application/json"   -d '{"url":"https://www.youtube.com/watch?v=VIDEO_ID","language":"en"}' | python -m json.tool
```

### Get a job status
```bash
curl -s "http://localhost:8000/jobs/<job_id>" | python -m json.tool
```

### Generate study materials for a pack
```bash
curl -s -X POST "http://localhost:8000/study-packs/<study_pack_id>/generate" | python -m json.tool
```

### Fetch generated materials
```bash
curl -s "http://localhost:8000/study-packs/<study_pack_id>/materials" | python -m json.tool
```

---

## Local setup (step-by-step)

### 1) Backend setup
```bash
cd ~/youtube-learning-copilot/apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` (example keys):
```bash
# Database
DATABASE_URL="postgresql+psycopg://ylc:ylc@localhost:5433/ylc"

# Providers
STUDY_MATERIALS_PROVIDER="openai"   # or "heuristic"

# OpenAI (only if provider=openai)
OPENAI_API_KEY="your_key_here"
OPENAI_MODEL="gpt-4o-mini"
```

Run the API:
```bash
cd ~/youtube-learning-copilot/apps/api
source .venv/bin/activate
set -a; source .env; set +a

uvicorn app.main:app --reload --port 8000
```

### 2) Start the Celery worker
In another terminal:
```bash
cd ~/youtube-learning-copilot/apps/api
source .venv/bin/activate
set -a; source .env; set +a

celery -A app.worker.celery_app:celery_app worker -l info
```

### 3) Frontend setup
```bash
cd ~/youtube-learning-copilot/apps/web
npm install
npm run dev
```

Open:
- Web UI: `http://localhost:3000`
- API: `http://localhost:8000`

---

## What we fixed during implementation (important learnings)

### 1) “OpenAI path not used” bug (provider import / symbol missing)
At one point, the Celery worker was always producing heuristic-style outputs, and OpenAI generation was not being executed. We diagnosed this by checking whether the `generate_study_materials_openai` symbol existed in the module and then fixing the import pathway so the provider implementation lives in:

- `apps/api/app/services/llm/openai_client.py`
- `apps/api/app/services/llm/prompts.py`

…and is imported from `app.services.study_materials.generate_and_store_all()` when `STUDY_MATERIALS_PROVIDER=openai`.

### 2) OpenAI SDK mismatch (`response_format` error)
We hit this runtime issue:
> `Responses.create() got an unexpected keyword argument 'response_format'`

That was caused by a mismatch between the SDK usage and the installed OpenAI python package version. We adjusted the client code to align with the SDK version in the repo (and added robust error handling + fallback).

### 3) Timeouts + safe fallback
We observed OpenAI timeouts when transcripts were large. The system now:

- records `openai_error` in `_meta`
- falls back to heuristic generation
- still stores usable study materials, so the UI never breaks

### 4) Debug metadata `_meta` for every material row
Every material `content_json` now carries a `_meta` block like:

```json
{
  "_meta": {
    "requested_provider": "openai",
    "provider": "openai",
    "openai_model": "gpt-4o-mini",
    "openai_error": null,
    "transcript_len": 13912,
    "transcript_clean_len": 10111
  }
}
```

This makes it easy to debug “what happened” using SQL:

```sql
SELECT kind, status,
       (content_json::jsonb->'_meta'->>'requested_provider') AS requested_provider,
       (content_json::jsonb->'_meta'->>'provider') AS provider,
       (content_json::jsonb->'_meta'->>'openai_model') AS model,
       (content_json::jsonb->'_meta'->>'openai_error') AS openai_error
FROM study_materials
WHERE study_pack_id = 25
ORDER BY kind;
```

---

## Outcome so far

- End-to-end flow works: **URL → ingest → pack page → generate → materials render**
- Outputs are now **synthesized** (when OpenAI succeeds), not transcript dumps
- Strong debugging visibility via `_meta`
- UI is functional and aligned to a “glass UI” direction (can be improved further)

---

## What we defined for V1 (next scope)

We haven’t formally “locked” V1 in a single written spec inside this conversation excerpt. Based on the current V0 state and your stated direction (“UI needs to be improved a lot” + “landing-page feel” + “glassmorphism”), this is the V1 definition you can use going forward:

### A) Learning output quality (core)
1. **Chunked generation (map-reduce)** for long transcripts to reduce timeouts and improve coverage.
2. **Stronger validations** to prevent transcript dumps and enforce length/count constraints.
3. **Retry strategy**: retry OpenAI with smaller chunks before falling back to heuristic.
4. **Configurable model/provider** with safe defaults.

### B) UX / UI (core)
1. A real **landing-page style** home with clearer hierarchy and CTA.
2. **Consistent glassmorphism** across all surfaces (inputs, buttons, cards, sections).
3. Better material consumption:
   - tabs/segmented controls
   - improved reading spacing and typography
   - collapsible details where needed
4. Better progress + empty states during ingest/generate.

### C) Product features (high leverage)
1. **Export** pack to Markdown/PDF.
2. **Shareable pack links**.
3. **Recent packs list** page.

### D) Hardening
1. Improved error surfacing in UI (clean + user-friendly).
2. Basic job/material logs for debugging.

---

## Repo structure (relevant parts)

Backend:
- `apps/api/app/main.py` – FastAPI app + CORS
- `apps/api/app/api/study_materials.py` – generate + materials endpoints
- `apps/api/app/services/study_materials.py` – provider orchestration + validation + DB upsert
- `apps/api/app/services/llm/openai_client.py` – OpenAI call logic
- `apps/api/app/services/llm/prompts.py` – prompts
- `apps/api/app/worker/*` – Celery tasks

Frontend:
- `apps/web/src/app/page.tsx` – landing/create flow
- `apps/web/src/app/packs/[id]/page.tsx` – pack viewer + generate
- `apps/web/src/lib/api.ts` – typed API client

---

## Notes
- This README captures what is **implemented today** plus the **V1 scope definition** aligned to your product direction.
- If you want, we can convert the V1 scope into a PRD checklist + step-by-step execution plan with git commits per step.
