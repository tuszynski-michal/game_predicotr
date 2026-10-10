"""Super game series, their derivation state and audit (TASK-0933, D-535).

Revision ID: 0152_super_game_series
Revises: 0151_super_game_roles

Adds four game-partitioned tables to ``game_data_v2`` and the frozen storage
manifest v6:

- ``super_game_series``: the published series of a game; identity
  ``(game_id, trigger_sequence_number)``; the operator's super symbol with a
  compare-and-set ``revision``;
- ``super_game_series_generation_rows``: working rows of an unpublished
  generation, written in batches and swapped in one final transaction;
- ``super_game_derivation_state``: the per-game input counter
  ``input_version`` and the input version of the published generation;
  staleness is always derived from the two, never stored;
- ``super_game_series_audit_events``: super symbol changes and removed series.

Existing game stores receive empty protected partitions and move to manifest
v6. The new job type ``super_game_series_derive`` (lane ``general``) is added
to the ``job_type`` enum. No existing data is rewritten. Downgrade refuses
while operator decisions (a defined super symbol or an audit event) exist;
derived rows are reproducible and are dropped with their tables.
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from game_predictor_api.storage.game_data_v2_manifest_v6 import (
    ADDED_GAME_TABLES,
    CATALOG,
    CONTROL_TABLES,
    GAME_TABLES,
    SHARED,
    ownership,
)

revision: str = "0152_super_game_series"
down_revision: str | Sequence[str] | None = "0151_super_game_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

V5 = "game-data-v2-manifest-v5"
V6 = "game-data-v2-manifest-v6"
JOB_TYPE = "super_game_series_derive"
SERIES = "super_game_series"
GENERATION_ROWS = "super_game_series_generation_rows"
STATE = "super_game_derivation_state"
AUDIT = "super_game_series_audit_events"
_SERIES_CHECKS = """
        CONSTRAINT ck_{prefix}_positions CHECK (
            trigger_sequence_number BETWEEN 1 AND 10000000
            AND start_sequence_number = trigger_sequence_number + 1
            AND length BETWEEN 1 AND 10000000),
        CONSTRAINT ck_{prefix}_completeness CHECK (completeness IN ('complete','incomplete')),
        CONSTRAINT ck_{prefix}_run_verification CHECK (
            run_verification IN ('verified','unverified')),
        CONSTRAINT ck_{prefix}_retriggers CHECK (
            array_ndims(retrigger_sequence_numbers) IS NULL
            OR array_ndims(retrigger_sequence_numbers) = 1)"""


def _suffix(table: str) -> str:
    return hashlib.sha256(table.encode("ascii")).hexdigest()[:12]


def _guard() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_lifecycle_operations
                   WHERE status <> 'done') THEN
            RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS';
        END IF;
        IF EXISTS (SELECT 1 FROM public.game_storage_locations
                   WHERE status NOT IN ('active','blocked')) THEN
            RAISE EXCEPTION 'GAME_STORAGE_LOCATION_BUSY';
        END IF;
    END $guard$""")


def _protect(table: str) -> None:
    op.execute(f"ALTER TABLE game_data_v2.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE game_data_v2.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY game_scope_v1 ON game_data_v2.{table} "
        "USING(game_id = game_data_v2.current_game_id_v1()) "
        "WITH CHECK(game_id = game_data_v2.current_game_id_v1())"
    )
    op.execute(f"""DO $partitions$ DECLARE location record; child text; BEGIN
        FOR location IN SELECT game_id FROM public.game_storage_locations ORDER BY game_id LOOP
            child := 'gpv2_' || left(replace(location.game_id::text,'-',''),12)
                || '_{_suffix(table)}';
            EXECUTE format('CREATE TABLE game_data_v2.%I '
                'PARTITION OF game_data_v2.{table} FOR VALUES IN (%L)',child,location.game_id);
            EXECUTE format('ALTER TABLE game_data_v2.%I ENABLE ROW LEVEL SECURITY',child);
            EXECUTE format('ALTER TABLE game_data_v2.%I FORCE ROW LEVEL SECURITY',child);
            EXECUTE format('CREATE POLICY game_scope_v1 ON game_data_v2.%I '
                'USING(game_id = game_data_v2.current_game_id_v1()) '
                'WITH CHECK(game_id = game_data_v2.current_game_id_v1())',child);
            EXECUTE format('ALTER TABLE game_data_v2.%I SET '
                '(autovacuum_vacuum_scale_factor = 0.02, '
                'autovacuum_analyze_scale_factor = 0.01)',child);
        END LOOP;
    END $partitions$""")


