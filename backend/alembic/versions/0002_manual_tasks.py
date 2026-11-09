"""manual mode: ChatGPT tasks

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-09
"""
import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "manual_tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer, nullable=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("task", sa.String(60), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("task_group", sa.String(200), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("meta", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("answer_text", sa.Text, nullable=True),
        sa.Column("answer_path", sa.Text, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("answered_at", TS, nullable=True),
        sa.UniqueConstraint("book_id", "key", name="uq_manual_task_book_key"),
    )
    op.create_index("ix_manual_tasks_book_id", "manual_tasks", ["book_id"])
    op.create_index("ix_manual_tasks_job_id", "manual_tasks", ["job_id"])
    op.create_index("ix_manual_tasks_status", "manual_tasks", ["status"])


def downgrade() -> None:
    op.drop_table("manual_tasks")
