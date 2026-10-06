from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0146_symbol_review_import_filter_index"
PREVIOUS = "0145_neural_page_geometry_binding"


def _config(output: StringIO) -> Config:
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    return result


def test_import_filter_index_migration_is_linear_and_data_neutral() -> None:
    script = ScriptDirectory.from_config(_config(StringIO()))
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS

    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "v2_ix_symbol_review_list_import" in sql
    assert "(game_id, import_job_id, sequence_number, cell_index, id)" in sql
    assert "UPDATE image_symbol_review_cells" not in sql
    assert "INSERT INTO image_symbol_review_cells" not in sql
    assert "DELETE FROM image_symbol_review_cells" not in sql
    assert "CASCADE" not in sql
