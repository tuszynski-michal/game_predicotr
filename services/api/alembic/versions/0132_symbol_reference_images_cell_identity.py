"""Symbol reference images identify their source cell without an observation (D-467).

TASK-0758 switches every runtime reader away from ``cell_observations``.  A
symbol reference already records its source cell as
``(source_recognized_board_id, cell_index)`` and the candidate API identifies
a candidate by its ``image_symbol_review_cells`` id, so the
``source_observation_id`` column and its foreign key to ``cell_observations``
are dropped.  Without this the S5 drop of ``cell_observations`` would be
blocked by the foreign key.

Upgrade refuses when an existing row's observation is not the observation at
its recorded ``(board, cell_index)``: only then would downgrade be unable to
restore it.  Downgrade restores the column from ``cell_observations`` (which
still exist until S5) and refuses when any row cannot be restored.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0132_symbol_reference_images_cell_identity"
down_revision: str | Sequence[str] | None = "0131_board_render_manifests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "game_data_v2.symbol_reference_images"
OBSERVATIONS = "game_data_v2.cell_observations"
# Frozen names created by the game_data_v2 schema (0105 derivation).
_FK = "v2_fk_657ff3d6c526545fcfa6"
_FK_INDEX = "v2_fkix_657ff3d6c526545fcfa6"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(f"LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (
            SELECT 1 FROM {TABLE} r
            WHERE NOT EXISTS (
                SELECT 1 FROM {OBSERVATIONS} o
                WHERE o.game_id = r.game_id
                  AND o.id = r.source_observation_id
                  AND o.recognized_board_id = r.source_recognized_board_id
                  AND o.row_index = r.cell_index / 5
                  AND o.column_index = r.cell_index % 5)
        ) THEN
            RAISE EXCEPTION 'SYMBOL_REFERENCE_OBSERVATION_MISMATCH: a reference observation is '
                'not the observation of its recorded board cell';
        END IF;
    END $guard$""")
    # Dropping the column drops its foreign key, the partition clones of the
    # foreign key and the supporting index on every partition.
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN source_observation_id")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(f"LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN source_observation_id UUID")
    op.execute(f"""UPDATE {TABLE} AS r SET source_observation_id = o.id
        FROM {OBSERVATIONS} AS o
        WHERE o.game_id = r.game_id
          AND o.recognized_board_id = r.source_recognized_board_id
          AND o.row_index = r.cell_index / 5
          AND o.column_index = r.cell_index % 5""")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM {TABLE} WHERE source_observation_id IS NULL) THEN
            RAISE EXCEPTION 'SYMBOL_REFERENCE_OBSERVATION_UNRECOVERABLE: a reference cell has '
                'no cell observation';
        END IF;
    END $guard$""")
    op.execute(f"ALTER TABLE {TABLE} ALTER COLUMN source_observation_id SET NOT NULL")
    op.execute(f"CREATE INDEX {_FK_INDEX} ON {TABLE} (game_id, source_observation_id)")
    op.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {_FK} "
        f"FOREIGN KEY (game_id, source_observation_id) REFERENCES {OBSERVATIONS} (game_id, id) "
        "ON DELETE RESTRICT"
    )
