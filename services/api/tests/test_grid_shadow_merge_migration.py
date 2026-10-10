"""Both released migration branches converge without replaying their own DDL."""

from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]
HEAD = "0143_merge_share_grid_shadow"


@pytest.mark.parametrize(
    ("previous", "needs_share", "needs_shadow"),
    (
        ("0140_grid_engine_profiles", True, True),
        ("0141_share_symbol_corrections", False, True),
        ("0142_grid_geometry_shadow_results", True, False),
    ),
)
def test_each_existing_head_upgrades_only_the_missing_branch(
    previous: str, needs_share: bool, needs_shadow: bool
) -> None:
    output = StringIO()
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    command.upgrade(config, f"{previous}:{HEAD}", sql=True)
    sql = output.getvalue()
    assert ("CREATE UNIQUE INDEX uq_bss_correction_operation" in sql) is needs_share
    assert ("CREATE TABLE game_data_v2.image_geometry_shadow_results" in sql) is needs_shadow
    assert "0143_merge_share_grid_shadow" in sql
    assert "DROP TABLE" not in sql
    assert "DELETE FROM game_data_v2." not in sql
    assert "UPDATE game_data_v2." not in sql
