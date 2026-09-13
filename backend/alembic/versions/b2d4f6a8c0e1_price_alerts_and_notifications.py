"""informational price alerts and in-app notifications

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
Create Date: 2026-09-13 18:00:00

- price_alerts: a user-defined threshold on one instrument (price above /
  below, absolute daily move), one-shot, evaluated from cached observations.
- notifications: the in-app message written when an alert triggers.
Both are "inform, never act" (specs/ROADMAP.md « alertes informatives »).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b2d4f6a8c0e1"
down_revision: Union[str, None] = "a1c3e5f7b9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("instrument_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_value", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.CheckConstraint("kind in ('price_above', 'price_below', 'move_pct')", name="ck_alert_kind"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_price_alerts_instrument_id"), "price_alerts", ["instrument_id"], unique=False)
    op.create_index(op.f("ix_price_alerts_user_id"), "price_alerts", ["user_id"], unique=False)
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("instrument_id", sa.String(length=32), nullable=True),
        sa.Column("alert_id", sa.String(length=32), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["alert_id"], ["price_alerts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_user_created", "notifications", ["user_id", "created_at"], unique=False)
    op.create_index(op.f("ix_notifications_instrument_id"), "notifications", ["instrument_id"], unique=False)
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_instrument_id"), table_name="notifications")
    op.drop_index("ix_notification_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_price_alerts_user_id"), table_name="price_alerts")
    op.drop_index(op.f("ix_price_alerts_instrument_id"), table_name="price_alerts")
    op.drop_table("price_alerts")
