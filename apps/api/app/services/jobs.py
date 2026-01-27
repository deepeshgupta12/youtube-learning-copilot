import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.job import Job


def create_job(db: Session, job_type: str, payload: dict) -> Job:
    job = Job(
        job_type=job_type,
        status="queued",
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
    )
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


def get_job_payload(db: Session, job_id: int) -> dict[str, Any]:
    job = db.query(Job).filter(Job.id == job_id).one()
    try:
        return json.loads(job.payload_json or "{}")
    except Exception:
        return {}


def set_job_payload(db: Session, job_id: int, payload: dict[str, Any]) -> Job:
    job = db.query(Job).filter(Job.id == job_id).one()
    job.payload_json = json.dumps(payload or {}, ensure_ascii=False)
    db.commit()
    db.refresh(job)
    return job


def merge_job_payload(db: Session, job_id: int, patch: dict[str, Any]) -> Job:
    """
    Safely merge a patch into payload_json.
    - Keeps existing keys
    - Overwrites keys present in patch
    """
    job = db.query(Job).filter(Job.id == job_id).one()
    base: dict[str, Any]
    try:
        base = json.loads(job.payload_json or "{}")
        if not isinstance(base, dict):
            base = {}
    except Exception:
        base = {}

    for k, v in (patch or {}).items():
        base[k] = v

    job.payload_json = json.dumps(base, ensure_ascii=False)
    db.commit()
    db.refresh(job)
    return job