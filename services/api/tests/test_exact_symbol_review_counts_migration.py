from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0109_exact_symbol_review_counts"
PREVIOUS = "0108_indexed_symbol_review_list"


def _config(output: StringIO) -> Config:
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    return result


def test_exact_count_migration_is_linear_bounded_and_data_neutral() -> None:
    script = ScriptDirectory.from_config(_config(StringIO()))
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS

    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert sql.count("ADD COLUMN count_projection_status") == 2
    assert sql.count("ADD COLUMN count_rebuild_cursor") == 2
    assert "SET LOCAL lock_timeout = '2s'" in sql
    assert "SET LOCAL statement_timeout = '30s'" in sql
    assert "UPDATE image_symbol_review" not in sql
    assert "DELETE FROM" not in sql
    assert "CASCADE" not in sql
