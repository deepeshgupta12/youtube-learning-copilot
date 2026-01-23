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


# --------------------------------------------------------------------------------------
# IMPORTANT:
# Celery autodiscover only imports "app.worker.tasks" by default.
# Your other tasks live in separate modules (generate_tasks.py, ingest_tasks.py),
# so we import them here to ensure they get registered with Celery.
# --------------------------------------------------------------------------------------

# noqa imports are intentional (they register @celery_app.task decorators)
from app.worker.generate_tasks import generate_study_materials  # noqa: F401,E402
from app.worker.ingest_tasks import ingest_youtube_captions  # noqa: F401,E402