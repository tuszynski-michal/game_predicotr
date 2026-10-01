"""TASK-0758: migration 0132 drops the observation identity of symbol references."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0132_symbol_reference_images_cell_identity"
PREVIOUS = "0131_board_render_manifests"


def _config(output: StringIO) -> Config:
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    return result


def test_migration_0132_drops_the_observation_column_behind_a_guard() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()
    assert "SET LOCAL lock_timeout" in sql and "SET LOCAL statement_timeout" in sql
    assert "LOCK TABLE game_data_v2.symbol_reference_images IN ACCESS EXCLUSIVE MODE" in sql
    assert "SYMBOL_REFERENCE_OBSERVATION_MISMATCH" in sql
    assert sql.index("SYMBOL_REFERENCE_OBSERVATION_MISMATCH") < sql.index("DROP COLUMN")
    assert (
        "ALTER TABLE game_data_v2.symbol_reference_images DROP COLUMN source_observation_id"
    ) in sql
    assert "CASCADE" not in sql
    revision = ScriptDirectory.from_config(_config(StringIO())).get_revision(REVISION)
    assert revision is not None and revision.down_revision == PREVIOUS


def test_migration_0132_downgrade_restores_the_column_from_the_cell_or_refuses() -> None:
    output = StringIO()
    command.downgrade(_config(output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()
    assert "ADD COLUMN source_observation_id UUID" in sql
    assert "o.row_index = r.cell_index / 5" in sql and "o.column_index = r.cell_index % 5" in sql
    assert sql.index("SYMBOL_REFERENCE_OBSERVATION_UNRECOVERABLE") < sql.index("SET NOT NULL")
    assert (
        "ADD CONSTRAINT v2_fk_657ff3d6c526545fcfa6 FOREIGN KEY (game_id, source_observation_id) "
        "REFERENCES game_data_v2.cell_observations (game_id, id) ON DELETE RESTRICT"
    ) in sql
