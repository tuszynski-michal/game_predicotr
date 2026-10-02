"""TASK-0793: offline contract of migration 0136 (PostgreSQL behaviour is in integration)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0136_drop_cell_render_spec.py"
)
_COLUMN = re.compile(r"\brender_spec\b(?!_)")


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0136", _PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_checks_do_not_mention_the_dropped_column() -> None:
    module = _migration()
    assert module.down_revision == "0135_virtual_only_asset_modes"
    for expression in (module.NEW_PROVENANCE_CHECK, module.NEW_SOURCE_ASSET_CHECK):
        assert _COLUMN.search(expression) is None
        assert "render_spec_checksum_sha256" in expression


def test_upgrade_order_preflight_checks_then_drop() -> None:
    module = _migration()
    executed: list[str] = []
    with patch.object(module.op, "execute", side_effect=executed.append, create=True):
        module.upgrade()
    assert executed[0] == "SET LOCAL lock_timeout = '5s'"
    assert executed[1] == "SET LOCAL statement_timeout = '120s'"
    assert "ACCESS EXCLUSIVE" in executed[2]
    assert "CELL_RENDER_MANIFEST_MISSING" in executed[4]
    assert "jsonb_array_elements" not in executed[4]
    swaps = [statement for statement in executed if "CONSTRAINT" in statement]
    assert len(swaps) == 4 and all(
        statement.endswith("NOT VALID") for statement in swaps if " ADD " in statement
    )
    assert executed[-1] == f"ALTER TABLE {module.CELLS} DROP COLUMN render_spec"


def test_downgrade_refuses() -> None:
    with pytest.raises(RuntimeError, match="CELL_RENDER_SPEC_DROP_IRREVERSIBLE"):
        _migration().downgrade()
