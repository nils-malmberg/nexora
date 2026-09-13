"""instrument fundamentals cache and portfolio target allocation

Revision ID: c3e5a7b9d1f3
Revises: b2d4f6a8c0e1
Create Date: 2026-09-14 09:00:00

- instrument_fundamentals: one cached snapshot per instrument (valuation
  ratios, analyst consensus) feeding the decision aid.
- portfolios.target_allocation: optional user-defined target by asset class,
  used to measure drift in the portfolio check-up.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3e5a7b9d1f3"
down_revision: Union[str, None] = "b2d4f6a8c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "instrument_fundamentals",
        sa.Column("instrument_id", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("data", JSON, nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("instrument_id"),
    )
    with op.batch_alter_table("portfolios") as batch:
        batch.add_column(sa.Column("target_allocation", JSON, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("portfolios") as batch:
        batch.drop_column("target_allocation")
    op.drop_table("instrument_fundamentals")
