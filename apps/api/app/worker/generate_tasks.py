from __future__ import annotations

from celery import shared_task

from app.db.session import SessionLocal
from app.services.study_materials import generate_and_store_all


@shared_task(name="generate.study_materials")
def generate_study_materials(job_id: int, study_pack_id: int) -> dict:
    """
    Generates study materials for a given study_pack_id.
    """
    db = SessionLocal()
    try:
        generate_and_store_all(db, study_pack_id)
        return {"ok": True, "study_pack_id": study_pack_id, "job_id": job_id}
    finally:
        db.close()