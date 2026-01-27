import os
from pathlib import Path

from celery import Celery

# Load .env for BOTH API + Celery worker (worker often runs without `source .env`)
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    # apps/api/app/worker/celery_app.py -> parents[3] is apps/api
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
except Exception:
    # Don't crash if dotenv isn't installed in some env
    pass


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

# Ensure tasks are discovered
celery_app.autodiscover_tasks(["app.worker"])

celery_app.conf.update(
    task_track_started=True,
    result_extended=True,
    enable_utc=True,
    timezone="UTC",
)

__all__ = ["celery_app"]