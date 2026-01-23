import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
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


settings = Settings()
