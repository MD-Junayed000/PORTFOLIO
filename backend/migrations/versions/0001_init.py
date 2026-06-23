"""initial schema (Neon PostgreSQL)

Revision ID: 0001_init
Revises:
Create Date: 2025-01-01 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "about_content",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("bio", sa.Text, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("photo_url", sa.String(500), nullable=True),
        sa.Column("photo_public_id", sa.String(500), nullable=True),
        sa.Column("education", sa.Text, nullable=True),
        sa.Column("focus_area", sa.Text, nullable=True),
        sa.Column("subtitle", sa.String(500), nullable=True),
        sa.Column("linkedin_url", sa.String(500), nullable=True),
        sa.Column("github_url", sa.String(500), nullable=True),
        sa.Column("scholar_url", sa.String(500), nullable=True),
        sa.Column("extra_links", sa.Text, nullable=True),
        sa.Column("cv_file_path", sa.String(500), nullable=True),
        sa.Column("cv_public_id", sa.String(500), nullable=True),
        sa.Column("project_display_count", sa.Integer, nullable=True, server_default="6"),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("tech_stack", sa.String(500), nullable=False),
        sa.Column("repo_url", sa.String(500), nullable=True),
        sa.Column("demo_url", sa.String(500), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("image_public_id", sa.String(500), nullable=True),
        sa.Column("order", sa.Integer, nullable=True, server_default="0"),
    )

    op.create_table(
        "skills",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("proficiency", sa.Float, nullable=True, server_default="0"),
    )

    op.create_table(
        "research",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("venue", sa.String(255), nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("link", sa.String(500), nullable=True),
    )

    op.create_table(
        "experiences",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("organization", sa.String(255), nullable=False),
        sa.Column("period", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("logo_public_id", sa.String(500), nullable=True),
    )

    op.create_table(
        "certificates",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("issuer", sa.String(255), nullable=True),
        sa.Column("date", sa.String(50), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_public_id", sa.String(500), nullable=True),
    )

    op.create_table(
        "contact_messages",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "contact_info",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(100), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("notification_emails", sa.Text, nullable=True),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("topic", sa.String(255), nullable=True),
        sa.Column("original_name", sa.String(500), nullable=True),
        sa.Column("uploaded_at", sa.DateTime, nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=True, server_default="0"),
        sa.Column("cloudinary_public_id", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    for tbl in [
        "documents",
        "contact_info",
        "contact_messages",
        "certificates",
        "experiences",
        "research",
        "skills",
        "projects",
        "about_content",
    ]:
        op.drop_table(tbl)
