import os
from celery import Celery


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v and v.strip() else default


BROKER_URL = (
    _env("CELERY_BROKER_URL")
    or _env("REDIS_URL")
    or "redis://localhost:6379/0"
)

RESULT_BACKEND = _env("CELERY_RESULT_BACKEND") or BROKER_URL


# IMPORTANT: the variable name MUST be `celery_app`
celery_app = Celery(
    "youtube_learning_copilot",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
)

# Ensure tasks are discovered (reliable + avoids import timing issues)
celery_app.autodiscover_tasks(["app.worker"])

celery_app.conf.update(
    task_track_started=True,
    result_extended=True,
    enable_utc=True,
    timezone="UTC",
)

if os.getenv("ENV") == "test":
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        task_store_eager_result=True,
    )

__all__ = ["celery_app"]