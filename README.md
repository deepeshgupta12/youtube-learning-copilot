# YouTube Learning Copilot 🎥📚  
*A local-first learning copilot that turns any YouTube video into a structured study pack — with progress tracking for chapters, flashcards, and quizzes.*

---

## Why I built this ✨

I wanted a **local, fast, distraction-free** way to learn from long YouTube lectures without constantly re-watching or losing context.  
Most learning happens after you watch the video — when you revise, test yourself, and track what you’ve actually understood.

So I built **YouTube Learning Copilot** as a **local-first study system**:

- ✅ Ingest a YouTube video into a **Study Pack**
- ✅ Generate structured learning materials (summary, chapters, flashcards, quiz)
- ✅ Study via dedicated UIs
- ✅ Persist learning progress in Postgres so it survives refreshes & sessions
- ✅ Keep the architecture clean enough to extend into RAG/Q&A, exports, and sharing later

---

## What the product does (today) ✅

### 1) Study Pack creation (YouTube → Pack) 📦
A **Study Pack** is the unit of learning. Each pack represents one ingested video (and later: playlists).

It stores:
- video URL, metadata and ingestion status
- transcript text / chunks (foundation)
- generated study materials

---

### 2) Material generation pipeline ⚙️🧠
From the transcript, the backend generates:

- **Summary**
- **Key Takeaways**
- **Chapters** (title + summary + optional sentences)
- **Flashcards** (Q/A)
- **Quiz** (MCQs + correct answers)

These are stored as `StudyMaterial` rows in Postgres and can be browsed on the pack page.

---

### 3) Study mode + progress tracking 🧩✅
This is what I focused on heavily in the latest implementation.

#### Flashcards study 📇
- Flip card
- Mark:
  - Known ✅
  - Review later 🕒
  - Reset ↩️
- Progress persists to DB:
  - seen_count, known_count, review_later_count
  - last_seen_at
  - current status

#### Quiz study 📝
- Mark question:
  - Correct ✅
  - Wrong ❌
  - Reset ↩️
- Persisted stats:
  - seen_count, correct_count, wrong_count
  - last_seen_at
  - current status (correct/wrong/null)

#### Chapters study 📖
- Open chapter (in-progress)
- Complete chapter ✅
- Reset ↩️
- Persisted fields:
  - opened_count, completed_count
  - last_opened_at, last_completed_at
  - status (in_progress/completed/null)
- Also provides:
  - **resume_chapter_index** (best next chapter to continue)

---

## What’s implemented version-wise 🚀

### ✅ V1 — Ingestion + generation foundation
Done:
- Study pack ingestion baseline
- Job queue pattern (create job → worker runs → UI polls)
- Materials generation: summary, takeaways, chapters, flashcards, quiz
- Pack page: browse materials cleanly

Still pending in V1:
- playlist ingestion fanout (create packs per playlist item)
- hardened captions-first → STT fallback orchestration
- canonical timestamped transcript chunk storage

---

### ✅ V2 — Study experience (progress + study hub)
Done in V2 so far:
- Flashcards progress DB + APIs + study UI ✅
- Quiz progress DB + APIs + study UI ✅
- Chapters progress DB + APIs + study UI ✅
- Pack page CTAs to study pages ✅

Still pending in V2 (actual “RAG + Q&A”):
- embeddings + pgvector pipeline
- retrieval endpoint with citations
- transcript-grounded chat endpoint with “not in video” refusal

---

### ⏳ V3 — Attempts + advanced outputs
Planned:
- Notes variants: short/structured/detailed/glossary
- Quiz types: multi-select, T/F, fill-blank, short answer
- Attempts + scoring + explanations
- Mock tests (timed + blueprint coverage)

---

### ⏳ V4 — Exports + sharing + ops polish
Planned:
- PDF/Markdown export
- share links (view-only / attempt-only)
- usage counters + moderation flags (analytics removed)

---

## Tech stack 🧱

### Frontend
- Next.js + TypeScript
- Tailwind CSS

### Backend
- FastAPI (Python)
- SQLAlchemy
- Pydantic

### DB / infra (local)
- PostgreSQL (Docker)
- Redis (for job queue / workers)

---

## Repo structure 🗂️

```txt
youtube-learning-copilot/
  apps/
    api/
      app/
        api/                # FastAPI routers
        models/             # SQLAlchemy models
        services/           # Business logic (flashcards/quizzes/chapters)
        worker/             # Background tasks
    web/
      src/
        app/
          packs/
            [id]/           # Pack page (browse + study hub CTAs)
            [id]/study/
              flashcards/   # Flashcards study UI
              quiz/         # Quiz study UI
              chapters/     # Chapters study UI
        lib/api.ts          # Typed API client
```

---

## Database tables added in V2 🧾

