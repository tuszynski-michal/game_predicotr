from __future__ import annotations

from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0115_shape_geometry_v2_global_library"
PREVIOUS = "0114_v7_semi_automatic_activation_gate"


def _config(output: StringIO) -> Config:
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option(
        "sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused"
    )
    return result


def test_global_geometry_library_migration_is_public_append_only_control_plane() -> None:
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "0115_shape_geometry_v2_global_library.py"
    )
    content = path.read_text(encoding="utf-8")

    assert (
        'down_revision: str | Sequence[str] | None = "0114_v7_semi_automatic_activation_gate"'
        in content
    )
    assert 'schema="public"' in content
    assert '"global_geometry_profile_versions"' in content
    assert '"global_geometry_evidence_samples"' in content
    assert '"global_geometry_profile_write_receipts"' in content
    assert "uq_global_geometry_profile_versions_active_scope" in content
    assert "GLOBAL_GEOMETRY_LIBRARY_APPEND_ONLY" in content
    assert "SHAPE_GEOMETRY_GLOBAL_LIBRARY_DOWNGRADE_HAS_DATA" in content
    assert "game_id" not in content


def test_global_geometry_library_migration_has_safe_offline_upgrade_and_downgrade() -> None:
    upgrade = StringIO()
    downgrade = StringIO()

    command.upgrade(_config(upgrade), f"{PREVIOUS}:{REVISION}", sql=True)
    command.downgrade(_config(downgrade), f"{REVISION}:{PREVIOUS}", sql=True)

    upgrade_sql = upgrade.getvalue().lower()
    downgrade_sql = downgrade.getvalue().lower()
    assert "create table public.global_geometry_profile_versions" in upgrade_sql
    assert "create table public.global_geometry_evidence_samples" in upgrade_sql
    assert "create table public.global_geometry_profile_write_receipts" in upgrade_sql
    assert "create trigger trg_global_geometry_profile_versions_append_only" in upgrade_sql
    assert "delete from" not in upgrade_sql
    assert "shape_geometry_global_library_downgrade_has_data" in downgrade_sql
    downgrade_guard = downgrade_sql.index("shape_geometry_global_library_downgrade_has_data")
    first_drop = downgrade_sql.index("drop table public.global_geometry_profile_write_receipts")
    assert downgrade_guard < first_drop
