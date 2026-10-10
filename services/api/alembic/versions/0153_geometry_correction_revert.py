"""Revert of the last manual grid-geometry correction (TASK-0945, plan D-538).

Revision ID: 0153_geometry_correction_revert
Revises: 0152_super_game_series

Schema of the geometry correction revert and of the rejected deferred slot:

- ``image_source_geometry_revisions.status`` gains ``reverted``. A reverted
  revision stays (append-only history, its id is referenced by events) but is
  never the current revision; the checksum uniqueness becomes a partial unique
  index over the non-reverted rows, so saving the same geometry again after a
  revert appends a new revision instead of resurrecting the reverted one;
- ``image_board_geometry_review_events.action`` and
  ``image_symbol_review_events.action`` gain ``geometry_reverted``;
- ``image_symbol_review_events.previous_assignment_source`` (nullable, the
  cell ``assignment_source`` vocabulary) is written by every new cell event;
- ``image_board_geometry_pending`` gains the ``rejected`` status with its
  reason, note, time and actor (W7; the write logic belongs to TASK-0949);
- the new game table ``image_geometry_correction_reverts`` keeps one
  append-only audit row with a checksummed snapshot of the deleted rows per
  revert. It has no foreign key to the deleted rows;
- the new game table ``image_board_geometry_pending_events`` keeps the durable,
  append-only identity of every rejection of a deferred slot and of its revert
  (TASK-0949): the idempotency key, the command checksum, the per-slot
  ``rejection_revision`` and the actor. A slot row forgets its rejection when
  the rejection is reverted (lifecycle CHECK); the events keep it, so retries
  replay the stored result and a stale revert cannot undo a newer rejection.
  A replacement photo that takes the sequence of a rejected slot over writes a
  ``superseded`` event with its successor review item (TASK-0950).
  Both new tables move the game stores to the frozen storage manifest v7.

No existing row is rewritten. Downgrade refuses while any revert history,
rejection or ``previous_assignment_source`` value exists (no silent loss).
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from game_predictor_api.storage.game_data_v2_manifest_v7 import (
    ADDED_GAME_TABLES,
    CATALOG,
    CONTROL_TABLES,
    GAME_TABLES,
    SHARED,
    ownership,
)

revision: str = "0153_geometry_correction_revert"
down_revision: str | Sequence[str] | None = "0152_super_game_series"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

V6 = "game-data-v2-manifest-v6"
V7 = "game-data-v2-manifest-v7"
AUDIT = "image_geometry_correction_reverts"
PENDING_EVENTS = "image_board_geometry_pending_events"
SOURCE_REVISIONS = "game_data_v2.image_source_geometry_revisions"
PENDING = "game_data_v2.image_board_geometry_pending"
BOARD_EVENTS = "game_data_v2.image_board_geometry_review_events"
CELL_EVENTS = "game_data_v2.image_symbol_review_events"
# Frozen name of the full checksum uniqueness (alembic/sql/game_data_v2_schema_v1.sql).
SOURCE_CHECKSUM_UNIQUE = "v2_uq_fd29b81bdd3878e81e86"
SOURCE_LIVE_CHECKSUM_INDEX = "v2_uq_source_geometry_revisions_live_checksum"

_SOURCE_STATE = (
    "geometry_source IN ('auto','manual','backfill') "
    "AND status IN ('pending','accepted','needs_review','rejected'{extra}) "
    "AND (processing_time_ms IS NULL OR processing_time_ms >= 0) "
    "AND length(btrim(created_by)) > 0"
)
_BOARD_EVENT_ACTIONS = "action IN ('approved','geometry_saved','backfilled'{extra})"
_CELL_EVENT_ACTIONS = (
    "action IN ('approve','reassign','mark_grid_issue','mark_blurry','mark_unreadable',"
    "'board_synchronized','geometry_invalidated'{extra})"
)
_PENDING_STATUS = "status IN ('pending','resolved','superseded'{extra})"
_PENDING_LIFECYCLE_V1 = (
    "(status = 'pending' AND resolved_geometry_revision IS NULL "
    "AND resolved_at IS NULL AND superseded_at IS NULL) OR "
    "(status = 'resolved' AND resolved_geometry_revision IS NOT NULL "
    "AND resolved_geometry_revision > expected_geometry_revision "
    "AND resolved_at IS NOT NULL AND superseded_at IS NULL) OR "
    "(status = 'superseded' AND resolved_geometry_revision IS NULL "
    "AND resolved_at IS NULL AND superseded_at IS NOT NULL)"
)
# A rejected slot may later be superseded by a replacement import (TASK-0950)
# and then keeps its rejection as history; open and resolved slots never carry one.
_PENDING_LIFECYCLE_V2 = (
    "(status = 'pending' AND resolved_geometry_revision IS NULL "
    "AND resolved_at IS NULL AND superseded_at IS NULL AND rejected_at IS NULL) OR "
    "(status = 'resolved' AND resolved_geometry_revision IS NOT NULL "
    "AND resolved_geometry_revision > expected_geometry_revision "
    "AND resolved_at IS NOT NULL AND superseded_at IS NULL AND rejected_at IS NULL) OR "
    "(status = 'superseded' AND resolved_geometry_revision IS NULL "
    "AND resolved_at IS NULL AND superseded_at IS NOT NULL) OR "
    "(status = 'rejected' AND resolved_geometry_revision IS NULL "
    "AND resolved_at IS NULL AND superseded_at IS NULL AND rejected_at IS NOT NULL)"
)
_PENDING_REJECTION = (
    "(rejection_reason IS NULL OR rejection_reason IN ('cropped','blurred','other')) "
    "AND (rejection_reason IS NULL) = (rejected_at IS NULL) "
    "AND (rejected_at IS NULL) = (rejected_by IS NULL) "
    "AND (rejected_by IS NULL OR length(btrim(rejected_by)) > 0) "
    "AND (rejection_note IS NULL OR (rejection_reason IS NOT NULL "
    "AND length(btrim(rejection_note)) BETWEEN 1 AND 1000)) "
    "AND (rejection_reason IS DISTINCT FROM 'other' OR rejection_note IS NOT NULL)"
)
_ASSIGNMENT_SOURCES = "('model','human','board_decision','backfill','geometry_partial')"


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


def _replace_check(table: str, name: str, expression: str) -> None:
    op.execute(
        f"ALTER TABLE {table} DROP CONSTRAINT {name}, ADD CONSTRAINT {name} CHECK ({expression})"
    )


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
                   WHERE manifest_version <> '{V6}' OR store_schema <> 'game_data_v2') THEN
            RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_constraint
            WHERE conrelid = '{SOURCE_REVISIONS}'::regclass
              AND conname = '{SOURCE_CHECKSUM_UNIQUE}' AND contype = 'u'
              AND pg_catalog.pg_get_constraintdef(oid)
                  = 'UNIQUE (game_id, source_image_id, geometry_checksum_sha256)') THEN
            RAISE EXCEPTION 'SOURCE_GEOMETRY_CHECKSUM_UNIQUE_UNEXPECTED';
        END IF;
    END $guard$""")

    # 1. Source geometry revisions: ``reverted`` and the live-only checksum key.
    _replace_check(
        SOURCE_REVISIONS,
        "ck_image_source_geometry_revisions_state",
        _SOURCE_STATE.format(extra=",'reverted'"),
    )
    op.execute(f"ALTER TABLE {SOURCE_REVISIONS} DROP CONSTRAINT {SOURCE_CHECKSUM_UNIQUE}")
    op.execute(
        f"CREATE UNIQUE INDEX {SOURCE_LIVE_CHECKSUM_INDEX} ON {SOURCE_REVISIONS} "
        "(game_id, source_image_id, geometry_checksum_sha256) WHERE status <> 'reverted'"
    )

    # 2. Event vocabularies and the previous assignment source of cell events.
    _replace_check(
        BOARD_EVENTS,
        "ck_image_board_geometry_review_events_action",
        _BOARD_EVENT_ACTIONS.format(extra=",'geometry_reverted'"),
    )
    _replace_check(
        CELL_EVENTS,
        "ck_image_symbol_review_events_action",
        _CELL_EVENT_ACTIONS.format(extra=",'geometry_reverted'"),
    )
    op.execute(f"ALTER TABLE {CELL_EVENTS} ADD COLUMN previous_assignment_source VARCHAR(30)")
    op.execute(
        f"ALTER TABLE {CELL_EVENTS} ADD CONSTRAINT "
        "ck_image_symbol_review_events_previous_assignment_source CHECK ("
        f"previous_assignment_source IS NULL OR previous_assignment_source IN "
        f"{_ASSIGNMENT_SOURCES})"
    )

    # 3. Rejected deferred slot (schema only; TASK-0949 owns the write path).
    op.execute(f"""ALTER TABLE {PENDING}
        ADD COLUMN rejection_reason VARCHAR(20),
        ADD COLUMN rejection_note TEXT,
        ADD COLUMN rejected_at TIMESTAMP WITH TIME ZONE,
        ADD COLUMN rejected_by VARCHAR(200)""")
    _replace_check(
        PENDING,
        "ck_image_board_geometry_pending_status",
        _PENDING_STATUS.format(extra=",'rejected'"),
    )
    _replace_check(PENDING, "ck_image_board_geometry_pending_lifecycle", _PENDING_LIFECYCLE_V2)
    op.execute(
        f"ALTER TABLE {PENDING} ADD CONSTRAINT ck_image_board_geometry_pending_rejection "
        f"CHECK ({_PENDING_REJECTION})"
    )

    # 4. Append-only revert audit with the snapshot of the deleted rows.
    op.execute(f"""CREATE TABLE game_data_v2.{AUDIT} (
        game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1(),
        id UUID NOT NULL,
        import_job_id UUID NOT NULL,
        source_image_id UUID NOT NULL,
        sequence_number BIGINT NOT NULL,
        position_index SMALLINT NOT NULL,
        kind VARCHAR(20) NOT NULL,
        pending_geometry_id UUID,
        recognized_board_id UUID NOT NULL,
        review_item_id UUID NOT NULL,
        reverted_geometry_revision INTEGER NOT NULL,
        reverted_board_geometry_revision_id UUID NOT NULL,
        reverted_source_geometry_revision_id UUID NOT NULL,
        restored_source_geometry_revision_id UUID NOT NULL,
        restored_geometry_revision INTEGER,
        reverted_idempotency_key UUID NOT NULL,
        idempotency_key UUID NOT NULL,
        snapshot JSONB NOT NULL,
        snapshot_checksum_sha256 VARCHAR(64) NOT NULL,
        actor VARCHAR(200) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT v2_pk_image_geometry_correction_reverts PRIMARY KEY (game_id,id),
        CONSTRAINT uq_image_geometry_correction_reverts_idempotency
            UNIQUE (game_id,idempotency_key),
        CONSTRAINT uq_image_geometry_correction_reverts_revision
            UNIQUE (game_id,reverted_board_geometry_revision_id),
        CONSTRAINT ck_image_geometry_correction_reverts_kind CHECK (
            kind IN ('pending_slot','board_revision')),
        CONSTRAINT ck_image_geometry_correction_reverts_shape CHECK (
            sequence_number > 0 AND position_index BETWEEN 0 AND 8
            AND reverted_geometry_revision >= 1
            AND length(btrim(actor)) > 0
            AND snapshot_checksum_sha256 ~ '^[0-9a-f]{{64}}$'
            AND jsonb_typeof(snapshot) = 'object'
            AND ((kind = 'pending_slot' AND pending_geometry_id IS NOT NULL
                  AND restored_geometry_revision IS NULL)
                 OR (kind = 'board_revision'
                     AND restored_geometry_revision > reverted_geometry_revision))),
        CONSTRAINT v2_owner_image_geometry_correction_reverts FOREIGN KEY(game_id)
            REFERENCES public.games(id) ON DELETE RESTRICT,
        CONSTRAINT v2_fk_image_geometry_correction_reverts_job
            FOREIGN KEY(game_id,import_job_id)
            REFERENCES public.jobs(game_id,id) ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    # 4b. Durable identity of the rejection of a deferred slot (TASK-0949) and
    # of its replacement (``superseded``, TASK-0950: the successor review item
    # of the replacement photo). Neither id has a foreign key: the row must
    # outlive any later slot or item cleanup.
    op.execute(f"""CREATE TABLE game_data_v2.{PENDING_EVENTS} (
        game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1(),
        id UUID NOT NULL,
        import_job_id UUID NOT NULL,
        pending_geometry_id UUID NOT NULL,
        rejection_revision INTEGER NOT NULL,
        action VARCHAR(30) NOT NULL,
        idempotency_key UUID NOT NULL,
        command_sha256 VARCHAR(64) NOT NULL,
        reason VARCHAR(20),
        note TEXT,
        actor VARCHAR(200) NOT NULL,
        successor_review_item_id UUID,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT v2_pk_image_board_geometry_pending_events PRIMARY KEY (game_id,id),
        CONSTRAINT uq_image_board_geometry_pending_events_idempotency
            UNIQUE (game_id,idempotency_key),
        CONSTRAINT uq_image_board_geometry_pending_events_revision
            UNIQUE (game_id,pending_geometry_id,rejection_revision,action),
        CONSTRAINT ck_image_board_geometry_pending_events_shape CHECK (
            rejection_revision >= 1
            AND action IN ('rejected','rejection_reverted','superseded')
            AND length(btrim(actor)) > 0
            AND command_sha256 ~ '^[0-9a-f]{{64}}$'
            AND (reason IS NULL OR reason IN ('cropped','blurred','other'))
            AND (note IS NULL OR length(btrim(note)) BETWEEN 1 AND 1000)
            AND (reason IS DISTINCT FROM 'other' OR note IS NOT NULL)
            AND ((action = 'rejected' AND reason IS NOT NULL
                  AND successor_review_item_id IS NULL)
                 OR (action = 'rejection_reverted' AND reason IS NULL AND note IS NULL
                  AND successor_review_item_id IS NULL)
                 OR (action = 'superseded' AND reason IS NULL AND note IS NULL
                  AND successor_review_item_id IS NOT NULL))),
        CONSTRAINT v2_owner_image_board_geometry_pending_events FOREIGN KEY(game_id)
            REFERENCES public.games(id) ON DELETE RESTRICT,
        CONSTRAINT v2_fk_image_board_geometry_pending_events_job
            FOREIGN KEY(game_id,import_job_id)
            REFERENCES public.jobs(game_id,id) ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute(
        f"CREATE INDEX ix_image_board_geometry_pending_events_import "
        f"ON game_data_v2.{PENDING_EVENTS} (game_id,import_job_id,created_at DESC)"
    )
    op.execute(
        f"CREATE INDEX ix_image_board_geometry_pending_events_slot "
        f"ON game_data_v2.{PENDING_EVENTS} (game_id,pending_geometry_id,rejection_revision DESC)"
    )
    op.execute(
        f"CREATE INDEX ix_image_geometry_correction_reverts_import ON game_data_v2.{AUDIT} "
        "(game_id,import_job_id,created_at DESC)"
    )
    op.execute(
        f"CREATE INDEX ix_image_geometry_correction_reverts_reverted_key "
        f"ON game_data_v2.{AUDIT} (game_id,reverted_idempotency_key)"
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
                "manifest_version": V7,
                "table_name": table,
                "ownership": ownership(table),
                "partitioned": table in GAME_TABLES,
            }
            for table in sorted(CATALOG | SHARED | set(GAME_TABLES) | set(CONTROL_TABLES))
        ],
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations "
        "DROP CONSTRAINT ck_game_storage_locations_manifest_version_v6"
    )
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version = '{V7}',"
        f"revision = revision + 1,updated_at = now() WHERE manifest_version = '{V6}'"
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations "
        f"ADD CONSTRAINT ck_game_storage_locations_manifest_version_v7 "
        f"CHECK(manifest_version = '{V7}')"
    )


