"""Exact planned source replacement and retained human decision chronology."""

import hashlib

from alembic import op

revision = "0174_source_replacement"
down_revision = "0173_merge_quality_corrections"
branch_labels = depends_on = None
TABLES = (
    "source_replacement_batches",
    "source_replacement_entries",
    "source_replacement_slots",
    "source_replacement_retired",
    "source_replacement_commands",
    "symbol_readability_decisions",
    "source_replacement_sources",
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
    _guard(20)
    op.execute(
        """
CREATE TABLE game_data_v2.source_replacement_batches (game_id uuid NOT NULL
DEFAULT game_data_v2.current_game_id_v1() REFERENCES public.games(id) ON
DELETE RESTRICT, id uuid NOT NULL, revision integer NOT NULL
CHECK(revision>=1), status text NOT NULL CHECK(status IN ('planned',
'cancelled', 'gap_open', 'replacement_staged', 'importing',
'awaiting_review', 'restored')), preview_token text NOT NULL
CHECK(preview_token ~ '^[0-9a-f]{64}$'), document jsonb NOT NULL
CHECK(jsonb_typeof(document)='object'), created_at timestamptz NOT NULL
DEFAULT now(), PRIMARY KEY(game_id, id)) PARTITION BY LIST(game_id)
"""
    )
    op.execute(
        """
CREATE TABLE game_data_v2.source_replacement_entries (game_id uuid NOT NULL
DEFAULT game_data_v2.current_game_id_v1() REFERENCES public.games(id) ON
DELETE RESTRICT, id uuid NOT NULL, batch_id uuid NOT NULL, source_id uuid
NOT NULL, source_sha256 text NOT NULL CHECK(source_sha256 ~
'^[0-9a-f]{64}$'), revision integer NOT NULL DEFAULT 1 CHECK(revision>=1),
phase text NOT NULL DEFAULT 'planned' CHECK(phase IN ('planned',
'cancelled', 'gap_open', 'replacement_staged', 'importing',
'awaiting_review', 'restored')), failure_code text, document jsonb NOT NULL
CHECK(jsonb_typeof(document)='object'), PRIMARY KEY(game_id, id),
UNIQUE(game_id, batch_id, source_id), FOREIGN KEY(game_id, batch_id)
REFERENCES game_data_v2.source_replacement_batches(game_id, id) ON DELETE
RESTRICT, FOREIGN KEY(game_id, source_id) REFERENCES
game_data_v2.source_images(game_id, id) ON DELETE RESTRICT) PARTITION BY
LIST(game_id)
"""
    )
    op.execute(
        """
CREATE TABLE game_data_v2.source_replacement_slots (game_id uuid NOT NULL
DEFAULT game_data_v2.current_game_id_v1() REFERENCES public.games(id) ON
DELETE RESTRICT, sequence_number bigint NOT NULL CHECK(sequence_number>0),
entry_id uuid NOT NULL, batch_id uuid NOT NULL, state text NOT NULL
CHECK(state IN ('reserved', 'pending_bound')), new_source_id uuid,
new_sha256 text CHECK(new_sha256 IS NULL OR new_sha256 ~ '^[0-9a-f]{64}$'),
bound_review_id uuid, revision integer NOT NULL CHECK(revision>=1), document
jsonb NOT NULL CHECK(jsonb_typeof(document)='object'), PRIMARY KEY(game_id,
sequence_number), FOREIGN KEY(game_id, entry_id) REFERENCES
game_data_v2.source_replacement_entries(game_id, id) ON DELETE RESTRICT,
FOREIGN KEY(game_id, batch_id) REFERENCES
game_data_v2.source_replacement_batches(game_id, id) ON DELETE RESTRICT)
PARTITION BY LIST(game_id)
"""
    )
    op.execute(
        """
CREATE TABLE game_data_v2.source_replacement_retired (game_id uuid NOT NULL
DEFAULT game_data_v2.current_game_id_v1() REFERENCES public.games(id) ON
DELETE RESTRICT, source_id uuid NOT NULL, entry_id uuid NOT NULL,
source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[0-9a-f]{64}$'),
document jsonb NOT NULL CHECK(jsonb_typeof(document)='object'), retired_at
timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(game_id, source_id), FOREIGN
KEY(game_id, source_id) REFERENCES game_data_v2.source_images(game_id, id)
ON DELETE RESTRICT, FOREIGN KEY(game_id, entry_id) REFERENCES
game_data_v2.source_replacement_entries(game_id, id) ON DELETE RESTRICT)
PARTITION BY LIST(game_id)
"""
    )
    op.execute(
        """
CREATE TABLE game_data_v2.source_replacement_commands (game_id uuid NOT NULL
DEFAULT game_data_v2.current_game_id_v1() REFERENCES public.games(id) ON
DELETE RESTRICT, idempotency_key uuid NOT NULL, command_sha256 text NOT NULL
CHECK(command_sha256 ~ '^[0-9a-f]{64}$'), batch_id uuid NOT NULL, response
jsonb NOT NULL CHECK(jsonb_typeof(response)='object'), PRIMARY KEY(game_id,
idempotency_key), FOREIGN KEY(game_id, batch_id) REFERENCES
game_data_v2.source_replacement_batches(game_id, id) ON DELETE RESTRICT)
PARTITION BY LIST(game_id)
"""
    )
    op.execute(
        """
CREATE TABLE game_data_v2.symbol_readability_decisions (game_id uuid NOT
NULL DEFAULT game_data_v2.current_game_id_v1() REFERENCES public.games(id)
ON DELETE RESTRICT, cell_id uuid NOT NULL, ordinal bigint NOT NULL
CHECK(ordinal>0), idempotency_key uuid NOT NULL, run_id uuid NOT NULL,
item_revision integer NOT NULL CHECK(item_revision>0), identity text NOT
NULL CHECK(identity ~ '^[0-9a-f]{64}$'), state text NOT NULL CHECK(state IN
('pending', 'readable', 'unreadable', 'skipped')), overlap boolean, snapshot
jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object'), created_at
timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(game_id, cell_id, ordinal),
UNIQUE(game_id, idempotency_key, cell_id), FOREIGN KEY(game_id, run_id)
REFERENCES game_data_v2.symbol_readability_runs(game_id, id) ON DELETE
RESTRICT) PARTITION BY LIST(game_id)
"""
    )
    op.execute("""
CREATE TABLE game_data_v2.source_replacement_sources (       game_id uuid
NOT NULL DEFAULT game_data_v2.current_game_id_v1(),        entry_id uuid NOT
NULL, source_id uuid NOT NULL,        PRIMARY KEY(game_id, entry_id,
source_id),        FOREIGN KEY(game_id, entry_id) REFERENCES
game_data_v2.source_replacement_entries(game_id, id) ON DELETE RESTRICT,
FOREIGN KEY(game_id, source_id) REFERENCES
game_data_v2.source_images(game_id, id) ON DELETE RESTRICT     ) PARTITION
BY LIST(game_id)
""")
    op.execute("""
ALTER TABLE game_data_v2.source_replacement_entries       ADD CONSTRAINT
uq_replacement_entry_batch UNIQUE(game_id, batch_id, id)
""")
    op.execute("""
ALTER TABLE game_data_v2.source_replacement_slots       ADD CONSTRAINT
fk_replacement_slot_entry_batch FOREIGN KEY(game_id, batch_id, entry_id)
REFERENCES game_data_v2.source_replacement_entries(game_id, batch_id, id) ON
DELETE RESTRICT,        ADD CONSTRAINT fk_replacement_slot_new_source
FOREIGN KEY(game_id, new_source_id)         REFERENCES
game_data_v2.source_images(game_id, id) ON DELETE RESTRICT,        ADD
CONSTRAINT fk_replacement_slot_review FOREIGN KEY(game_id, bound_review_id)
REFERENCES game_data_v2.image_review_items(game_id, id) ON DELETE RESTRICT
""")
    op.execute(
        """
CREATE INDEX ix_replacement_entry_batch ON
game_data_v2.source_replacement_entries(game_id, batch_id)
"""
    )
    op.execute(
        """
CREATE INDEX ix_replacement_retired_sha ON
game_data_v2.source_replacement_retired(game_id, source_sha256)
"""
    )
    op.execute(
        """
CREATE INDEX ix_readability_decisive ON
game_data_v2.symbol_readability_decisions(game_id, cell_id, identity,
ordinal DESC) WHERE state IN ('readable', 'unreadable')
"""
    )
    op.execute(
        """
CREATE FUNCTION game_data_v2.replacement_immutable_v1() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'SOURCE_REPLACEMENT_IMMUTABLE';
END $$
"""
    )
    for table in (
        "symbol_readability_decisions",
        "source_replacement_commands",
        "source_replacement_retired",
    ):
        op.execute(
            f"CREATE TRIGGER replacement_immutable BEFORE UPDATE OR DELETE ON game_data_v2.{table} "
            "FOR EACH ROW EXECUTE FUNCTION game_data_v2.replacement_immutable_v1()"
        )
    for table in TABLES:
        _protect(table)
    op.execute(
        """
INSERT INTO public.game_storage_table_manifest SELECT
'game-data-v2-manifest-v21', table_name, ownership, partitioned FROM
public.game_storage_table_manifest WHERE
manifest_version='game-data-v2-manifest-v20'
"""
    )
    for table in TABLES:
        op.execute(
            "INSERT INTO public.game_storage_table_manifest VALUES "
            f"('game-data-v2-manifest-v21','{table}','game',true)"
        )
    _manifest(20, 21)


def downgrade() -> None:
    _guard(21)
    for table in TABLES:
        op.execute(
            f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM game_data_v2.{table}) "
            "THEN RAISE EXCEPTION 'SOURCE_REPLACEMENT_HAS_HISTORY'; END IF; END $$"
        )
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE game_data_v2.{table}")
    op.execute("DROP FUNCTION game_data_v2.replacement_immutable_v1()")
    _manifest(21, 20)
    op.execute(
        """
DELETE FROM public.game_storage_table_manifest WHERE
manifest_version='game-data-v2-manifest-v21'
"""
    )
