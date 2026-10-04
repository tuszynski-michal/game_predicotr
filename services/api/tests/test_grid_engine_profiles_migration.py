"""Static contract of migration 0140 (TASK-0830); the lifecycle runs in integration/."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0140_grid_engine_profiles.py"
)


def test_0140_extends_the_constraint_with_exactly_the_domain_values() -> None:
    spec = importlib.util.spec_from_file_location("migration_0140", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "0140_grid_engine_profiles"
    assert module.down_revision == "0139_source_image_geometry_completeness"
    assert set(module.PREVIOUS_VALUES + module.GRID_ENGINE_PROFILE_VALUES) == {
        value.value for value in GameShapeGeometryConfiguration
    }
    assert module.PREVIOUS_VALUES == ("framed_full_page_v2", "requires_clarification")
    # The 0116 expression is restored verbatim on downgrade.
    assert module._expression(module.PREVIOUS_VALUES) == (
        "shape_geometry_configuration IS NULL OR shape_geometry_configuration IN "
        "('framed_full_page_v2', 'requires_clarification')"
    )
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "GRID_ENGINE_PROFILE_IN_USE" in source
    assert "UPDATE" not in source
