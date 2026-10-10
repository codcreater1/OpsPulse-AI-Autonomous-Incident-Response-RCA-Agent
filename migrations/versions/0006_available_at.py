"""Deferred retries: `available_at` keeps a re-queued incident from being claimed before its backoff ends.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-10
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("incidents") as batch:
        batch.add_column(sa.Column("available_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("incidents") as batch:
        batch.drop_column("available_at")
