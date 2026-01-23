from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(title="YouTube Learning Copilot API", version="0.0.1")


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, service="api", version=app.version)