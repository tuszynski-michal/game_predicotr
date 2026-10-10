"""The enumerated write points of the super game derivation input (TASK-0933).

Static half of the contract: every listed write point calls
``record_super_game_input_change`` with its own source, and every call site in
the code base is listed.  The behavioural half (the bump commits or rolls back
with the write, one queued job per game) runs on PostgreSQL in
``integration/test_super_game_series_postgres.py``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import textwrap
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.storage import catalog_repository
from game_predictor_api.storage.game_storage_routing import GameStorageRouter
from game_predictor_api.storage.models import GameModel
from game_predictor_api.storage.super_game_input_version import (
    SUPER_GAME_INPUT_SOURCES,
    SUPER_GAME_INPUT_WRITE_POINTS,
    SuperGameInputWritePoint,
    record_super_game_input_change,
)

ROOT = Path(__file__).resolve().parents[3]
PACKAGES = (
    ROOT / "services" / "api" / "src" / "game_predictor_api",
    ROOT / "services" / "worker" / "src" / "game_predictor_worker",
)
HELPER = "record_super_game_input_change"


def _resolve(point: SuperGameInputWritePoint) -> object:
    target: object = importlib.import_module(f"game_predictor_api.{point.module}")
    for part in point.qualname.split("."):
        target = getattr(target, part)
    return target


def _helper_sources(function: object) -> list[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))  # type: ignore[arg-type]
    sources: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == HELPER:
            for keyword in node.keywords:
                if keyword.arg == "source" and isinstance(keyword.value, ast.Constant):
                    sources.append(str(keyword.value.value))
    return sources


@pytest.mark.parametrize(
    "point", SUPER_GAME_INPUT_WRITE_POINTS, ids=lambda point: f"{point.source}:{point.qualname}"
)
def test_every_listed_write_point_bumps_the_input_version(point: SuperGameInputWritePoint) -> None:
    function = _resolve(point)
    assert point.source in _helper_sources(function), (
        f"{point.module}:{point.qualname} must call {HELPER}(..., source={point.source!r})"
    )


def test_every_call_site_is_listed() -> None:
    listed = {
        (point.module, point.qualname.split(".")[-1]) for point in SUPER_GAME_INPUT_WRITE_POINTS
    }
    found: set[tuple[str, str]] = set()
    for package in PACKAGES:
        for path in package.rglob("*.py"):
            if path.name == "super_game_input_version.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for function in ast.walk(tree):
                if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                calls = [
                    node
                    for node in ast.walk(function)
                    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == HELPER
                ]
                if calls:
                    module = ".".join(path.relative_to(package).with_suffix("").parts)
                    found.add((module, function.name))
    assert found == listed


def test_sources_are_known_and_cover_the_task_categories() -> None:
    assert {
        "symbol_cells",
        "symbol_cell_backfill",
        "board_source_cleanup",
        "symbol_role",
        "super_game_kind",
        "rules_publication",
    } <= SUPER_GAME_INPUT_SOURCES
    with pytest.raises(ValueError, match="SUPER_GAME_INPUT_SOURCE_UNKNOWN"):
        record_super_game_input_change(object(), object(), source="unlisted")  # type: ignore[arg-type]


class _StubSession:
    def __init__(self, record: object) -> None:
        self.record = record

    def get(self, _model: object, _key: object) -> object:
        return self.record

    def flush(self) -> None:
        return None


class _StubRouter:
    def describe(self, _session: object, game_id: UUID) -> object:
        return GameStorageRouter._in_memory_v2(game_id)  # noqa: SLF001


def test_save_game_bumps_on_layout_count_and_kind_changes_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audit P0-1: ``expected_layout_count`` bounds the derivation, so it is input."""

    calls: list[str] = []

    def recorder(_session: object, _game_id: UUID, *, source: str) -> bool:
        calls.append(source)
        return True

    monkeypatch.setattr(catalog_repository, "record_super_game_input_change", recorder)
    now = datetime.now(UTC)
    record = GameModel(
        id=uuid4(),
        code="mumie",
        name="Mumie",
        status=GameStatus.DRAFT,
        expected_layout_count=1_000,
        shape_geometry_configuration=None,
        super_game_kind="wild_super_spins",
        created_at=now,
        updated_at=now,
    )
    repository = catalog_repository.SqlAlchemyCatalogRepository(
        _StubSession(record),  # type: ignore[arg-type]
        _StubRouter(),  # type: ignore[arg-type]
    )
    game = catalog_repository._to_game(record)  # noqa: SLF001

    repository.save_game(replace(game, name="Renamed", status=GameStatus.ACTIVE))
    assert calls == []
    repository.save_game(replace(game, expected_layout_count=500))
    assert calls == ["expected_layout_count"]
    assert record.expected_layout_count == 500
    repository.save_game(replace(game, expected_layout_count=500, super_game_kind="none"))
    assert calls == ["expected_layout_count", "super_game_kind"]
