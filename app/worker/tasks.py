import time
from sqlalchemy.orm import Session

from app.worker.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.jobs import set_job_status


@celery_app.task(name="jobs.run_sample_pipeline")
def run_sample_pipeline(job_id: int, sleep_sec: int = 2) -> dict:
    db: Session = SessionLocal()
    try:
        set_job_status(db, job_id, "running")
        time.sleep(sleep_sec)
        set_job_status(db, job_id, "done")
        return {"ok": True, "job_id": job_id}
    except Exception as e:
        set_job_status(db, job_id, "failed", error=str(e))
        raise
    finally:
        db.close()
