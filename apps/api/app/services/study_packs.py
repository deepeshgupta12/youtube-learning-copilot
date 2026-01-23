import json
from sqlalchemy.orm import Session

from app.models.study_pack import StudyPack


def create_study_pack(db: Session, source_type: str, source_url: str, source_id: str | None, language: str | None) -> StudyPack:
    sp = StudyPack(
        source_type=source_type,
        source_url=source_url,
        source_id=source_id,
        language=language,
        status="created",
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return sp


def set_ingested(
    db: Session,
    study_pack_id: int,
    *,
    title: str | None,
    meta: dict | None,
    transcript_segments: list,
    transcript_text: str,
    language: str | None,
) -> StudyPack:
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).one()
    sp.title = title or sp.title
    sp.meta_json = json.dumps(meta or {}, ensure_ascii=False)
    sp.transcript_json = json.dumps(transcript_segments, ensure_ascii=False)
    sp.transcript_text = transcript_text
    sp.language = language or sp.language
    sp.status = "ingested"
    sp.error = None
    db.commit()
    db.refresh(sp)
    return sp


def set_failed(db: Session, study_pack_id: int, error: str) -> StudyPack:
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).one()
    sp.status = "failed"
    sp.error = error
    db.commit()
    db.refresh(sp)
    return sp
