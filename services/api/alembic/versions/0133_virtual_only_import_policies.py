"""Image import rollout states use only virtual policies (D-467, TASK-0790).

The ``verified_v19`` (``legacy`` / ``legacy_files``) and ``structured_shadow``
(``structured_shadow`` / ``virtual_shadow``) import policies were removed.  A
game whose rollout state still names a non-virtual mode (on the operator
database: two games that were never switched, revision 0) moves to the virtual
default policy of a new game, ``structured_lattice_v3`` / ``virtual_default``.
The move mirrors ``apply_engine_policy``: the revision is incremented and the
bounded-validation progress is reset, because it was bound to the old mode.

The mode CHECK constraints are narrowed to the virtual policies and the column
defaults follow the new-game default.  The statements run on the partitioned
parent, so every per-game partition receives the same constraint name.

Upgrade refuses while a non-virtual state has an active validation backfill
(``processing``).  Downgrade refuses: the previous modes and revisions are not
recoverable without a copy, and restoring a legacy mode would re-enable a
removed import path.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0133_virtual_only_import_policies"
down_revision: str | Sequence[str] | None = "0132_symbol_reference_images_cell_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "game_data_v2.image_geometry_rollout_states"
# Frozen values: no ORM or application import in a migration.
TARGET_GEOMETRY_MODE = "structured_lattice_v3"
TARGET_CELL_ASSET_MODE = "virtual_default"
VIRTUAL_PAIRS = (
    "(('structured_default', 'virtual_default'), ('structured_lattice_v3', 'virtual_default'))"
)
ACTOR = "system:migration-0133-virtual-only-import-policies"
GEOMETRY_CHECK = "ck_image_geometry_rollout_states_geometry_mode"
ASSET_CHECK = "ck_image_geometry_rollout_states_asset_mode"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(f"LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (
            SELECT 1 FROM {TABLE}
            WHERE (geometry_mode, cell_asset_mode) NOT IN {VIRTUAL_PAIRS}
              AND backfill_status = 'processing'
        ) THEN
            RAISE EXCEPTION 'IMAGE_ENGINE_POLICY_MIGRATION_BUSY: a non-virtual rollout state '
                'has an active validation backfill';
        END IF;
    END $guard$""")
    op.execute(f"""UPDATE {TABLE}
        SET geometry_mode = '{TARGET_GEOMETRY_MODE}',
            cell_asset_mode = '{TARGET_CELL_ASSET_MODE}',
            revision = revision + 1,
            backfill_status = 'not_started',
            last_source_image_id = NULL,
            failure_code = NULL,
            failure_message = NULL,
            validation_rollout_revision = NULL,
            validation_input_checksum_sha256 = NULL,
            validation_job_id = NULL,
            updated_by = '{ACTOR}',
            updated_at = now()
        WHERE (geometry_mode, cell_asset_mode) NOT IN {VIRTUAL_PAIRS}""")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {GEOMETRY_CHECK}")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {ASSET_CHECK}")
    op.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {GEOMETRY_CHECK} "
        "CHECK (geometry_mode IN ('structured_default', 'structured_lattice_v3'))"
    )
    op.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {ASSET_CHECK} "
        "CHECK (cell_asset_mode IN ('virtual_default'))"
    )
    op.execute(
        f"ALTER TABLE {TABLE} ALTER COLUMN geometry_mode SET DEFAULT '{TARGET_GEOMETRY_MODE}'"
    )
    op.execute(
        f"ALTER TABLE {TABLE} ALTER COLUMN cell_asset_mode SET DEFAULT '{TARGET_CELL_ASSET_MODE}'"
    )


def downgrade() -> None:
    op.execute("""DO $refuse$ BEGIN
        RAISE EXCEPTION 'IMAGE_ENGINE_POLICY_MIGRATION_IRREVERSIBLE: migration 0133 cannot '
            'restore removed legacy import policies; restore a database backup instead';
    END $refuse$""")
