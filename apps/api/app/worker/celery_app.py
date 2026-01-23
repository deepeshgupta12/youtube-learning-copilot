import os
from celery import Celery

from app.core.celery_settings import is_test_env

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)

celery_app = Celery(
    "ylc_worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
)

# Ensure tasks are discovered
celery_app.autodiscover_tasks(["app.worker"])

# Make tests deterministic (no external worker required)
if is_test_env():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
