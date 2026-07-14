"""add job status and run stats columns

Revision ID: e3a7c9912b4d
Revises: d2d1bb4f085f
Create Date: 2026-07-14 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3a7c9912b4d"
down_revision: Union[str, Sequence[str], None] = "d2d1bb4f085f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("status", sa.String(20), server_default="parsed", nullable=False))
    op.add_column("jobs", sa.Column("scrape_run_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_jobs_scrape_run_id", "jobs", "scrape_runs", ["scrape_run_id"], ["id"])

    op.add_column("scrape_runs", sa.Column("categories", sa.JSON(), nullable=True))
    op.add_column("scrape_runs", sa.Column("pages_scraped", sa.Integer(), server_default="0", nullable=False))
    op.add_column("scrape_runs", sa.Column("errors", sa.JSON(), nullable=True))
    op.add_column("scrape_runs", sa.Column("jobs_embedded", sa.Integer(), server_default="0", nullable=False))
    op.add_column("scrape_runs", sa.Column("jobs_matched", sa.Integer(), server_default="0", nullable=False))
    op.add_column("scrape_runs", sa.Column("jobs_notified", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("scrape_runs", "jobs_notified")
    op.drop_column("scrape_runs", "jobs_matched")
    op.drop_column("scrape_runs", "jobs_embedded")
    op.drop_column("scrape_runs", "errors")
    op.drop_column("scrape_runs", "pages_scraped")
    op.drop_column("scrape_runs", "categories")

    op.drop_constraint("fk_jobs_scrape_run_id", "jobs", type_="foreignkey")
    op.drop_column("jobs", "scrape_run_id")
    op.drop_column("jobs", "status")