def downgrade() -> None:
    _guard()
    # FORCE RLS must never make a non-empty table look empty. A role without
    # BYPASSRLS fails here rather than silently dropping revert history.
    op.execute("SET LOCAL row_security = off")
    op.execute(
        f"LOCK TABLE game_data_v2.{AUDIT}, game_data_v2.{PENDING_EVENTS}, "
        f"{SOURCE_REVISIONS}, {PENDING}, {BOARD_EVENTS}, {CELL_EVENTS} IN ACCESS EXCLUSIVE MODE"
    )
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM game_data_v2.{AUDIT})
           OR EXISTS (SELECT 1 FROM game_data_v2.{PENDING_EVENTS})
           OR EXISTS (SELECT 1 FROM {SOURCE_REVISIONS} WHERE status = 'reverted')
           OR EXISTS (SELECT 1 FROM {BOARD_EVENTS} WHERE action = 'geometry_reverted')
           OR EXISTS (SELECT 1 FROM {CELL_EVENTS} WHERE action = 'geometry_reverted')
           OR EXISTS (SELECT 1 FROM {CELL_EVENTS} WHERE previous_assignment_source IS NOT NULL)
           OR EXISTS (SELECT 1 FROM {PENDING}
                      WHERE status = 'rejected' OR rejected_at IS NOT NULL) THEN
            RAISE EXCEPTION 'GEOMETRY_CORRECTION_REVERT_DOWNGRADE_HAS_HISTORY';
        END IF;
        IF EXISTS (SELECT 1 FROM public.game_storage_locations
                   WHERE manifest_version <> '{V7}') THEN
            RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED';
        END IF;
    END $guard$""")
    op.execute(f"DROP TABLE game_data_v2.{AUDIT}")
    op.execute(f"DROP TABLE game_data_v2.{PENDING_EVENTS}")

    op.execute(f"ALTER TABLE {PENDING} DROP CONSTRAINT ck_image_board_geometry_pending_rejection")
    _replace_check(PENDING, "ck_image_board_geometry_pending_lifecycle", _PENDING_LIFECYCLE_V1)
    _replace_check(
        PENDING, "ck_image_board_geometry_pending_status", _PENDING_STATUS.format(extra="")
    )
    op.execute(f"""ALTER TABLE {PENDING}
        DROP COLUMN rejection_reason,
        DROP COLUMN rejection_note,
        DROP COLUMN rejected_at,
        DROP COLUMN rejected_by""")

    op.execute(
        f"ALTER TABLE {CELL_EVENTS} "
        "DROP CONSTRAINT ck_image_symbol_review_events_previous_assignment_source, "
        "DROP COLUMN previous_assignment_source"
    )
    _replace_check(
        CELL_EVENTS, "ck_image_symbol_review_events_action", _CELL_EVENT_ACTIONS.format(extra="")
    )
    _replace_check(
        BOARD_EVENTS,
        "ck_image_board_geometry_review_events_action",
        _BOARD_EVENT_ACTIONS.format(extra=""),
    )

    op.execute(f"DROP INDEX game_data_v2.{SOURCE_LIVE_CHECKSUM_INDEX}")
    op.execute(
        f"ALTER TABLE {SOURCE_REVISIONS} ADD CONSTRAINT {SOURCE_CHECKSUM_UNIQUE} "
        "UNIQUE (game_id, source_image_id, geometry_checksum_sha256)"
    )
    _replace_check(
        SOURCE_REVISIONS, "ck_image_source_geometry_revisions_state", _SOURCE_STATE.format(extra="")
    )

    op.execute(
        "ALTER TABLE public.game_storage_locations "
        "DROP CONSTRAINT ck_game_storage_locations_manifest_version_v7"
    )
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version = '{V6}',"
        f"revision = revision + 1,updated_at = now() WHERE manifest_version = '{V7}'"
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations "
        f"ADD CONSTRAINT ck_game_storage_locations_manifest_version_v6 "
        f"CHECK(manifest_version = '{V6}')"
    )
    op.execute(f"DELETE FROM public.game_storage_table_manifest WHERE manifest_version = '{V7}'")
