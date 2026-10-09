"""Initial `incidents` table, identical to the schema the first release created with create_all().

Existing deployments created before Alembic was introduced: run `alembic stamp 0001` once, then
`alembic upgrade head`.

Revision ID: 0001
Revises:
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("repo_name", sa.String(255), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("stack_trace", sa.Text(), nullable=False),
        sa.Column("affected_file", sa.String(1024), nullable=True),
        sa.Column("root_cause_analysis", JSONType, nullable=True),
        sa.Column("suggested_patch", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("iterations", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("pr_url", sa.String(1024), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("pr_branch", sa.String(255), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_incidents_fingerprint", "incidents", ["fingerprint"])
    op.create_index("ix_incidents_repo_name", "incidents", ["repo_name"])
    op.create_index("ix_incidents_affected_file", "incidents", ["affected_file"])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_created_at", "incidents", ["created_at"])
    op.create_index("ix_incidents_repo_fingerprint", "incidents", ["repo_name", "fingerprint"])


def downgrade() -> None:
    op.drop_table("incidents")
