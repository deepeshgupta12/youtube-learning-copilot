from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

app = FastAPI(title="YouTube Learning Copilot API", version="0.0.1")


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str
    db_ok: bool


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    # lightweight DB check
    db_ok = False
    try:
        db: Session = next(get_db())
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    finally:
        try:
            db.close()
        except Exception:
            pass

    return HealthResponse(ok=True, service="api", version=app.version, db_ok=db_ok)
