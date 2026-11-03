"""Durable independent quality labels, pilot and scan; no operator run is created.

Revision ID: 0172_symbol_readability
Revises: 0169_board_search_sequence_logs
"""

import hashlib

from alembic import op

revision = "0172_symbol_readability"
down_revision = "0169_board_search_sequence_logs"
branch_labels = None
depends_on = None

TABLES = (
    "symbol_readability_runs",
    "symbol_readability_items",
    "symbol_readability_models",
    "symbol_readability_commands",
)


def _protect(table: str) -> None:
    suffix = hashlib.sha256(table.encode("ascii")).hexdigest()[:12]
    op.execute(f"ALTER TABLE game_data_v2.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE game_data_v2.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY game_scope_v1 ON game_data_v2.{table} "
        "USING(game_id=game_data_v2.current_game_id_v1()) "
        "WITH CHECK(game_id=game_data_v2.current_game_id_v1())"
    )
    op.execute(f"""DO $parts$ DECLARE r record; child text; g record; BEGIN
      FOR r IN SELECT game_id FROM public.game_storage_locations ORDER BY game_id LOOP
        child := 'gpv2_' || left(replace(r.game_id::text,'-',''),12) || '_{suffix}';
        EXECUTE format('CREATE TABLE game_data_v2.%I PARTITION OF game_data_v2.{table} '
          'FOR VALUES IN (%L)',child,r.game_id);
        EXECUTE format('ALTER TABLE game_data_v2.%I ENABLE ROW LEVEL SECURITY',child);
        EXECUTE format('ALTER TABLE game_data_v2.%I FORCE ROW LEVEL SECURITY',child);
        EXECUTE format('CREATE POLICY game_scope_v1 ON game_data_v2.%I '
          'USING(game_id=game_data_v2.current_game_id_v1()) '
          'WITH CHECK(game_id=game_data_v2.current_game_id_v1())',child);
      END LOOP;
      FOR g IN SELECT DISTINCT a.grantee,a.privilege_type
        FROM information_schema.role_table_grants a
        WHERE a.table_schema='game_data_v2' AND a.table_name='image_symbol_review_cells'
        AND a.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE') LOOP
        EXECUTE format('GRANT %s ON game_data_v2.{table} TO %I',g.privilege_type,g.grantee);
      END LOOP;
    END $parts$""")


