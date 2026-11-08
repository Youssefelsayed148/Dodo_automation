"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-08
"""
import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "books",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("source_text", sa.Text, nullable=True),
        sa.Column("book_language", sa.String(5), nullable=False),
        sa.Column("trim_size", sa.String(40), nullable=False),
        sa.Column("bleed", sa.Boolean, nullable=False),
        sa.Column("page_count", sa.Integer, nullable=False),
        sa.Column("theme_id", sa.Integer, nullable=True),
        sa.Column("format_id", sa.Integer, nullable=True),
        sa.Column("style_anchor", sa.JSON, nullable=False),
        sa.Column("meta", sa.JSON, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("mood", sa.String(200), nullable=False),
        sa.Column("age_group", sa.String(50), nullable=False),
        sa.Column("line_weight", sa.String(50), nullable=False),
        sa.Column("detail_level", sa.String(50), nullable=False),
        sa.Column("page_mix", sa.JSON, nullable=False),
        sa.Column("confidence", sa.String(10), nullable=False),
        sa.Column("notes", sa.Text, nullable=False),
    )
    op.create_table(
        "theme_options",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("chosen", sa.Boolean, nullable=False),
    )
    op.create_table(
        "format_options",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("blocks", sa.JSON, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("chosen", sa.Boolean, nullable=False),
    )
    op.create_table(
        "characters",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("species", sa.String(200), nullable=False),
        sa.Column("personality", sa.Text, nullable=False),
        sa.Column("signature_feature", sa.String(300), nullable=False),
        sa.Column("proportions", sa.String(300), nullable=False),
        sa.Column("brief", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("in_library", sa.Boolean, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "character_assets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("character_id", sa.Integer, sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("selected", sa.Boolean, nullable=False),
        sa.Column("meta", sa.JSON, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "pages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("index", sa.Integer, nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("text_content", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("image_path", sa.Text, nullable=True),
        sa.Column("qa", sa.JSON, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("batch_no", sa.Integer, nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("meta", sa.JSON, nullable=False),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("book_id", sa.Integer, nullable=True, index=True),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("progress", sa.Float, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_table(
        "usage_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("units", sa.Float, nullable=False),
        sa.Column("est_cost_usd", sa.Float, nullable=False),
        sa.Column("book_id", sa.Integer, nullable=True, index=True),
        sa.Column("page_id", sa.Integer, nullable=True, index=True),
        sa.Column("purpose", sa.String(60), nullable=False),
        sa.Column("at", TS, nullable=False),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    for t in ("settings", "usage_logs", "jobs", "pages", "character_assets", "characters", "format_options",
              "theme_options", "recipes", "books"):
        op.drop_table(t)
