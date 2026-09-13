"""broker import presets and interest/fee transaction types

Revision ID: a1c3e5f7b9d2
Revises: d76f5d277546
Create Date: 2026-09-13 15:10:00

- import_jobs.preset: the broker export profile applied to a job
  (app/domain/broker_presets.py), NULL for a generic CSV.
- transactions.type check constraint: adds `interet` (cash interest) and
  `frais` (standalone fee) - internal cash movements like dividends.

Batch mode keeps the constraint change portable to SQLite (which cannot
alter constraints in place) while emitting plain ALTERs on PostgreSQL.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, None] = "d76f5d277546"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TYPES = ("achat", "vente", "dividende", "coupon", "depot", "retrait", "transfert", "split", "valorisation_privee")
NEW_TYPES = (
    "achat",
    "vente",
    "dividende",
    "coupon",
    "interet",
    "frais",
    "depot",
    "retrait",
    "transfert",
    "split",
    "valorisation_privee",
)


def _types_sql(types: tuple[str, ...]) -> str:
    return "type in (" + ", ".join(f"'{t}'" for t in types) + ")"


def upgrade() -> None:
    with op.batch_alter_table("import_jobs") as batch:
        batch.add_column(sa.Column("preset", sa.String(length=32), nullable=True))
    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("ck_transaction_type", type_="check")
        batch.create_check_constraint("ck_transaction_type", _types_sql(NEW_TYPES))


def downgrade() -> None:
    # Rows using the new types would violate the old constraint: refuse to
    # silently lose them (reverse them first, or leave the schema as is).
    conn = op.get_bind()
    count = conn.execute(sa.text("SELECT count(*) FROM transactions WHERE type IN ('interet', 'frais')")).scalar()
    if count:
        raise RuntimeError(f"{count} transaction(s) of type interet/frais exist; cannot downgrade without data loss")
    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("ck_transaction_type", type_="check")
        batch.create_check_constraint("ck_transaction_type", _types_sql(OLD_TYPES))
    with op.batch_alter_table("import_jobs") as batch:
        batch.drop_column("preset")
