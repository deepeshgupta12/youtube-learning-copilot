# apps/api/app/worker/celery_app.py
import os
from celery import Celery

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v and v.strip() else default

# Option A: Redis is our default local broker.
BROKER_URL = (
    _env("CELERY_BROKER_URL")
    or _env("REDIS_URL")
    or "redis://localhost:6379/0"
)

RESULT_BACKEND = _env("CELERY_RESULT_BACKEND") or BROKER_URL

celery_app = Celery(
    "youtube_learning_copilot",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "app.worker.ingest_tasks",
        "app.worker.generate_tasks",
    ],
)

celery_app.conf.update(
    task_track_started=True,
    result_extended=True,
    enable_utc=True,
    timezone="UTC",
)

# Helpful startup log (shows up in worker terminal)
celery_app.log.setup()
celery_app.log.get_default_logger().info(
    "Celery configured: broker=%s backend=%s", BROKER_URL, RESULT_BACKEND
)