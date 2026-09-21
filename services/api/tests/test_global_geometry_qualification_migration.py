from __future__ import annotations

from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0117_shape_geometry_v2_qualification"
PREVIOUS = "0116_game_shape_geometry_configuration"


def _config(output: StringIO) -> Config:
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option(
        "sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused"
    )
    return result


def test_qualification_migration_is_public_append_only_control_plane() -> None:
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "0117_shape_geometry_v2_qualification.py"
    )
    content = path.read_text(encoding="utf-8")

    assert (
        'down_revision: str | Sequence[str] | None = "0116_game_shape_geometry_configuration"'
        in content
    )
    assert 'schema="public"' in content
    assert '"global_geometry_profile_qualification_results"' in content
    assert '"global_geometry_profile_qualification_receipts"' in content
    assert "GLOBAL_GEOMETRY_LIBRARY_APPEND_ONLY" not in content
    assert "SHAPE_GEOMETRY_QUALIFICATION_DOWNGRADE_HAS_DATA" in content
    assert "game_id" not in content


def test_qualification_migration_has_safe_offline_upgrade_and_downgrade() -> None:
    upgrade = StringIO()
    downgrade = StringIO()

    command.upgrade(_config(upgrade), f"{PREVIOUS}:{REVISION}", sql=True)
    command.downgrade(_config(downgrade), f"{REVISION}:{PREVIOUS}", sql=True)

    upgrade_sql = upgrade.getvalue().lower()
    downgrade_sql = downgrade.getvalue().lower()
    assert "create table public.global_geometry_profile_qualification_results" in upgrade_sql
    assert "create table public.global_geometry_profile_qualification_receipts" in upgrade_sql
    assert (
        "create trigger trg_global_geometry_profile_qualification_results_append_only"
        in upgrade_sql
    )
    assert "delete from" not in upgrade_sql
    assert "shape_geometry_qualification_downgrade_has_data" in downgrade_sql
    downgrade_guard = downgrade_sql.index("shape_geometry_qualification_downgrade_has_data")
    first_drop = downgrade_sql.index(
        "drop table public.global_geometry_profile_qualification_receipts"
    )
    assert downgrade_guard < first_drop
