from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, UniqueConstraint, func

from app.db.base_class import Base


class ChapterProgress(Base):
    __tablename__ = "study_chapter_progress"

    id = Column(BigInteger, primary_key=True, index=True)
    study_pack_id = Column(BigInteger, nullable=False, index=True)
    chapter_index = Column(Integer, nullable=False)

    # status: null | "in_progress" | "completed"
    status = Column(String(32), nullable=True)

    opened_count = Column(Integer, nullable=False, default=0)
    completed_count = Column(Integer, nullable=False, default=0)

    last_opened_at = Column(DateTime(timezone=True), nullable=True)
    last_completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("study_pack_id", "chapter_index", name="uq_chapter_pack_chapter"),
    )