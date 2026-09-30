"""approval_executed_and_action_audit_values

Revision ID: 35bf4318c3d9
Revises: af6e3c97e1f8
Create Date: 2026-09-05 15:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '35bf4318c3d9'
down_revision: Union[str, None] = 'af6e3c97e1f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New ApprovalRequestStatus member: an approved request that has actually
    # been executed through the canonical execute_action path. Same
    # native-enum-add-value pattern as every prior migration in this file.
    op.execute("ALTER TYPE approval_request_status ADD VALUE IF NOT EXISTS 'EXECUTED'")

    # New AuditEventType members for the approval -> execution wiring.
    for value in ("ACTION_EXECUTED", "ACTION_BLOCKED", "ACTION_FAILED"):
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'")

    # Traceability columns for the moment an approved request is actually
    # executed. Nullable: most existing rows (and any APPROVED-but-not-yet-run
    # request) have none of these set.
    op.add_column(
        "approval_requests",
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "approval_requests",
        sa.Column("execution_outcome", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "approval_requests",
        sa.Column("execution_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("approval_requests", "execution_reason")
    op.drop_column("approval_requests", "execution_outcome")
    op.drop_column("approval_requests", "executed_at")
    # Postgres cannot drop individual enum values without recreating the
    # type — not supported here, consistent with every prior enum-value
    # migration in this file (85291f408b58, af6e3c97e1f8).
    pass
