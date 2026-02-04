from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from pgvector.sqlalchemy import Vector

from app.db.base_class import Base


class TranscriptChunkEmbedding(Base):
    """
    Stores vector embeddings for each transcript chunk.

    Why separate table?
    - allows re-embedding with new models without touching transcript_chunks
    - keeps transcript_chunks lightweight
    - supports multiple embedding models per chunk (future)
    """
    __tablename__ = "transcript_chunk_embeddings"

    id = Column(BigInteger, primary_key=True, index=True)

    study_pack_id = Column(
        BigInteger,
        ForeignKey("study_packs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_id = Column(
        BigInteger,
        ForeignKey("transcript_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # embedding model metadata
    model = Column(String(128), nullable=False, default="unknown")
    dim = Column(Integer, nullable=False)

    # pgvector column (use a fixed dimension for now; V2 uses 384)
    embedding = Column(Vector(384), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    chunk = relationship("TranscriptChunk", backref="embeddings")
    study_pack = relationship("StudyPack", backref="chunk_embeddings")

    __table_args__ = (
        # one embedding per (chunk, model) in V2; supports future multi-model
        UniqueConstraint("chunk_id", "model", name="uq_chunk_embeddings_chunk_model"),
        Index("idx_chunk_embeddings_pack", "study_pack_id"),
        Index("idx_chunk_embeddings_chunk", "chunk_id"),
    )