### Flashcards progress
```sql
CREATE TABLE IF NOT EXISTS study_flashcard_progress (
  id BIGSERIAL PRIMARY KEY,
  study_pack_id BIGINT NOT NULL,
  card_index INT NOT NULL,
  status VARCHAR(32) NULL,
  seen_count INT NOT NULL DEFAULT 0,
  known_count INT NOT NULL DEFAULT 0,
  review_later_count INT NOT NULL DEFAULT 0,
  last_seen_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(study_pack_id, card_index)
);
```

### Quiz progress
```sql
CREATE TABLE IF NOT EXISTS study_quiz_progress (
  id BIGSERIAL PRIMARY KEY,
  study_pack_id BIGINT NOT NULL,
  question_index INT NOT NULL,
  status VARCHAR(32) NULL,
  seen_count INT NOT NULL DEFAULT 0,
  correct_count INT NOT NULL DEFAULT 0,
  wrong_count INT NOT NULL DEFAULT 0,
  last_seen_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(study_pack_id, question_index)
);
```

### Chapters progress
```sql
CREATE TABLE IF NOT EXISTS study_chapter_progress (
  id BIGSERIAL PRIMARY KEY,
  study_pack_id BIGINT NOT NULL,
  chapter_index INT NOT NULL,
  status VARCHAR(32) NULL,
  opened_count INT NOT NULL DEFAULT 0,
  completed_count INT NOT NULL DEFAULT 0,
  last_opened_at TIMESTAMPTZ NULL,
  last_completed_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(study_pack_id, chapter_index)
);
```

---

## Key APIs (what I use from the frontend) 🔌

### Materials
- `GET /study-packs/{id}/materials` → fetch all generated materials  
- `POST /study-packs/{id}/generate` → trigger generation job

### Flashcards progress
- `GET /study-packs/{id}/flashcards/progress`
- `POST /study-packs/{id}/flashcards/progress`
  ```json
  {"card_index": 0, "action": "known"} 
  ```

### Quiz progress
- `GET /study-packs/{id}/quiz/progress`
- `POST /study-packs/{id}/quiz/progress`
  ```json
  {"question_index": 0, "action": "correct"}
  ```

### Chapters progress
- `GET /study-packs/{id}/chapters/progress`
- `POST /study-packs/{id}/chapters/progress`
  ```json
  {"chapter_index": 0, "action": "complete"}
  ```

---

## How progress logic works (high level) 🧠

### ✅ “Progress is derived from generated material count”
For flashcards/quiz/chapters, I don’t store total counts in DB.  
Instead:
- I load the generated material (from `StudyMaterial.kind`)
- derive total cards/questions/chapters from that JSON
- then read progress rows and merge into a complete index-aligned list

This keeps it clean: if generation changes, progress still maps correctly by index.

---

## Local setup (quickstart) 🏁

> Assumes you already have Python + Node + Docker installed.

### 1) Start infra (Postgres + Redis)
```bash
docker compose up -d
```

### 2) Backend
```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3) Frontend
```bash
cd apps/web
npm install
npm run dev
```

Open:
- Web: `http://localhost:3000`
- API: `http://localhost:8000`

---

## How I test quickly ✅

### Materials present?
```bash
curl -s "http://localhost:8000/study-packs/87/materials" | python -m json.tool
```

### Flashcards progress
```bash
curl -s "http://localhost:8000/study-packs/87/flashcards/progress" | python -m json.tool
curl -s -X POST "http://localhost:8000/study-packs/87/flashcards/progress" \
  -H "Content-Type: application/json" \
  -d '{"card_index":0,"action":"known"}' | python -m json.tool
```

### Quiz progress
```bash
curl -s "http://localhost:8000/study-packs/87/quiz/progress" | python -m json.tool
curl -s -X POST "http://localhost:8000/study-packs/87/quiz/progress" \
  -H "Content-Type: application/json" \
  -d '{"question_index":0,"action":"correct"}' | python -m json.tool
```

### Chapters progress
```bash
curl -s "http://localhost:8000/study-packs/87/chapters/progress" | python -m json.tool
curl -s -X POST "http://localhost:8000/study-packs/87/chapters/progress" \
  -H "Content-Type: application/json" \
  -d '{"chapter_index":0,"action":"open"}' | python -m json.tool
```

---

## What I’ll build next 🔜 (Study Hub + RAG)
- A unified **Study Hub** home inside each pack:
  - continue where I left off (chapters resume)
  - quick actions: flashcards / quiz / chapters
  - progress summaries in one place
- Then start the true V2:
  - transcript chunk embeddings
  - citations-first retrieval
  - grounded chat/Q&A with “not in video” refusal

---

## Notes / constraints 🧩
- All progress currently maps by **index** (card_index/question_index/chapter_index).
- If a pack regenerates and changes ordering, old progress remains but may not map perfectly.
  - Later I can attach stable IDs/hashes to generated items.

---

## Credits 🙌
Built as a local-first learning tool to make YouTube studying structured, trackable, and actually effective.

