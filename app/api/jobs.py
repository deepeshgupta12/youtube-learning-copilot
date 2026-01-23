from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.jobs import create_job
from app.worker.tasks import run_sample_pipeline

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCreateRequest(BaseModel):
    job_type: str = "sample_pipeline"
    payload: dict = {}
    sleep_sec: int = 2


class JobCreateResponse(BaseModel):
    ok: bool
    job_id: int
    task_id: str


@router.post("", response_model=JobCreateResponse)
def create_and_run_job(req: JobCreateRequest, db: Session = Depends(get_db)) -> JobCreateResponse:
    job = create_job(db, req.job_type, req.payload)
    async_result = run_sample_pipeline.delay(job.id, req.sleep_sec)
    return JobCreateResponse(ok=True, job_id=job.id, task_id=async_result.id)


class JobGetResponse(BaseModel):
    ok: bool
    job_id: int
    job_type: str
    status: str
    error: str | None
    payload_json: str


@router.get("/{job_id}", response_model=JobGetResponse)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobGetResponse:
    from app.models.job import Job

    job = db.query(Job).filter(Job.id == job_id).one()
    return JobGetResponse(
        ok=True,
        job_id=job.id,
        job_type=job.job_type,
        status=job.status,
        error=job.error,
        payload_json=job.payload_json,
    )
