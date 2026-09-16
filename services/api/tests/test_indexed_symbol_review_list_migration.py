from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0108_indexed_symbol_review_list"
PREVIOUS = "0107_current_symbol_cell_projection"


def _config(output: StringIO) -> Config:
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    return result


def test_indexed_symbol_review_list_migration_is_linear_and_bounded() -> None:
    script = ScriptDirectory.from_config(_config(StringIO()))
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS

    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "ADD COLUMN prediction_confidence FLOAT" in sql
    assert "v2_ix_symbol_review_list_all" in sql
    assert "v2_ix_symbol_review_list_symbol_state" in sql
    assert "v2_ix_symbol_review_list_unknown" in sql
    assert "v2_ix_symbol_review_list_confidence" in sql
    assert "v2_ix_symbol_review_active_cohort" in sql
    assert "UPDATE image_symbol_review_cells" not in sql
    assert "INSERT INTO image_symbol_review_cells" not in sql
    assert "DELETE FROM image_symbol_review_cells" not in sql
    assert "CASCADE" not in sql
