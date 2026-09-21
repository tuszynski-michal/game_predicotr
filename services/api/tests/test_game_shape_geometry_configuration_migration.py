from __future__ import annotations

import importlib.util
from pathlib import Path

from game_predictor_api.storage.models import GameModel

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPOSITORY_ROOT
    / "services"
    / "api"
    / "alembic"
    / "versions"
    / "0116_game_shape_geometry_configuration.py"
)


def test_migration_0116_adds_nullable_game_configuration_without_backfill() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "0115_shape_geometry_v2_global_library" in source
    assert '"shape_geometry_configuration"' in source
    assert "nullable=True" in source
    assert "framed_full_page_v2" in source
    assert "requires_clarification" in source
    assert "UPDATE games" not in source
    assert 'op.drop_column("games", "shape_geometry_configuration"' in source


def test_migration_module_and_orm_expose_the_nullable_configuration() -> None:
    spec = importlib.util.spec_from_file_location("migration_0116", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "0116_game_shape_geometry_configuration"
    assert module.down_revision == "0115_shape_geometry_v2_global_library"
    assert GameModel.shape_geometry_configuration.property.columns[0].nullable is True
