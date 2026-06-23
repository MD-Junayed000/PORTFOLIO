"""enable pgvector + create document_chunks table

Revision ID: 0002_pgvector
Revises: 0001_init
Create Date: 2025-01-02 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_pgvector"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable the pgvector extension. Neon supports it on all plans.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("chunk_id", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("document_id", sa.String(255), nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("section_number", sa.String(50), nullable=True, index=True),
        sa.Column("entity_type", sa.String(50), nullable=True, index=True),
        sa.Column("section", sa.String(500), nullable=True),
        sa.Column("subsection", sa.String(500), nullable=True),
        sa.Column("source", sa.String(500), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("keywords", sa.Text, nullable=True),
        sa.Column("extra_metadata", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    # Add the vector column with the documented dimension.
    # We use raw SQL because SQLAlchemy's Vector type ships with pgvector but
    # we want this migration to be self-contained.
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(384)")

    # IVFFlat index for cosine similarity. lists=100 is appropriate for up to
    # ~1M rows; raise it later if the collection grows.
    op.execute(
        "CREATE INDEX document_chunks_embedding_idx "
        "ON document_chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS document_chunks_embedding_idx")
    op.drop_table("document_chunks")
    # Leave the vector extension installed; dropping it can fail if other
    # tables depend on it.
