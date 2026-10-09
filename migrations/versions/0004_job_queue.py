"""Durable job queue on the incidents table: claim attempts and lease expiry.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("incidents") as batch:
        batch.add_column(sa.Column("job_attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_incidents_status_created", ["status", "created_at"])


def downgrade() -> None:
    with op.batch_alter_table("incidents") as batch:
        batch.drop_index("ix_incidents_status_created")
        batch.drop_column("lease_expires_at")
        batch.drop_column("job_attempts")
