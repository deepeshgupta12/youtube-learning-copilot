from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, BigInteger, String, UniqueConstraint, func
from app.db.base_class import Base  # this should match your project Base import


class FlashcardProgress(Base):
    __tablename__ = "study_flashcard_progress"

    id = Column(BigInteger, primary_key=True, index=True)
    study_pack_id = Column(BigInteger, nullable=False, index=True)
    card_index = Column(Integer, nullable=False)

    # status: null | "known" | "review_later"
    status = Column(String(32), nullable=True)

    seen_count = Column(Integer, nullable=False, default=0)
    known_count = Column(Integer, nullable=False, default=0)
    review_later_count = Column(Integer, nullable=False, default=0)

    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("study_pack_id", "card_index", name="uq_flashcard_pack_card"),
    )