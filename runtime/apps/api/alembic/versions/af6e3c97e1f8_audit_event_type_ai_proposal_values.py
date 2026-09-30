"""audit_event_type_ai_proposal_values

Revision ID: af6e3c97e1f8
Revises: 61d3f32902b8
Create Date: 2026-09-01 17:37:04.173706
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'af6e3c97e1f8'
down_revision: Union[str, None] = '61d3f32902b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New AuditEventType members for Phase 10 (AI proposal layer). Same
    # convention as the Phase 9 migration (85291f408b58): SQLAlchemy's
    # native Postgres Enum stores the Python enum MEMBER NAME, not `.value`.
    for value in ("AI_PROPOSAL_REJECTED", "AI_PROPOSAL_ROUTED_TO_APPROVAL"):
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Postgres cannot drop individual enum values without recreating the
    # type — not supported here, consistent with 85291f408b58.
    pass
