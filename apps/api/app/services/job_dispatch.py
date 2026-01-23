from __future__ import annotations

from typing import Any, Dict

from app.worker import tasks as worker_tasks


# Map API-level job_type -> Celery task function (task object)
JOB_TYPE_TO_TASK = {
    "sample_pipeline": worker_tasks.run_sample_pipeline,
    "generate_study_materials": worker_tasks.generate_study_materials,
    "ingest_youtube_captions": worker_tasks.ingest_youtube_captions,
}


def dispatch_job(job_type: str, payload: Dict[str, Any] | None = None):
    """
    Dispatch using task objects (.delay/.apply_async) so ENV=test eager mode works.
    Returns celery result object (EagerResult or AsyncResult).
    """
    payload = payload or {}

    task = JOB_TYPE_TO_TASK.get(job_type)
    if not task:
        raise ValueError(f"Unknown job_type: {job_type}")

    # IMPORTANT: use task.apply_async / task.delay (not celery_app.send_task)
    return task.apply_async(kwargs=payload)