def upgrade() -> None:
    _guard()
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_locations
                   WHERE manifest_version <> '{V5}' OR store_schema <> 'game_data_v2') THEN
            RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED';
        END IF;
    END $guard$""")
    # Not used in this transaction; the worker claim query needs the label.
    op.execute(f"ALTER TYPE job_type ADD VALUE IF NOT EXISTS '{JOB_TYPE}'")
    op.execute(f"""CREATE TABLE game_data_v2.{SERIES} (
        game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1(),
        id UUID NOT NULL,
        trigger_sequence_number INTEGER NOT NULL,
        start_sequence_number INTEGER NOT NULL,
        length INTEGER NOT NULL,
        retrigger_sequence_numbers INTEGER[] NOT NULL DEFAULT '{{}}',
        completeness VARCHAR(20) NOT NULL,
        run_verification VARCHAR(20) NOT NULL,
        super_symbol_id UUID,
        defined_by VARCHAR(200),
        defined_at TIMESTAMP WITH TIME ZONE,
        revision INTEGER NOT NULL DEFAULT 0,
        generation_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT v2_pk_super_game_series PRIMARY KEY (game_id,id),
        CONSTRAINT uq_super_game_series_trigger UNIQUE (game_id,trigger_sequence_number),
        {_SERIES_CHECKS.format(prefix="super_game_series")},
        CONSTRAINT ck_super_game_series_definition CHECK (
            (defined_by IS NULL) = (defined_at IS NULL)
            AND (super_symbol_id IS NULL OR defined_by IS NOT NULL)),
        CONSTRAINT ck_super_game_series_revision CHECK (revision >= 0),
        CONSTRAINT v2_owner_super_game_series FOREIGN KEY(game_id)
            REFERENCES public.games(id) ON DELETE RESTRICT,
        CONSTRAINT v2_fk_super_game_series_symbol FOREIGN KEY(game_id,super_symbol_id)
            REFERENCES public.symbols(game_id,id) ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.{GENERATION_ROWS} (
        game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1(),
        generation_id UUID NOT NULL,
        trigger_sequence_number INTEGER NOT NULL,
        start_sequence_number INTEGER NOT NULL,
        length INTEGER NOT NULL,
        retrigger_sequence_numbers INTEGER[] NOT NULL DEFAULT '{{}}',
        completeness VARCHAR(20) NOT NULL,
        run_verification VARCHAR(20) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT v2_pk_super_game_generation_rows
            PRIMARY KEY (game_id,generation_id,trigger_sequence_number),
        {_SERIES_CHECKS.format(prefix="super_game_generation_rows")},
        CONSTRAINT v2_owner_super_game_generation_rows FOREIGN KEY(game_id)
            REFERENCES public.games(id) ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.{STATE} (
        game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1(),
        input_version BIGINT NOT NULL DEFAULT 0,
        current_generation_id UUID,
        input_version_of_generation BIGINT,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT v2_pk_super_game_derivation_state PRIMARY KEY (game_id),
        CONSTRAINT ck_super_game_derivation_state_versions CHECK (
            input_version >= 0
            AND (current_generation_id IS NULL) = (input_version_of_generation IS NULL)
            AND (input_version_of_generation IS NULL
                 OR input_version_of_generation BETWEEN 0 AND input_version)),
        CONSTRAINT v2_owner_super_game_derivation_state FOREIGN KEY(game_id)
            REFERENCES public.games(id) ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.{AUDIT} (
        game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1(),
        id UUID NOT NULL,
        series_id UUID NOT NULL,
        trigger_sequence_number INTEGER NOT NULL,
        event_kind VARCHAR(30) NOT NULL,
        previous_super_symbol_id UUID,
        super_symbol_id UUID,
        previous_revision INTEGER,
        revision INTEGER,
        generation_id UUID,
        actor VARCHAR(200) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT v2_pk_super_game_series_audit PRIMARY KEY (game_id,id),
        CONSTRAINT ck_super_game_series_audit_kind CHECK (
            event_kind IN ('super_symbol_defined','series_removed')),
        CONSTRAINT ck_super_game_series_audit_shape CHECK (
            trigger_sequence_number >= 1 AND length(btrim(actor)) > 0
            AND (event_kind <> 'super_symbol_defined'
                 OR (previous_revision IS NOT NULL AND revision = previous_revision + 1))
            AND (event_kind <> 'series_removed'
                 OR (generation_id IS NOT NULL AND super_symbol_id IS NULL))),
        CONSTRAINT v2_owner_super_game_series_audit FOREIGN KEY(game_id)
            REFERENCES public.games(id) ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute(
        f"CREATE INDEX ix_super_game_series_audit_series ON game_data_v2.{AUDIT} "
        "(game_id,series_id,created_at,id)"
    )
    for table in ADDED_GAME_TABLES:
        _protect(table)
    manifest = sa.table(
        "game_storage_table_manifest",
        sa.column("manifest_version", sa.Text()),
        sa.column("table_name", sa.Text()),
        sa.column("ownership", sa.Text()),
        sa.column("partitioned", sa.Boolean()),
        schema="public",
    )
    op.bulk_insert(
        manifest,
        [
            {
                "manifest_version": V6,
                "table_name": table,
                "ownership": ownership(table),
                "partitioned": table in GAME_TABLES,
            }
            for table in sorted(CATALOG | SHARED | set(GAME_TABLES) | set(CONTROL_TABLES))
        ],
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations "
        "DROP CONSTRAINT ck_game_storage_locations_manifest_version_v5"
    )
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version = '{V6}',"
        f"revision = revision + 1,updated_at = now() WHERE manifest_version = '{V5}'"
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations "
        f"ADD CONSTRAINT ck_game_storage_locations_manifest_version_v6 "
        f"CHECK(manifest_version = '{V6}')"
    )


def downgrade() -> None:
    _guard()
    # FORCE RLS must never make a non-empty table look empty. A role without
    # BYPASSRLS fails here rather than silently dropping operator decisions.
    op.execute("SET LOCAL row_security = off")
    for table in ADDED_GAME_TABLES:
        op.execute(f"LOCK TABLE game_data_v2.{table} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM game_data_v2.{SERIES} WHERE defined_by IS NOT NULL)
           OR EXISTS (SELECT 1 FROM game_data_v2.{AUDIT}) THEN
            RAISE EXCEPTION 'SUPER_GAME_SERIES_DOWNGRADE_HAS_DECISIONS';
        END IF;
        IF EXISTS (SELECT 1 FROM public.jobs WHERE job_type::text = '{JOB_TYPE}'
                   AND status IN ('created','processing')) THEN
            RAISE EXCEPTION 'SUPER_GAME_SERIES_DOWNGRADE_JOB_ACTIVE';
        END IF;
        IF EXISTS (SELECT 1 FROM public.game_storage_locations
                   WHERE manifest_version <> '{V6}') THEN
            RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED';
        END IF;
    END $guard$""")
    for table in (AUDIT, GENERATION_ROWS, SERIES, STATE):
        op.execute(f"DROP TABLE game_data_v2.{table}")
    op.execute(
        "ALTER TABLE public.game_storage_locations "
        "DROP CONSTRAINT ck_game_storage_locations_manifest_version_v6"
    )
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version = '{V5}',"
        f"revision = revision + 1,updated_at = now() WHERE manifest_version = '{V6}'"
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations "
        f"ADD CONSTRAINT ck_game_storage_locations_manifest_version_v5 "
        f"CHECK(manifest_version = '{V5}')"
    )
    op.execute(f"DELETE FROM public.game_storage_table_manifest WHERE manifest_version = '{V6}'")
    # PostgreSQL enums cannot drop a label safely; the unused label is kept
    # (precedent 0083). Unfinished derive jobs are left to the operator.
