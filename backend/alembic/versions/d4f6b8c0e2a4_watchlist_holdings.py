"""watchlist items carry an optional 'held' note (entry price, date, quantity)

Revision ID: d4f6b8c0e2a4
Revises: c3e5a7b9d1f3
Create Date: 2026-09-14 12:00:00

Since the pivot to market analysis the watchlist replaces portfolio
bookkeeping for the decision aid: "I hold this at that price" is enough to
frame sell-or-hold readings.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d4f6b8c0e2a4"
down_revision: Union[str, None] = "c3e5a7b9d1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("watchlist_items") as batch:
        batch.add_column(sa.Column("held", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("entry_price", sa.Numeric(precision=20, scale=6), nullable=True))
        batch.add_column(sa.Column("entry_date", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=True))
        batch.add_column(sa.Column("note", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("watchlist_items") as batch:
        for column in ("note", "quantity", "entry_date", "entry_price", "held"):
            batch.drop_column(column)
