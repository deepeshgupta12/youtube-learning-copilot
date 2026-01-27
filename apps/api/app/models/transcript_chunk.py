from __future__ import annotations

from sqlalchemy import BigInteger, Column, Float, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"

    id = Column(BigInteger, primary_key=True, index=True)

    study_pack_id = Column(
        BigInteger,
        ForeignKey("study_packs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    idx = Column(Integer, nullable=False)
    start_sec = Column(Float, nullable=False)
    end_sec = Column(Float, nullable=False)
    text = Column(Text, nullable=False)

    study_pack = relationship("StudyPack", backref="transcript_chunks")

    __table_args__ = (
        UniqueConstraint("study_pack_id", "idx", name="uq_transcript_chunks_pack_idx"),
        Index("idx_transcript_chunks_pack", "study_pack_id"),
        Index("idx_transcript_chunks_time", "study_pack_id", "start_sec", "end_sec"),
    )