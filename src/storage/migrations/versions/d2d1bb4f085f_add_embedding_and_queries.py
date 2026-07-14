"""add embedding and queries

Revision ID: d2d1bb4f085f
Revises: 740fe950bbef
Create Date: 2026-07-14 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = "d2d1bb4f085f"
down_revision: Union[str, Sequence[str], None] = "740fe950bbef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("jobs", sa.Column("embedding", Vector(768), nullable=True))
    op.create_table(
        "queries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("queries")
    op.drop_column("jobs", "embedding")
