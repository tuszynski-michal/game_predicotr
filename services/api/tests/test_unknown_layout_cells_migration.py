from pathlib import Path

MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "0074_unknown_layout_cells.py"


def test_unknown_layout_cells_migration_is_bounded_and_reversible() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    expected_down_revision = (
        'down_revision: str | Sequence[str] | None = '
        '"0073_topology_geometry_crop_provenance"'
    )
    assert expected_down_revision in source
    assert "cardinality(cells) > 0 AND 0 <= ALL(cells)" in source
    assert "cells IS NULL OR (0 <= ALL(cells)" in source
    assert "cardinality(cells) = 15 AND 1 <= ALL(cells)" in source
    assert "UPDATE " not in source
