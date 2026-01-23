from __future__ import annotations

from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

# IMPORTANT:
# DO NOT import Base from app.db.base here (that creates a circular import).
# Use base_class instead.
from app.db.base_class import Base


class StudyPack(Base):
    __tablename__ = "study_packs"

    id = Column(Integer, primary_key=True, index=True)

    source_type = Column(String(32), nullable=False)
    source_url = Column(Text, nullable=False)
    title = Column(String(512), nullable=True)
    status = Column(String(32), nullable=False)

    source_id = Column(String(64), nullable=True, index=True)
    language = Column(String(16), nullable=True)

    meta_json = Column(Text, nullable=True)
    transcript_json = Column(Text, nullable=True)
    transcript_text = Column(Text, nullable=True)

    error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)