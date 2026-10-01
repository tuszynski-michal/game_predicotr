from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "drop_diagnostic_databases_test_module",
    REPOSITORY_ROOT / "scripts" / "drop_diagnostic_databases.py",
)
assert _SPEC is not None and _SPEC.loader is not None
script: Any = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = script
_SPEC.loader.exec_module(script)


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: Any, _parameters: Any = None) -> Any:
        self.statements.append(str(statement))
        return None


def _preview(*databases: tuple[str, int]) -> dict[str, Any]:
    return {
        "databases": [
            {"name": name, "bytes": 1, "sessions": sessions} for name, sessions in databases
        ],
        "previewSha256": "a" * 64,
    }


def test_confirmation_phrase_is_bound_to_the_preview() -> None:
    assert script._required_confirmation("abcdef0123456789ffff") == (
        "DROP-DIAGNOSTIC-DATABASES abcdef0123456789"
    )


def test_only_listed_idle_databases_are_dropped() -> None:
    connection = _Connection()

    dropped = script._drop(connection, _preview(("diag_raw_test", 0)))

    assert dropped == ["diag_raw_test"]
    assert connection.statements == ['DROP DATABASE "diag_raw_test"']


@pytest.mark.parametrize(
    ("preview", "code"),
    [
        (_preview(("game_predictor", 0)), "DIAGNOSTIC_DATABASE_NOT_LISTED"),
        (_preview(("postgres", 0)), "DIAGNOSTIC_DATABASE_NOT_LISTED"),
        (_preview(("diag_search_path_test", 2)), "DIAGNOSTIC_DATABASE_IN_USE"),
    ],
)
def test_unlisted_or_busy_databases_are_refused(preview: dict[str, Any], code: str) -> None:
    connection = _Connection()

    with pytest.raises(script.DropRefused, match=code):
        script._drop(connection, preview)

    assert connection.statements == []