def _guard(version: int) -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='120s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $g$ BEGIN
      IF EXISTS(SELECT 1 FROM public.game_storage_lifecycle_operations WHERE status<>'done')
        THEN RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS'; END IF;
      IF EXISTS(SELECT 1 FROM public.game_storage_locations WHERE
        manifest_version<>'game-data-v2-manifest-v{version}' OR store_schema<>'game_data_v2')
        THEN RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED'; END IF;
    END $g$""")


def _manifest(previous: int, current: int) -> None:
    op.execute(
        "ALTER TABLE public.game_storage_locations DROP CONSTRAINT "
        f"ck_game_storage_locations_manifest_version_v{previous}"
    )
    op.execute(
        "UPDATE public.game_storage_locations SET "
        f"manifest_version='game-data-v2-manifest-v{current}',revision=revision+1,updated_at=now()"
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations ADD CONSTRAINT "
        f"ck_game_storage_locations_manifest_version_v{current} "
        f"CHECK(manifest_version='game-data-v2-manifest-v{current}')"
    )


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE public.job_type ADD VALUE IF NOT EXISTS 'symbol_readability'")
    _guard(19)
    op.execute("""CREATE TABLE game_data_v2.symbol_readability_runs (
      game_id uuid NOT NULL DEFAULT game_data_v2.current_game_id_v1(), id uuid NOT NULL,
      kind text NOT NULL CHECK(kind IN ('pilot','scan')),
      status text NOT NULL CHECK(status IN
('created','processing','completed','failed','cancelled')),
      revision integer NOT NULL DEFAULT 0 CHECK(revision>=0),
      job_id uuid NOT NULL REFERENCES public.jobs(id) ON DELETE RESTRICT,
      model_id uuid, seed text NOT NULL, inventory_fingerprint text,
      item_count integer NOT NULL DEFAULT 0 CHECK(item_count>=0),
      processed_count integer NOT NULL DEFAULT 0 CHECK(processed_count>=0 AND
processed_count<=item_count),
      receipt jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(receipt)='object'),
      error_code text,error_message text,created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(game_id,id), FOREIGN KEY(game_id) REFERENCES public.games(id) ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute("""CREATE TABLE game_data_v2.symbol_readability_items (
      game_id uuid NOT NULL DEFAULT game_data_v2.current_game_id_v1(),run_id uuid NOT NULL,
      cell_id uuid NOT NULL,source_id uuid NOT NULL,sequence_number integer NOT NULL
CHECK(sequence_number>0),
      cell_index integer NOT NULL CHECK(cell_index BETWEEN 0 AND 14),
      snapshot jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object'),identity text NOT NULL,
      revision integer NOT NULL DEFAULT 0 CHECK(revision>=0),
      state text NOT NULL DEFAULT 'pending' CHECK(state IN
        ('pending','readable','unreadable','skipped','stale','error')),
      overlap boolean,sharp boolean NOT NULL DEFAULT false,similar_readable boolean NOT NULL
DEFAULT false,
      sample_kind text NOT NULL CHECK(sample_kind IN ('pilot','audit','scan')),
      historical_unreadable boolean NOT NULL,ever_labelled boolean NOT NULL DEFAULT
false,processed boolean NOT NULL DEFAULT false,
      features jsonb,rank_margin double precision,rank_secondary double precision,
      overlap_score double precision,unreadable_score double precision,
      candidate boolean NOT NULL DEFAULT false,reasons jsonb NOT NULL DEFAULT '[]',
      PRIMARY KEY(game_id,run_id,cell_id),
      FOREIGN KEY(game_id,run_id) REFERENCES game_data_v2.symbol_readability_runs(game_id,id) ON
DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute("""CREATE TABLE game_data_v2.symbol_readability_models (
      game_id uuid NOT NULL DEFAULT game_data_v2.current_game_id_v1(),id uuid NOT NULL,
      pilot_run_id uuid NOT NULL,pilot_revision integer NOT NULL,
      job_id uuid NOT NULL REFERENCES public.jobs(id) ON DELETE RESTRICT,
      status text NOT NULL CHECK(status IN
('created','processing','completed','failed','cancelled')),
      revision integer NOT NULL DEFAULT 0 CHECK(revision>=0),fingerprint text,artifact_path text,
      report jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(report)='object'),
      accepted boolean NOT NULL DEFAULT false,error_code text,error_message text,
      PRIMARY KEY(game_id,id),
      FOREIGN KEY(game_id,pilot_run_id) REFERENCES
game_data_v2.symbol_readability_runs(game_id,id) ON DELETE RESTRICT,
      CHECK(NOT accepted OR (status='completed' AND fingerprint IS NOT NULL AND
report->>'status'='PASS'))
    ) PARTITION BY LIST(game_id)""")
    op.execute("""CREATE TABLE game_data_v2.symbol_readability_commands (
      game_id uuid NOT NULL DEFAULT game_data_v2.current_game_id_v1(),idempotency_key uuid NOT
NULL,
      command_sha256 text NOT NULL,response jsonb NOT NULL,
      PRIMARY KEY(game_id,idempotency_key),
      FOREIGN KEY(game_id) REFERENCES public.games(id) ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute(
        "CREATE INDEX ix_readability_pending_source ON game_data_v2.symbol_readability_items "
        "(game_id,run_id,processed,source_id,sequence_number,cell_index)"
    )
    op.execute(
        "CREATE INDEX ix_readability_review ON game_data_v2.symbol_readability_items "
        "(game_id,run_id,state,historical_unreadable,sequence_number,cell_index)"
    )
    for table in TABLES:
        _protect(table)
    op.execute(
        "INSERT INTO public.game_storage_table_manifest SELECT 'game-data-v2-manifest-v20',"
        "table_name,ownership,partitioned FROM public.game_storage_table_manifest "
        "WHERE manifest_version='game-data-v2-manifest-v19'"
    )
    for table in TABLES:
        op.execute(
            "INSERT INTO public.game_storage_table_manifest VALUES "
            f"('game-data-v2-manifest-v20','{table}','game',true)"
        )
    _manifest(19, 20)


def downgrade() -> None:
    _guard(20)
    op.execute("""DO $g$ BEGIN IF EXISTS(SELECT 1 FROM game_data_v2.symbol_readability_runs)
      OR EXISTS(SELECT 1 FROM public.jobs WHERE job_type::text='symbol_readability')
      THEN RAISE EXCEPTION 'READABILITY_DOWNGRADE_HAS_HISTORY'; END IF; END $g$""")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE game_data_v2.{table}")
    _manifest(20, 19)
    op.execute(
        "DELETE FROM public.game_storage_table_manifest WHERE "
        "manifest_version='game-data-v2-manifest-v20'"
    )
