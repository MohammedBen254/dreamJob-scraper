"""add ocr_results to jobs

Revision ID: f1a8c390d72e
Revises: d520eab54f65
Create Date: 2026-07-14 17:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a8c390d72e"
down_revision: Union[str, Sequence[str], None] = "d520eab54f65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("ocr_results", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "ocr_results")
