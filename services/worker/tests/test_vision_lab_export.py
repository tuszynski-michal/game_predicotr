"""Integrity and publication contracts of the standalone vision-lab exporter."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from game_predictor_api.storage.game_storage_routing import GameStorageIntent
from sqlalchemy import Engine as SqlAlchemyEngine

from scripts import vision_lab_export as exporter

GAME_ID = "0b0ec5fd-967e-4d55-8af9-61de2ef8332c"
SOURCE_ID = "222466b6-a283-4aa7-9b7a-370a2872def2"


@pytest.fixture
def workspace_path() -> Any:
    root = Path.cwd().resolve()
    target = (root / ".test-artifacts" / uuid4().hex[:8]).resolve()
    if not target.is_relative_to(root):
        raise RuntimeError("Test path escaped the workspace")
    target.mkdir(parents=True)
    try:
        yield target
    finally:
        shutil.rmtree(target)


def _manifest(checksum: str, role: str = "data") -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "datasetName": "pilot",
        "entries": [
            {
                "gameId": GAME_ID,
                "sourceImageId": SOURCE_ID,
                "expectedSourceSha256": checksum,
                "sourceFamilyId": "recording-1",
                "role": role,
            }
        ],
    }


def _managed_image(root: Path, contents: bytes) -> str:
    checksum = hashlib.sha256(contents).hexdigest()
    target = root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(contents)
    return checksum


def test_manifest_validation_rejects_duplicates_and_undeclared_roles() -> None:
    checksum = "a" * 64
    manifest = _manifest(checksum)
    assert exporter.validate_input(manifest)["entries"][0]["expectedSourceSha256"] == checksum
    manifest["entries"].append(dict(manifest["entries"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        exporter.validate_input(manifest)
    manifest["entries"] = [dict(manifest["entries"][0], role="training")]
    with pytest.raises(ValueError, match="role"):
        exporter.validate_input(manifest)


def test_database_transaction_is_read_only_and_pins_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[str] = []

    class Connection:
        info: dict[str, int] = {}

        def exec_driver_sql(self, statement: str) -> None:
            statements.append(statement)

        def execute(self, statement: object, _params: object) -> None:
            statements.append(str(statement))

        def rollback(self) -> None:
            statements.append("ROLLBACK")

    connection = Connection()

    class Engine:
        def connect(self) -> Any:
            @contextmanager
            def opened() -> Any:
                yield connection

            return opened()

    class Session:
        def __init__(self, *, bind: object) -> None:
            assert bind is connection

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    class Router:
        def bind(
            self,
            _session: object,
            game_id: UUID,
            *,
            intent: object,
            expected_generation: int | None,
        ) -> Any:
            assert game_id == UUID(GAME_ID)
            assert intent is GameStorageIntent.READ
            assert expected_generation == 3
            return SimpleNamespace(status=SimpleNamespace(value="active"), generation=3)

    monkeypatch.setattr(exporter, "Session", Session)
    monkeypatch.setattr(exporter, "GameStorageRouter", Router)
    with exporter._read_transaction(Engine(), UUID(GAME_ID), 3) as routed:  # type: ignore[arg-type]
        assert routed.info["vision_export_generation"] == 3
    assert statements[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    assert "statement_timeout" in statements[1]
    assert "idle_in_transaction_session_timeout" in statements[2]
    assert statements[-1] == "ROLLBACK"


def test_read_only_snapshot_retry_verifies_every_file(
    workspace_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = workspace_path / "a"
    checksum = _managed_image(artifacts, b"JPEG bytes for export")
    output = workspace_path / "o"
    monkeypatch.setattr(exporter, "freeze_export_identity", lambda *_: ("b" * 64, []))
    monkeypatch.setattr(exporter, "_export_rows", lambda *_: {})
    first = exporter.export_snapshot(None, _manifest(checksum), artifacts, output)  # type: ignore[arg-type]
    assert first == output / ("b" * 64)
    assert (
        first / "images" / checksum[:2] / f"{checksum}.jpg"
    ).read_bytes() == b"JPEG bytes for export"
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,sys; from pathlib import Path; "
            "from scripts.vision_lab_export import _verify_published; "
            "p=Path(sys.argv[1]); _verify_published(p,json.loads((p/'manifest.json').read_text()))",
            str(first),
        ],
        check=True,
        timeout=10,
        cwd=Path.cwd(),
    )
    assert exporter.export_snapshot(None, _manifest(checksum), artifacts, output) == first  # type: ignore[arg-type]
    (first / "approved_labels.json").write_text("corrupt", encoding="utf-8")
    with pytest.raises(exporter.ExportIntegrityError, match="differs"):
        exporter.export_snapshot(None, _manifest(checksum), artifacts, output)  # type: ignore[arg-type]
    assert not list(output.glob(".*"))


def test_changed_source_never_publishes(
    workspace_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = workspace_path / "a"
    checksum = _managed_image(artifacts, b"original")
    source = artifacts / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
    source.write_bytes(b"changed")
    monkeypatch.setattr(exporter, "freeze_export_identity", lambda *_: ("c" * 64, []))
    monkeypatch.setattr(exporter, "_export_rows", lambda *_: {})
    output = workspace_path / "o"
    with pytest.raises(exporter.ExportIntegrityError, match="changed or is corrupt"):
        exporter.export_snapshot(None, _manifest(checksum), artifacts, output)  # type: ignore[arg-type]
    assert list(output.iterdir()) == []


def test_row_drift_and_missing_row_never_publish(
    workspace_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    game = UUID(GAME_ID)
    original = {"id": game, "code": "original"}
    reference = exporter.FrozenRow(
        game, "games", (GAME_ID,), exporter._sha(exporter._json(original))
    )

    @contextmanager
    def transaction(*_: Any) -> Any:
        yield object()

    monkeypatch.setattr(exporter, "_read_transaction", transaction)
    monkeypatch.setattr(exporter, "_rows", lambda *_: [{"id": game, "code": "changed"}])
    with pytest.raises(exporter.ExportIntegrityError, match="drifted"):
        exporter._export_rows(None, [reference], workspace_path)  # type: ignore[arg-type]
    monkeypatch.setattr(exporter, "_rows", lambda *_: [])
    with pytest.raises(exporter.ExportIntegrityError, match="Missing"):
        exporter._export_rows(None, [reference], workspace_path)  # type: ignore[arg-type]


def test_referenced_board_and_crop_assets_are_verified(workspace_path: Path) -> None:
    artifacts = workspace_path / "a"
    stage = workspace_path / "s"
    stage.mkdir()
    record_root = stage / "records" / GAME_ID
    record_root.mkdir(parents=True)
    board = b"board pixels"
    crop = b"crop pixels"
    board_checksum = hashlib.sha256(board).hexdigest()
    crop_checksum = hashlib.sha256(crop).hexdigest()
    for relative, contents in (("data/b.png", board), ("data/c.png", crop)):
        path = artifacts / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    (record_root / "recognized_boards.jsonl").write_text(
        json.dumps({"board_relative_path": "data/b.png", "board_checksum_sha256": board_checksum})
        + "\n",
        encoding="utf-8",
    )
    (record_root / "image_board_geometry_revisions.jsonl").write_text(
        json.dumps(
            {
                "board_relative_path": None,
                "board_checksum_sha256": None,
                "crop_artifacts": [
                    {"cropRelativePath": "data/c.png", "cropChecksumSha256": crop_checksum}
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = exporter._copy_referenced_artifacts(_manifest("a" * 64), artifacts, stage)
    assert result == {
        "assets/data/b.png": board_checksum,
        "assets/data/c.png": crop_checksum,
    }
    (artifacts / "data" / "c.png").write_bytes(b"changed")
    with pytest.raises(exporter.ExportIntegrityError, match="changed or is corrupt"):
        exporter._copy_referenced_artifacts(_manifest("a" * 64), artifacts, stage)


def test_comparison_keeps_initial_and_later_revision_separate(workspace_path: Path) -> None:
    checksum = "a" * 64
    root = workspace_path / "records" / GAME_ID
    root.mkdir(parents=True)
    data: dict[str, list[dict[str, Any]]] = {
        "source_images": [{"id": SOURCE_ID, "import_job_id": "job"}],
        "jobs": [
            {
                "id": "job",
                "input_payload": {
                    "lateral_partial_geometry": {"variant": "selective_board_review_v1_1"}
                },
            }
        ],
        "recognized_boards": [
            {
                "id": "board",
                "source_image_id": SOURCE_ID,
                "source_geometry_revision_id": "manual-source",
                "geometry_revision": 1,
                "position_index": 0,
                "sequence_number": 100,
            }
        ],
        "image_source_geometry_revisions": [
            {
                "id": "initial",
                "game_id": GAME_ID,
                "source_image_id": SOURCE_ID,
                "revision": 0,
                "sequence_range_start": 100,
                "engine_kind": "structured_opencv_v1",
                "engine_version": "structured-lattice-v4-selective-frame-v1",
                "geometry_source": "auto",
                "source_checksum_sha256": checksum,
                "active_board_slots": [0],
                "board_geometries": [
                    {"positionIndex": 0, "sequenceNumber": 100, "corners": [1, 2, 3, 4]}
                ],
            },
            {
                "id": "manual-source",
                "game_id": GAME_ID,
                "source_image_id": SOURCE_ID,
                "revision": 1,
                "sequence_range_start": 100,
                "engine_kind": "manual_v1",
                "engine_version": "manual-source-geometry-v1",
                "geometry_source": "manual",
                "source_checksum_sha256": checksum,
                "active_board_slots": [0],
                "board_geometries": [{"positionIndex": 0, "sequenceNumber": 100}],
            },
        ],
        "image_board_geometry_revisions": [
            {"id": "manual", "recognized_board_id": "board", "revision": 1},
        ],
    }
    for name, rows in data.items():
        (root / f"{name}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
    exporter._build_projections(
        workspace_path, exporter.validate_input(_manifest(checksum, "comparison_only"))
    )
    [comparison] = json.loads((workspace_path / "historical_comparisons.json").read_text())
    assert comparison["comparisonAvailable"] is True
    assert comparison["initialV11Revision"] == {
        "sourceGeometryRevisionId": "initial",
        "revision": 0,
        "boardPositionIndex": 0,
        "boardGeometrySha256": exporter._sha(
            exporter._json({"positionIndex": 0, "sequenceNumber": 100, "corners": [1, 2, 3, 4]})
        ),
    }
    assert comparison["laterGeometryRevisions"] == [{"id": "manual", "revision": 1}]
    data["image_source_geometry_revisions"].append(
        dict(data["image_source_geometry_revisions"][0], id="second", revision=2)
    )
    (root / "image_source_geometry_revisions.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in data["image_source_geometry_revisions"]),
        encoding="utf-8",
    )
    exporter._build_projections(
        workspace_path, exporter.validate_input(_manifest(checksum, "comparison_only"))
    )
    [comparison] = json.loads((workspace_path / "historical_comparisons.json").read_text())
    assert comparison["comparisonAvailable"] is True
    assert comparison["initialV11Revision"]["sourceGeometryRevisionId"] == "initial"
    data["recognized_boards"][0]["position_index"] = 1
    data["recognized_boards"][0]["sequence_number"] = 101
    (root / "recognized_boards.jsonl").write_text(
        json.dumps(data["recognized_boards"][0]) + "\n", encoding="utf-8"
    )
    exporter._build_projections(
        workspace_path, exporter.validate_input(_manifest(checksum, "comparison_only"))
    )
    [comparison] = json.loads((workspace_path / "historical_comparisons.json").read_text())
    assert comparison["comparisonAvailable"] is False
    data["recognized_boards"][0]["position_index"] = 0
    data["recognized_boards"][0]["sequence_number"] = 100
    (root / "recognized_boards.jsonl").write_text(
        json.dumps(data["recognized_boards"][0]) + "\n", encoding="utf-8"
    )
    (root / "image_source_geometry_revisions.jsonl").unlink()
    exporter._build_projections(
        workspace_path, exporter.validate_input(_manifest(checksum, "comparison_only"))
    )
    [comparison] = json.loads((workspace_path / "historical_comparisons.json").read_text())
    assert comparison["comparisonAvailable"] is False
    assert comparison["initialV11Revision"] is None


def test_approved_projection_enforces_current_training_gate(workspace_path: Path) -> None:
    root = workspace_path / "records" / GAME_ID
    root.mkdir(parents=True)
    board = {"id": "board", "source_image_id": SOURCE_ID, "geometry_revision": 2}
    cell = {
        "game_id": GAME_ID,
        "recognized_board_id": "board",
        "review_item_id": "review",
        "sequence_number": 7,
        "cell_index": 3,
        "geometry_revision": 2,
        "source_available": True,
        "review_state": "approved",
        "quality_issue": None,
        "crop_sample_id": "a" * 64,
        "approved_crop_sample_id": "a" * 64,
        "crop_checksum_sha256": "b" * 64,
        "approved_crop_checksum_sha256": "b" * 64,
        "approved_geometry_revision": 2,
        "asset_mode": "legacy_file",
        "approved_asset_mode": "legacy_file",
        "crop_relative_path": "data/crop.jpg",
        "assigned_symbol_id": "symbol",
        "revision": 4,
        "last_reviewed_at": None,
    }
    symbol = {"id": "symbol", "game_id": GAME_ID, "status": "active"}
    owner = {"sequence_number": 7, "review_item_id": "review", "recognized_board_id": "board"}
    rows: dict[str, list[dict[str, Any]]] = {
        "recognized_boards": [board],
        "image_symbol_review_cells": [cell],
        "symbols": [symbol],
        "image_board_search_fast_documents": [owner],
    }

    def project() -> list[dict[str, Any]]:
        for name, values in rows.items():
            (root / f"{name}.jsonl").write_text(
                "".join(json.dumps(value) + "\n" for value in values), encoding="utf-8"
            )
        exporter._build_projections(workspace_path, exporter.validate_input(_manifest("a" * 64)))
        return cast(
            list[dict[str, Any]],
            json.loads((workspace_path / "approved_labels.json").read_text()),
        )

    assert len(project()) == 1
    board["geometry_revision"] = 3
    assert project() == []
    board["geometry_revision"] = 2
    cell["source_available"] = False
    assert project() == []
    cell["source_available"] = True
    symbol["status"] = "inactive"
    assert project() == []
    symbol["status"] = "active"
    owner["review_item_id"] = "new-owner"
    assert project() == []
    owner["review_item_id"] = "review"
    cell["approved_crop_checksum_sha256"] = "c" * 64
    assert project() == []


def test_existing_snapshot_rejects_reparse_and_ads_paths(
    workspace_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = workspace_path / "snapshot"
    (snapshot / "records").mkdir(parents=True)
    data = snapshot / "records" / "record.jsonl"
    data.write_bytes(b"{}\n")
    payload = {"files": {"records/record.jsonl": exporter._sha(data.read_bytes())}}
    (snapshot / "manifest.json").write_bytes(exporter._json(payload) + b"\n")
    exporter._verify_published(snapshot, payload)
    with pytest.raises(exporter.ExportIntegrityError, match="escapes"):
        exporter._snapshot_file(snapshot, "records/record.jsonl:stream")
    with pytest.raises(exporter.ExportIntegrityError, match="escapes"):
        exporter._snapshot_file(snapshot, "records:stream/record.jsonl")

    original_lstat = Path.lstat
    for blocked in (snapshot, snapshot / "manifest.json", snapshot / "records", data):

        def fake_lstat(path: Path, *args: Any, blocked_path: Path = blocked, **kwargs: Any) -> Any:
            result = original_lstat(path, *args, **kwargs)
            if path == blocked_path:
                return SimpleNamespace(
                    st_mode=result.st_mode,
                    st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024),
                )
            return result

        with monkeypatch.context() as patch:
            patch.setattr(Path, "lstat", fake_lstat)
            with pytest.raises(exporter.ExportIntegrityError, match="link or reparse"):
                exporter._verify_published(snapshot, payload)


def test_publish_conflict_and_interruption_do_not_overwrite_snapshot(
    workspace_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = workspace_path / "output"
    output.mkdir()
    existing = output / ("d" * 64)
    existing.mkdir()
    (existing / "manifest.json").write_bytes(exporter._json({"files": {}, "other": True}))
    stage = output / ".stage-test"
    stage.mkdir()
    with pytest.raises(exporter.ExportIntegrityError, match="conflicts"):
        exporter.publish_snapshot(stage, existing, {"files": {}})
    assert (existing / "manifest.json").read_bytes() == exporter._json({"files": {}, "other": True})
    shutil.rmtree(stage)
    artifacts = workspace_path / "artifacts"
    checksum = _managed_image(artifacts, b"original")
    monkeypatch.setattr(exporter, "freeze_export_identity", lambda *_: ("e" * 64, []))
    monkeypatch.setattr(
        exporter, "_export_rows", lambda *_: (_ for _ in ()).throw(RuntimeError("interrupted"))
    )
    with pytest.raises(RuntimeError, match="interrupted"):
        exporter.export_snapshot(None, _manifest(checksum), artifacts, output)  # type: ignore[arg-type]
    assert not (output / ("e" * 64)).exists()
    assert not list(output.glob(".stage-*"))


def test_freeze_routes_each_game_in_one_read_only_postgresql_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    second_game = "dbb06968-44c2-4e63-8db1-822202a80eae"
    statements: list[str] = []
    routing: list[tuple[str, str | None]] = []

    class Connection:
        def __init__(self) -> None:
            self.info: dict[str, Any] = {}

        def exec_driver_sql(self, statement: str) -> None:
            statements.append(statement)

        def execute(self, statement: object, _params: object) -> None:
            statements.append(str(statement))

        def rollback(self) -> None:
            statements.append("ROLLBACK")

    connection = Connection()

    class Engine:
        def connect(self) -> Any:
            @contextmanager
            def opened() -> Any:
                yield connection

            return opened()

    class Session:
        def __init__(self, *, bind: object) -> None:
            assert bind is connection

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    class Router:
        def clear_session_binding(self, _session: object) -> None:
            routing.append(("clear", None))

        def bind(
            self,
            _session: object,
            game_id: UUID,
            *,
            intent: object,
            expected_generation: int | None,
        ) -> Any:
            assert intent is GameStorageIntent.READ
            assert expected_generation is None
            routing.append(("bind", str(game_id)))
            return SimpleNamespace(status=SimpleNamespace(value="active"), generation=7)

    monkeypatch.setattr(exporter, "Session", Session)
    monkeypatch.setattr(exporter, "GameStorageRouter", Router)
    monkeypatch.setattr(
        exporter,
        "_freeze_game",
        lambda _connection, game_id, _entries: {"games": [{"id": game_id}]},
    )
    manifest = _manifest("a" * 64)
    manifest["entries"].append(
        dict(manifest["entries"][0], gameId=second_game, sourceImageId=str(uuid4()))
    )
    snapshot_id, frozen = exporter.freeze_export_identity(
        cast(SqlAlchemyEngine, Engine()),
        exporter.validate_input(manifest),
    )
    assert len(snapshot_id) == 64
    assert len(frozen) == 2
    assert all(row.storage_generation == 7 for row in frozen)
    assert routing == [("clear", None), ("bind", GAME_ID), ("clear", None), ("bind", second_game)]
    assert statements[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    assert statements[-1] == "ROLLBACK"
