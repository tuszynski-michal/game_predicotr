"""A changed runtime SQL anchor must abort migration instead of dropping a fence."""

import importlib.util
from pathlib import Path

import pytest


def _migration():
    path = Path(__file__).parents[1] / "alembic/versions/0175_source_replacement_guards.py"
    spec = importlib.util.spec_from_file_location("replacement_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("sql", ["absent", "anchor anchor"])
def test_changed_sql_anchor_fails_closed(sql):
    with pytest.raises(RuntimeError, match="missing or ambiguous"):
        _migration()._replace_once(sql, "anchor", "fence")


def test_single_sql_anchor_preserves_surrounding_contract():
    assert _migration()._replace_once("before anchor after", "anchor", "fence") == (
        "before fence after"
    )
