from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.study_pack import StudyPack

router = APIRouter(tags=["study-packs"])


@router.get("/study-packs/{study_pack_id}")
def get_study_pack(study_pack_id: int, db: Session = Depends(get_db)):
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Study pack not found")

    return {
        "ok": True,
        "study_pack": {
            "id": sp.id,
            "source_type": sp.source_type,
            "source_url": sp.source_url,
            "title": sp.title,
            "status": sp.status,
            "source_id": sp.source_id,
            "language": sp.language,
            "meta_json": sp.meta_json,
            "transcript_json": sp.transcript_json,
            "transcript_text": sp.transcript_text,
            "error": sp.error,
            "created_at": sp.created_at.isoformat() if sp.created_at else None,
            "updated_at": sp.updated_at.isoformat() if sp.updated_at else None,
        },
    }