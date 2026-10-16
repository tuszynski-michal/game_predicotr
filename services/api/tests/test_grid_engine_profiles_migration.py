"""Static contract of migration 0140 (TASK-0830); the lifecycle runs in integration/."""

from __future__ import annotations

import ast
import importlib.util
import re
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
    # 0140 is immutable history. The neutral V3 value was introduced by 0156.
    assert set(module.PREVIOUS_VALUES + module.GRID_ENGINE_PROFILE_VALUES) == {
        "framed_full_page_v2",
        "requires_clarification",
        "grid_profile_mumie_v1",
        "grid_profile_777_v2",
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


def test_0156_extends_the_constraint_with_exactly_the_current_domain_values() -> None:
    path = next(MIGRATION_PATH.parent.glob("0156_*.py"))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constraint = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_check_constraint"
        and ast.literal_eval(node.args[0]) == "ck_games_shape_geometry_configuration"
    )
    expression = ast.literal_eval(constraint.args[2])
    assert set(re.findall(r"'([^']+)'", expression)) == {
        value.value for value in GameShapeGeometryConfiguration
    }
