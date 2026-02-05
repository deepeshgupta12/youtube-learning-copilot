import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Always load .env from apps/api/.env (stable, regardless of CWD)
    BASE_DIR = Path(__file__).resolve().parents[2]  # apps/api
    dotenv_path = BASE_DIR / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=False)
except Exception:
    # dotenv is optional; if not installed, env vars still work
    pass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://ylc:ylc@localhost:5433/ylc",
    )
    env: str = os.getenv("ENV", "local")

    # V2.3 — Ollama
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")


settings = Settings()