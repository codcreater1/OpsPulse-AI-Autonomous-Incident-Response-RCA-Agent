"""Claim token: only the worker holding the current claim may renew it or write the result.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-10
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("incidents") as batch:
        batch.add_column(sa.Column("claim_token", sa.String(32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("incidents") as batch:
        batch.drop_column("claim_token")
