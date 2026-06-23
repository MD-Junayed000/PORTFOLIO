"""no-op migration (was: enable pgvector + create document_chunks table)

Revision ID: 0002_pgvector
Revises: 0001_init
Create Date: 2025-01-02 00:00:00

NOTE:
    The pgvector-backed ``document_chunks`` table is no longer created here.
    RAG now runs entirely in-process via ``services/rag_pipeline.py``, which
    loads the local knowledge-base PDF on every FastAPI startup (see the
    ``lifespan`` handler in ``main.py``). This revision is kept so existing
    databases upgrade cleanly and the migration graph stays linear.
"""
from typing import Sequence, Union


revision: str = "0002_pgvector"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: document_chunks was retired when RAG moved off Neon Postgres."""
    return None


def downgrade() -> None:
    """No-op: there is nothing to drop because upgrade() never created anything."""
    return None

