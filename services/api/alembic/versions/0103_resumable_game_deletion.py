"""Durable bounded deletion receipts and a legacy-game write fence.

No deletion or fence activation is performed by this migration. Versioned SQL
generation is deliberately frozen in game_deletion_policy_v1.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from game_predictor_api.storage.game_deletion_policy_v1 import (
    DIRECT,
    INDIRECT,
    LEGACY_ID,
    LOCK_KEY,
    OWNED,
    SPECIAL,
    owner_sql,
    quote,
)
from sqlalchemy.dialects import postgresql

revision: str = "0103_resumable_game_deletion"
down_revision: str | Sequence[str] | None = "0102_index_symbol_review_prediction_revision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game_deletion_operations",
        sa.Column("game_id", sa.Uuid(), primary_key=True),  # intentionally no games FK
        sa.Column("policy", sa.Text(), nullable=False),
        sa.Column("schema_sha256", sa.String(64), nullable=False),
        sa.Column("archive_sha256", sa.String(64), nullable=False),
        sa.Column("archive_proof", postgresql.JSONB(), nullable=False),
        sa.Column("preview_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("stage_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage_cursor", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("batch_sequence", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("deleted_counts", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("executor_xid", sa.BigInteger(), nullable=True),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("status IN ('deleting','failed','database_done')"),
        sa.CheckConstraint("stage_index >= 0 AND batch_sequence >= 0"),
    )
    op.create_table(
        "game_deletion_batches",
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("deleted_count", sa.Integer(), nullable=False),
        sa.Column("asset_references", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("game_id", "sequence"),
        sa.ForeignKeyConstraint(["game_id"], ["game_deletion_operations.game_id"]),
        sa.CheckConstraint("deleted_count >= 0"),
        sa.CheckConstraint("octet_length(asset_references::text) <= 8388608"),
    )
    op.execute(f"""
CREATE FUNCTION public.guard_game_delete_v1() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE candidate uuid; owner_id uuid; allowed_xid bigint; owner_keys uuid[];
BEGIN
  -- Both owners matter: moving a row out of a fenced game is also a write.
  owner_keys := ARRAY[]::uuid[];
  IF TG_OP <> 'INSERT' THEN
    EXECUTE format('SELECT ($1).%I',TG_ARGV[1]) INTO candidate USING OLD;
    owner_keys := array_append(owner_keys,candidate);
  END IF;
  IF TG_OP <> 'DELETE' THEN
    EXECUTE format('SELECT ($1).%I',TG_ARGV[1]) INTO candidate USING NEW;
    owner_keys := array_append(owner_keys,candidate);
  END IF;
  FOREACH candidate IN ARRAY owner_keys
  LOOP
    EXECUTE TG_ARGV[0] INTO owner_id USING candidate;
    IF owner_id = '{LEGACY_ID}'::uuid THEN
      -- An old RR snapshot must not miss a subsequently committed fence.
      IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'GAME_DELETE_ISOLATION_UNSUPPORTED' USING ERRCODE = '55000';
      END IF;
      PERFORM pg_advisory_xact_lock_shared({LOCK_KEY});
      SELECT executor_xid INTO allowed_xid
        FROM public.game_deletion_operations WHERE game_id = owner_id;
      IF FOUND AND allowed_xid IS DISTINCT FROM txid_current() THEN
        RAISE EXCEPTION 'GAME_DELETE_WRITE_FENCED' USING ERRCODE = '55000';
      END IF;
    END IF;
  END LOOP;
  IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $function$;
""")
    for table in sorted(OWNED):
        field = "game_id" if table in DIRECT else SPECIAL.get(table)
        if field is None:
            field = INDIRECT[table][0]
        expression = (
            f"SELECT {owner_sql(table, lock_parents=True)} FROM "
            f"(SELECT $1::uuid AS {quote(field)}) r"
        ).replace("'", "''")
        for event in ("INSERT", "UPDATE", "DELETE"):
            condition = ""
            if table in DIRECT or table in SPECIAL:
                tests = []
                if event != "INSERT":
                    tests.append(f"OLD.{quote(field)}='{LEGACY_ID}'::uuid")
                if event != "DELETE":
                    tests.append(f"NEW.{quote(field)}='{LEGACY_ID}'::uuid")
                condition = " WHEN (" + " OR ".join(tests) + ")"
            op.execute(
                f"CREATE TRIGGER a_game_delete_fence_{event.lower()} BEFORE {event} "
                f"ON public.{quote(table)} FOR EACH ROW{condition} EXECUTE FUNCTION "
                f"public.guard_game_delete_v1('{expression}','{field}')"
            )


def downgrade() -> None:
    op.execute("""
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM public.game_deletion_operations) THEN
   RAISE EXCEPTION 'GAME_DELETE_RECEIPTS_PREVENT_DOWNGRADE';
 END IF;
END $$;
""")
    for table in sorted(OWNED):
        for event in ("insert", "update", "delete"):
            op.execute(f"DROP TRIGGER a_game_delete_fence_{event} ON public.{quote(table)}")
    op.execute("DROP FUNCTION public.guard_game_delete_v1()")
    op.drop_table("game_deletion_batches")
    op.drop_table("game_deletion_operations")
