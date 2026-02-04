"""V2.0 add pgvector transcript chunk embeddings

Revision ID: 298b25f25b72
Revises: 2837d8b91cde
Create Date: 2026-02-04 17:43:48.086533

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "298b25f25b72"
down_revision: Union[str, None] = "2837d8b91cde"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


class VectorType(sa.types.UserDefinedType):
    """SQLAlchemy type for pgvector: vector(dim)."""

    cache_ok = True

    def __init__(self, dim: int):
        self.dim = int(dim)

    def get_col_spec(self, **kw) -> str:  # required by SQLAlchemy compiler
        return f"vector({self.dim})"


def upgrade() -> None:
    # pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "transcript_chunk_embeddings",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),

        sa.Column(
            "study_pack_id",
            sa.BigInteger(),
            sa.ForeignKey("study_packs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            sa.BigInteger(),
            sa.ForeignKey("transcript_chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),

        sa.Column("model", sa.String(length=128), nullable=False, server_default="unknown"),
        sa.Column("dim", sa.Integer(), nullable=False),

        # ✅ pgvector column
        sa.Column("embedding", VectorType(384), nullable=False),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.UniqueConstraint("chunk_id", "model", name="uq_chunk_embeddings_chunk_model"),
    )

    op.create_index("ix_transcript_chunk_embeddings_id", "transcript_chunk_embeddings", ["id"])
    op.create_index("idx_chunk_embeddings_pack", "transcript_chunk_embeddings", ["study_pack_id"])
    op.create_index("idx_chunk_embeddings_chunk", "transcript_chunk_embeddings", ["chunk_id"])


def downgrade() -> None:
    op.drop_index("idx_chunk_embeddings_chunk", table_name="transcript_chunk_embeddings")
    op.drop_index("idx_chunk_embeddings_pack", table_name="transcript_chunk_embeddings")
    op.drop_index("ix_transcript_chunk_embeddings_id", table_name="transcript_chunk_embeddings")
    op.drop_table("transcript_chunk_embeddings")
    # Keep extension installed (safe). If you want strict rollback:
    # op.execute("DROP EXTENSION IF EXISTS vector")