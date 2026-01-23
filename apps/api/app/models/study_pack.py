from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class StudyPack(Base):
    __tablename__ = "study_packs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # source
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # youtube_video|youtube_playlist
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # display/meta
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # ingestion outputs
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)         # JSON string
    transcript_json: Mapped[str | None] = mapped_column(Text, nullable=True)   # JSON string: [{text,start,duration}]
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # status
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
