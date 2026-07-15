"""add job_matches table

Revision ID: d520eab54f65
Revises: e3a7c9912b4d
Create Date: 2026-07-14 16:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d520eab54f65"
down_revision: Union[str, Sequence[str], None] = "e3a7c9912b4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_matches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["query_id"], ["queries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_matches_job_query", "job_matches", ["job_id", "query_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_job_matches_job_query", table_name="job_matches")
    op.drop_table("job_matches")
