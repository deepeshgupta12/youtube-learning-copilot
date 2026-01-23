from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.db.base import Base


class StudyMaterial(Base):
    __tablename__ = "study_materials"

    id = Column(Integer, primary_key=True, index=True)
    study_pack_id = Column(Integer, ForeignKey("study_packs.id", ondelete="CASCADE"), nullable=False, index=True)

    # summary | key_takeaways | chapters | flashcards | quiz
    kind = Column(String(50), nullable=False, index=True)

    status = Column(String(20), nullable=False, default="pending", index=True)  # pending|generated|failed
    content_json = Column(Text, nullable=True)   # JSON string
    content_text = Column(Text, nullable=True)   # optional plain text
    error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    study_pack = relationship("StudyPack", backref="materials")