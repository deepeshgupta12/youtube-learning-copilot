# apps/api/app/worker/generate_tasks.py
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.study_materials import generate_and_store_all
from app.worker.celery_app import celery_app


@celery_app.task(name="generate.study_materials")
def generate_study_materials(job_id: int, study_pack_id: int) -> dict:
    """
    Generates study materials for a given study_pack_id.
    """
    db: Session = SessionLocal()
    try:
        generate_and_store_all(db, study_pack_id)
        return {"ok": True, "study_pack_id": study_pack_id, "job_id": job_id}
    finally:
        db.close()