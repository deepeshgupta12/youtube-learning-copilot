from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.jobs import set_job_status
from app.services.study_materials import generate_and_store_all
from app.worker.celery_app import celery_app


@celery_app.task(name="generate.study_materials")
def generate_study_materials(job_id: int, study_pack_id: int) -> dict:
    db: Session = SessionLocal()
    try:
        set_job_status(db, job_id, "running")
        generate_and_store_all(db, study_pack_id)
        set_job_status(db, job_id, "done")
        return {"ok": True, "study_pack_id": study_pack_id, "job_id": job_id}
    except Exception as e:
        set_job_status(db, job_id, "failed", error=str(e))
        raise
    finally:
        db.close()