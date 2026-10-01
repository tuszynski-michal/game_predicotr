from __future__ import annotations

import argparse
import json
from contextlib import nullcontext
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from game_predictor_api.domain.cell_level_verification_migration import (
    BoardMigrationPlan,
    CellLevelMigrationError,
    build_manifest,
    plan_board_migration,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError
from game_predictor_api.storage.cell_level_verification_migration_repository import (
    CellLevelMigrationInvariantError,
)

GAME_ID = UUID("bfc4f949-5c14-4850-b02a-db99610bcfa5")
IDS = [UUID(f"00000000-0000-4000-8000-00000000000{index}") for index in range(1, 4)]


def _script() -> ModuleType:
    path = Path(__file__).parents[3] / "scripts" / "migrate_cell_level_verification.py"
    spec = spec_from_file_location("migrate_cell_level_verification", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Session:
    def connection(self) -> Any:
        return SimpleNamespace(execute=lambda statement: None)


class _Sessions:
    def begin(self) -> Any:
        return nullcontext(_Session())


def _plans() -> list[BoardMigrationPlan]:
    return [
        plan_board_migration(
            review_item_id=review_item_id,
            sequence_number=index,
            status="pending",
            fingerprint="f" * 64,
            changed_pixel_approvals=(),
            resolution_after_recheck=None,
            projection_stale=True,
        )
        for index, review_item_id in enumerate(IDS, start=1)
    ]


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    script: ModuleType,
    outcomes: dict[UUID, Exception | dict[str, Any]],
) -> list[UUID]:
    """Replace the database with fakes; returns the boards apply touched."""

    touched: list[UUID] = []

    class _Repository:
        def __init__(self, session: object) -> None:
            self.session = session

        def require_ready_game(self, game_id: UUID) -> None:
            assert game_id == GAME_ID

        def preview(self, game_id: UUID, **_: object) -> dict[str, Any]:
            return build_manifest(game_id=game_id, plans=_plans(), scanned=3, generated_at="now")

        def apply_board(self, game_id: UUID, plan: BoardMigrationPlan) -> dict[str, Any]:
            touched.append(plan.review_item_id)
            outcome = outcomes.get(
                plan.review_item_id,
                {"reviewItemId": str(plan.review_item_id), "result": "applied"},
            )
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(script, "ApiSettings", SimpleNamespace(from_environment=lambda: None))
    monkeypatch.setattr(script, "create_maintenance_database_engine", lambda settings: None)
    monkeypatch.setattr(script, "create_session_factory", lambda engine: _Sessions())
    monkeypatch.setattr(script, "game_storage_scope", lambda game_id: nullcontext())
    monkeypatch.setattr(script, "CellLevelVerificationMigrationRepository", _Repository)
    return touched


def _manifest_file(tmp_path: Path) -> tuple[Path, str]:
    manifest = build_manifest(game_id=GAME_ID, plans=_plans(), scanned=3, generated_at="now")
    path = tmp_path / "preview.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, manifest["previewSha256"]


def _apply_args(tmp_path: Path, sha: str, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "preview": tmp_path / "preview.json",
        "preview_sha256": sha,
        "output": tmp_path / "apply.json",
        "limit": None,
        "after_review_item_id": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_preview_is_immutable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()
    _wire(monkeypatch, script, {})
    output = tmp_path / "preview.json"
    args = argparse.Namespace(game_id=GAME_ID, output=output, batch_size=500)

    assert script.run_preview(args) == 0
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["counts"]["boards"] == 3
    with pytest.raises(CellLevelMigrationError) as error:
        script.run_preview(args)
    assert error.value.code == "CELL_MIGRATION_OUTPUT_EXISTS"


def test_apply_requires_the_exact_checksum_and_a_new_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _script()
    touched = _wire(monkeypatch, script, {})
    _path, sha = _manifest_file(tmp_path)

    with pytest.raises(CellLevelMigrationError) as wrong:
        script.run_apply(_apply_args(tmp_path, "0" * 64))
    assert wrong.value.code == "CELL_MIGRATION_SCOPE_INVALID"
    (tmp_path / "apply.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CellLevelMigrationError) as existing:
        script.run_apply(_apply_args(tmp_path, sha))
    assert existing.value.code == "CELL_MIGRATION_OUTPUT_INVALID"
    assert touched == []


def test_apply_runs_in_resumable_chunks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()
    touched = _wire(monkeypatch, script, {})
    _path, sha = _manifest_file(tmp_path)

    assert script.run_apply(_apply_args(tmp_path, sha, after_review_item_id=IDS[0], limit=1)) == 0
    report = json.loads((tmp_path / "apply.json").read_text(encoding="utf-8"))
    assert touched == [IDS[1]]
    assert report["lastReviewItemId"] == str(IDS[1])
    assert report["summary"]["applied"] == 1


def test_a_failed_board_is_reported_and_the_run_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _script()
    touched = _wire(
        monkeypatch,
        script,
        {IDS[0]: SymbolCellReviewError("SYMBOL_CELL_REVIEW_MIGRATION_DRIFT", "changed")},
    )
    _path, sha = _manifest_file(tmp_path)

    assert script.run_apply(_apply_args(tmp_path, sha)) == 1
    report = json.loads((tmp_path / "apply.json").read_text(encoding="utf-8"))
    assert touched == IDS
    assert report["results"][0]["result"] == "failed"
    assert report["results"][0]["code"] == "SYMBOL_CELL_REVIEW_MIGRATION_DRIFT"
    assert report["summary"] == {
        "failed": 1,
        "applied": 2,
        "rechecked": 0,
        "reopened": 0,
        "closed": 0,
        "closeMissed": 0,
    }


def test_a_broken_invariant_stops_the_run_with_a_partial_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _script()
    touched = _wire(
        monkeypatch,
        script,
        {IDS[1]: CellLevelMigrationInvariantError("CELL_MIGRATION_NEW_VERIFICATION", "stop")},
    )
    _path, sha = _manifest_file(tmp_path)

    with pytest.raises(CellLevelMigrationInvariantError):
        script.run_apply(_apply_args(tmp_path, sha))
    report = json.loads((tmp_path / "apply.json").read_text(encoding="utf-8"))
    assert touched == IDS[:2]
    assert [result["reviewItemId"] for result in report["results"]] == [str(IDS[0])]
    assert report["fatal"]["reviewItemId"] == str(IDS[1])
    assert report["fatal"]["code"] == "CELL_MIGRATION_NEW_VERIFICATION"
