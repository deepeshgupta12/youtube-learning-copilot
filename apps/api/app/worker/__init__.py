# Ensures Celery sees tasks in this package
from app.worker import tasks  # noqa: F401
from app.worker import ingest_tasks  # noqa: F401
