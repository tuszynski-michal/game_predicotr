from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0107_current_symbol_cell_projection"
PREVIOUS = "0106_game_storage_routing_fence"


def _config(output: StringIO) -> Config:
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    return result


def test_v2_projection_has_one_row_per_logical_cell_without_data_rewrite() -> None:
    output = StringIO()

    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)

    sql = output.getvalue()
    assert "UNIQUE (game_id, sequence_number, cell_index)" in sql
    assert "ALTER TABLE game_data_v2.image_symbol_review_cells" in sql
    assert "INSERT INTO" not in sql
    assert "UPDATE game_data_v2" not in sql
    assert "DELETE FROM" not in sql


def test_v2_projection_revision_is_linear_and_reversible() -> None:
    script = ScriptDirectory.from_config(_config(StringIO()))
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS

    output = StringIO()
    command.downgrade(_config(output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()
    assert "DROP CONSTRAINT uq_v2_symbol_cell_current_logical_position" in sql
    assert "CASCADE" not in sql
