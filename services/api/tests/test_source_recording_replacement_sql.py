"""Keep composed registry SQL aligned with the deployed 0175 replacement fences."""

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from game_predictor_api.storage.source_recording_replacement_sql import (
    GUARD_SQL,
    REPLACEMENT_V4_SQL,
    REPLACEMENT_V5_WRAPPER,
)
from game_predictor_api.storage.source_recording_sql_v6 import PHOTO_SQL, WRAPPER_SQL

ROOT = Path(__file__).resolve().parents[3]


def test_legacy_sql_matches_actual_0175_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    migration = script.get_revision("0175_source_replacement_guards").module
    tree = ast.parse(inspect.getsource(migration.upgrade))
    guards = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "guard" for target in node.targets)
    ]
    assert len(guards) == 1
    assert ast.literal_eval(guards[0]) == GUARD_SQL

    statements: list[str] = []
    connection = SimpleNamespace(
        dialect=SimpleNamespace(identifier_preparer=SimpleNamespace(quote=lambda value: value))
    )
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(execute=statements.append, get_bind=lambda: connection),
    )
    monkeypatch.setattr(migration, "validate_recording_capability", lambda _connection: "owner")
    migration.upgrade()

    assert statements[1] == REPLACEMENT_V5_WRAPPER
    photo = REPLACEMENT_V4_SQL[
        REPLACEMENT_V4_SQL.index(
            "CREATE FUNCTION public.recording_photo_cohort_v1("
        ) : REPLACEMENT_V4_SQL.index("ALTER FUNCTION public.recording_cohort_command_v3")
    ]
    assert statements[2] == photo.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


@pytest.mark.parametrize("sql", [PHOTO_SQL, WRAPPER_SQL], ids=["photo", "wrapper"])
def test_v6_installs_replacement_guard_once(sql: str) -> None:
    assert sql.count(GUARD_SQL) == 1
    assert sql.count("SOURCE_REPLACEMENT_RESERVED") == 1
    assert sql.count("SOURCE_REPLACEMENT_RETIRED") == 1
    assert sql.count("sequence-ownership") == 1
    assert sql.count("public.source_replacement_source_current_v1(") == (
        2 if sql == PHOTO_SQL else 1
    )


def test_v6_filters_current_photo_population_once() -> None:
    current_filter = (
        "WHERE s.game_id=wanted AND public.source_replacement_source_current_v1("
        "wanted,s.id,s.checksum_sha256) AND s.import_job_id IN"
    )
    assert PHOTO_SQL.count(current_filter) == 1
    assert "WHERE s.game_id=wanted AND s.import_job_id IN" not in PHOTO_SQL
