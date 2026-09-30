"""audit_event_type_slack_values

Revision ID: 85291f408b58
Revises: 652aa4c821af
Create Date: 2026-09-01 17:24:57.626926
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '85291f408b58'
down_revision: Union[str, None] = '652aa4c821af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New AuditEventType members for Phase 9 (Slack scaffold). SQLAlchemy's
    # native Postgres Enum stores the Python enum MEMBER NAME (not `.value`)
    # by default — confirmed against the existing rows (GOVERNANCE_RULE_CREATED
    # etc, all upper-snake-case), so new values must follow the same
    # convention or ORM writes/reads will mismatch the stored labels.
    for value in (
        "INTEGRATION_CONNECTED",
        "INTEGRATION_DISCONNECTED",
        "INTEGRATION_TEST_SUCCEEDED",
        "INTEGRATION_TEST_FAILED",
        "SLACK_EVENT_RECEIVED",
        "SLACK_MESSAGE_SENT",
    ):
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Postgres cannot drop individual enum values without recreating the
    # type. Not supported here — consistent with how Postgres enum
    # migrations are conventionally handled; a downgrade would require a
    # full type rebuild that is out of scope for adding vocabulary.
    pass
