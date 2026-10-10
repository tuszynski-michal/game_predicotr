"""Immutable reviewed-pilot activation registry; no gate is enabled by migration."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0145_v7_pilot_acceptances"
down_revision: str | Sequence[str] | None = "0144_v7_reviewed_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
_TABLE = "semi_automatic_selection_v7_pilot_acceptances"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("operation_id", sa.Uuid(), primary_key=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("receipt_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("receipt", postgresql.JSONB(), nullable=False),
        sa.Column("expected_generation", sa.BigInteger(), nullable=False),
        sa.Column("resulting_generation", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "expected_generation >= 0 AND resulting_generation = expected_generation + 1",
            name="ck_v7_pilot_acceptance_generation",
        ),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$' AND receipt_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_v7_pilot_acceptance_fingerprints",
        ),
        schema="public",
    )
    op.execute("""
        CREATE FUNCTION public.v7_pilot_acceptance_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'V7 pilot acceptance receipts are immutable';
        END $$
    """)
    op.execute(f"""
        CREATE TRIGGER v7_pilot_acceptance_immutable
        BEFORE UPDATE OR DELETE ON public.{_TABLE}
        FOR EACH ROW EXECUTE FUNCTION public.v7_pilot_acceptance_immutable()
    """)
    op.execute(f"""
        CREATE TRIGGER v7_pilot_acceptance_no_truncate
        BEFORE TRUNCATE ON public.{_TABLE}
        FOR EACH STATEMENT EXECUTE FUNCTION public.v7_pilot_acceptance_immutable()
    """)


def downgrade() -> None:
    if op.get_bind().execute(sa.text(f"SELECT EXISTS(SELECT 1 FROM public.{_TABLE})")).scalar():
        raise RuntimeError("Cannot downgrade immutable V7 pilot acceptance receipts.")
    op.execute(f"DROP TRIGGER v7_pilot_acceptance_no_truncate ON public.{_TABLE}")
    op.execute(f"DROP TRIGGER v7_pilot_acceptance_immutable ON public.{_TABLE}")
    op.execute("DROP FUNCTION public.v7_pilot_acceptance_immutable()")
    op.drop_table(_TABLE, schema="public")
