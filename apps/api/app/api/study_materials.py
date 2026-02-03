from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.study_material import StudyMaterial
from app.models.study_pack import StudyPack
from app.services.flashcards import get_flashcards_progress, mark_flashcard
from app.services.jobs import create_job
from app.services.quizzes import get_quiz_progress, mark_quiz_question
from app.worker.generate_tasks import generate_study_materials
from app.services.chapters import get_chapters_progress, mark_chapter

router = APIRouter(prefix="/study-packs", tags=["study_materials"])


class GenerateStudyMaterialsResponse(BaseModel):
    ok: bool
    study_pack_id: int
    job_id: int
    task_id: str

class ChapterProgressResponse(BaseModel):
    ok: bool
    study_pack_id: int
    total_chapters: int
    opened_chapters: int
    completed_chapters: int
    resume_chapter_index: int
    items: list[dict]


class ChapterMarkRequest(BaseModel):
    chapter_index: int
    action: str  # open | complete | reset


# -----------------------
# Materials
# -----------------------
def _safe_json_loads(s: str | None):
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


@router.post("/{study_pack_id}/generate", response_model=GenerateStudyMaterialsResponse)
def generate_for_study_pack(study_pack_id: int, db: Session = Depends(get_db)) -> GenerateStudyMaterialsResponse:
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Study pack not found")
    if sp.status != "ingested":
        raise HTTPException(status_code=400, detail=f"Study pack is not ingested yet (status={sp.status})")

    job = create_job(db, "generate_study_materials", {"study_pack_id": study_pack_id})
    async_result = generate_study_materials.delay(job.id, study_pack_id)

    return GenerateStudyMaterialsResponse(ok=True, study_pack_id=study_pack_id, job_id=job.id, task_id=async_result.id)


@router.get("/{study_pack_id}/materials")
def get_materials(study_pack_id: int, db: Session = Depends(get_db)):
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Study pack not found")

    rows = (
        db.query(StudyMaterial)
        .filter(StudyMaterial.study_pack_id == study_pack_id)
        .order_by(StudyMaterial.id.asc())
        .all()
    )

    materials = []
    for r in rows:
        materials.append(
            {
                "id": r.id,
                "kind": r.kind,
                "status": r.status,
                "content_json": _safe_json_loads(r.content_json),
                "content_text": r.content_text,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
        )

    return {"ok": True, "study_pack_id": study_pack_id, "materials": materials}


# -----------------------
# Flashcards progress
# -----------------------
class FlashcardProgressResponse(BaseModel):
    ok: bool
    study_pack_id: int
    total_cards: int
    seen_cards: int
    known_cards: int
    review_later_cards: int
    items: list[dict]


class FlashcardMarkRequest(BaseModel):
    card_index: int
    action: str  # known | review_later | reset | seen


@router.get("/{study_pack_id}/flashcards/progress", response_model=FlashcardProgressResponse)
def flashcards_progress(study_pack_id: int, db: Session = Depends(get_db)) -> FlashcardProgressResponse:
    try:
        p = get_flashcards_progress(db, study_pack_id)
        return FlashcardProgressResponse(ok=True, **p)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{study_pack_id}/flashcards/progress", response_model=FlashcardProgressResponse)
def flashcards_mark(
    study_pack_id: int,
    req: FlashcardMarkRequest,
    db: Session = Depends(get_db),
) -> FlashcardProgressResponse:
    try:
        p = mark_flashcard(db, study_pack_id, req.card_index, req.action)
        return FlashcardProgressResponse(ok=True, **p)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# -----------------------
# Quiz progress
# -----------------------
class QuizProgressResponse(BaseModel):
    ok: bool
    study_pack_id: int
    total_questions: int
    seen_questions: int
    correct_questions: int
    wrong_questions: int
    items: list[dict]


class QuizMarkRequest(BaseModel):
    question_index: int
    action: str  # correct | wrong | reset | seen


@router.get("/{study_pack_id}/quiz/progress", response_model=QuizProgressResponse)
def quiz_progress(study_pack_id: int, db: Session = Depends(get_db)) -> QuizProgressResponse:
    try:
        p = get_quiz_progress(db, study_pack_id)
        return QuizProgressResponse(ok=True, **p)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{study_pack_id}/quiz/progress", response_model=QuizProgressResponse)
def quiz_mark(
    study_pack_id: int,
    req: QuizMarkRequest,
    db: Session = Depends(get_db),
) -> QuizProgressResponse:
    try:
        p = mark_quiz_question(db, study_pack_id, req.question_index, req.action)
        return QuizProgressResponse(ok=True, **p)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.get("/{study_pack_id}/chapters/progress", response_model=ChapterProgressResponse)
def chapters_progress(study_pack_id: int, db: Session = Depends(get_db)) -> ChapterProgressResponse:
    try:
        p = get_chapters_progress(db, study_pack_id)
        return ChapterProgressResponse(ok=True, **p)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{study_pack_id}/chapters/progress", response_model=ChapterProgressResponse)
def chapters_mark(
    study_pack_id: int,
    req: ChapterMarkRequest,
    db: Session = Depends(get_db),
) -> ChapterProgressResponse:
    try:
        p = mark_chapter(db, study_pack_id, req.chapter_index, req.action)
        return ChapterProgressResponse(ok=True, **p)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))