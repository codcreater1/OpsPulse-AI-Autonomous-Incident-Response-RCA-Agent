"""Add incidents.error_category and the remediation_approvals table (human approval before PR creation).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("incidents") as batch:
        batch.add_column(sa.Column("error_category", sa.String(64), nullable=True))
        batch.create_index("ix_incidents_error_category", ["error_category"])

    op.create_table(
        "remediation_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("target_file", sa.String(1024), nullable=False),
        sa.Column("patch_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reviewer", sa.String(200), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_remediation_approvals_incident_id", "remediation_approvals", ["incident_id"])
    op.create_index("ix_remediation_approvals_status", "remediation_approvals", ["status"])


def downgrade() -> None:
    op.drop_table("remediation_approvals")
    with op.batch_alter_table("incidents") as batch:
        batch.drop_index("ix_incidents_error_category")
        batch.drop_column("error_category")
