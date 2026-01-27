from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.study_material import StudyMaterial
from app.models.study_pack import StudyPack
from app.services.jobs import create_job
from app.worker.generate_tasks import generate_study_materials

router = APIRouter(prefix="/study-packs", tags=["study_materials"])


class GenerateStudyMaterialsResponse(BaseModel):
    ok: bool
    study_pack_id: int
    job_id: int
    task_id: str


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


def _safe_json_loads(s: str | None):
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        # Don't break API if one row has corrupted JSON.
        return None


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