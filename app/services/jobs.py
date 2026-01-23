import json
from sqlalchemy.orm import Session

from app.models.job import Job


def create_job(db: Session, job_type: str, payload: dict) -> Job:
    job = Job(job_type=job_type, status="queued", payload_json=json.dumps(payload or {}))
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def set_job_status(db: Session, job_id: int, status: str, error: str | None = None) -> Job:
    job = db.query(Job).filter(Job.id == job_id).one()
    job.status = status
    job.error = error
    db.commit()
    db.refresh(job)
    return job
