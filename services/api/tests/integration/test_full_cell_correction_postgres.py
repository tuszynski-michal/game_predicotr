"""8% history and 0% manual rendering survive a fresh API process/session."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import test_virtual_deferred_resolution_postgres as deferred_fixture
from fastapi.testclient import TestClient
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.storage import game_partition_lifecycle
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyGridCorrectionSymbolRepository,
    SqlAlchemyImageSymbolReviewRepository,
)
from game_predictor_api.storage.models import (
    BoardRenderManifestModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SymbolModel,
)
from game_predictor_api.storage.symbol_cell_training_source_repository import (
    SqlAlchemySymbolCellTrainingSourceRepository,
)
from sqlalchemy import select, text
from test_reviewer_operational_geometry_postgres import _add_symbols, _app
from test_virtual_deferred_resolution_postgres import (
    _corners,
    _Database,
    _factory,
    _provision_game,
    _resolve_via_reviewer_endpoint,
    _seed,
    database,  # noqa: F401
    pytestmark,  # noqa: F401
)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def test_new_full_cells_preserve_old_pins_and_reopen_changed_symbols_after_restart(
    database: _Database,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(deferred_fixture, "CREATE_TABLES", game_partition_lifecycle.CREATE_TABLES)
    game = _provision_game(database.engine, "task1175-full-field")
    factory = _factory(database.engine)
    seed = _seed(factory, game, tmp_path, label="full-field", slot_count=1)
    _add_symbols(factory, game)
    pending_base = (
        f"/api/v1/admin/games/{game}/image-imports/{seed.import_job_id}"
        f"/board-cell-geometry-pending/{seed.pending_ids[0]}"
    )
    pending_command = dict(
        corners=_corners(),
        expectedGeometryRevision=0,
        expectedResolutionRevision=0,
        expectedManifestChecksumSha256=seed.manifest_checksums[0],
        cropPolicyVersion="full-cell-v2",
    )
    app = _app(database, tmp_path)
    try:
        with TestClient(app) as client:
            preview = client.post(pending_base + "/geometry-preview", json=pending_command)
            inset_preview = client.post(
                pending_base + "/geometry-preview",
                json={k: v for k, v in pending_command.items() if k != "cropPolicyVersion"},
            )
            symbols = client.post(pending_base + "/geometry-symbol-preview", json=pending_command)
    finally:
        app.state.database_engine.dispose()
    assert preview.status_code == 200, preview.text
    assert symbols.status_code == 200, symbols.text
    assert preview.headers["x-board-cell-count"] == "15"
    assert inset_preview.status_code == 200
    assert preview.content != inset_preview.content
    # Both sheets contain real production renders from the same source; only
    # the inset changed. These fixture images are not operator quality evidence.
    (tmp_path / "full-0.png").write_bytes(preview.content)
    (tmp_path / "inset-8.png").write_bytes(inset_preview.content)

    # A legacy caller still creates its original 8% crop. This is history,
    # not a migration of the existing import to a new classifier contract.
    legacy = _resolve_via_reviewer_endpoint(database, tmp_path, seed)
    review_id = UUID(legacy["reviewItemId"])
    with game_storage_scope(game), factory.begin() as session:
        projection = SqlAlchemyImageSymbolReviewRepository(session)
        projection.start_or_resume_backfill(game)
        for _ in range(5):
            state = projection.backfill_next_batch(game, batch_size=10).report.status
            if state == "ready":
                break
            assert state == "rebuilding"
        else:
            pytest.fail("The one-board fixture projection did not become ready")
    with game_storage_scope(game), factory.begin() as session:
        symbol = session.scalar(select(SymbolModel.id).where(SymbolModel.game_id == game))
        assert symbol is not None
        SqlAlchemyGridCorrectionSymbolRepository(session).assign(
            game_id=game,
            review_item_id=review_id,
            symbol_id_by_cell_index={0: symbol},
            actor="owner",
        )
    with game_storage_scope(game), factory() as session:
        board_id = session.scalar(
            select(RecognizedBoardModel.id).where(
                RecognizedBoardModel.source_image_id == seed.source_image_id
            )
        )
        old = session.get(BoardRenderManifestModel, (game, board_id, 1))
        assert old is not None
        old_sha = _digest(old.cells)
        old_pin = _digest(session.get(JobModel, seed.import_job_id).input_payload)
        cell = session.scalar(
            select(ImageSymbolReviewCellModel).where(
                ImageSymbolReviewCellModel.review_item_id == review_id,
                ImageSymbolReviewCellModel.cell_index == 0,
            )
        )
        assert cell.review_state == "approved"
        previous_crop = cell.crop_checksum_sha256
        old_pixel_shas = [c["renderedPixelChecksumSha256"] for c in old.cells["cells"]]
        event_sql = text(
            "SELECT id::text,md5(to_jsonb(e)::text) FROM image_symbol_review_events e "
            "WHERE game_id=:game"
        )
        old_events = dict(session.execute(event_sql, {"game": game}).all())
        assert old_events
        assert old.cells["cells"][0]["renderSpec"]["configuration"]["paddingFraction"] == 0.08
        freeze_fence = SqlAlchemySymbolCellTrainingSourceRepository(
            session, tmp_path
        ).capture_freeze_fence(game_id=game)
    files = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    scope = dict(gameId=str(game), importJobId=str(seed.import_job_id))
    base = f"/api/v1/admin/image-review-items/{review_id}"
    command = dict(
        corners=_corners(),
        expectedGeometryRevision=1,
        expectedResolutionRevision=0,
        cropPolicyVersion="full-cell-v2",
        idempotencyKey=str(uuid4()),
        correctedBy="owner",
    )
    app = _app(database, tmp_path)
    try:
        with TestClient(app) as client:
            preview = client.post(
                base + "/geometry-preview",
                params=scope,
                json={
                    k: v for k, v in command.items() if k not in {"idempotencyKey", "correctedBy"}
                },
            )
            saved = client.post(base + "/geometry-revisions", params=scope, json=command)
    finally:
        app.state.database_engine.dispose()
    assert preview.status_code == 200, preview.text
    assert saved.status_code == 200, saved.text
    assert saved.json()["created"] is True
    with game_storage_scope(game), factory() as session:
        with pytest.raises(ImageReviewConflictError) as stale:
            SqlAlchemySymbolCellTrainingSourceRepository(session, tmp_path).require_freeze_fence(
                game_id=game, expected=freeze_fence
            )
        assert stale.value.code == "VERIFIED_TRAINING_COHORT_PREVIEW_STALE"
    # Real new interpreter: neither ORM objects nor module globals survive.
    command_path = tmp_path.parent / "cold-command.json"
    response_path = tmp_path.parent / "cold-response.json"
    command_path.write_text(json.dumps(command), encoding="utf-8")
    root = Path(__file__).resolve().parents[4]
    child_env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            str(root / p)
            for p in ("services/api/src", "services/worker/src", "services/test_support")
        ),
        "PYTHONUTF8": "1",
        "GAME_PREDICTOR_DATABASE_URL": database.url,
        "GAME_PREDICTOR_OWNER_DATABASE_URL": database.url,
        "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path),
    }
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("_full_cell_cold_replay.py")),
            str(command_path),
            str(game),
            str(seed.import_job_id),
            str(review_id),
            str(response_path),
        ],
        env=child_env,
        capture_output=True,
        timeout=40,
        check=True,
    )
    cold = json.loads(response_path.read_text(encoding="utf-8"))
    assert cold["pid"] != os.getpid()
    assert cold["status"] == 200, cold["body"]
    assert cold["body"]["created"] is False
    assert cold["body"]["geometryRevision"]["id"] == saved.json()["geometryRevision"]["id"]
    app = _app(database, tmp_path)
    try:
        with TestClient(app) as client:
            replay = client.post(base + "/geometry-revisions", params=scope, json=command)
            changed_policy = client.post(
                base + "/geometry-revisions",
                params=scope,
                json={k: v for k, v in command.items() if k != "cropPolicyVersion"},
            )
            unknown = client.post(
                base + "/geometry-revisions",
                params=scope,
                json={**command, "cropPolicyVersion": "future"},
            )
    finally:
        app.state.database_engine.dispose()
    assert replay.status_code == 200, replay.text
    assert replay.json()["created"] is False
    assert replay.json()["geometryRevision"]["id"] == saved.json()["geometryRevision"]["id"]
    assert changed_policy.status_code == 409, changed_policy.text
    assert unknown.status_code == 422
    with game_storage_scope(game), factory() as session:
        old = session.get(BoardRenderManifestModel, (game, board_id, 1))
        new = session.get(BoardRenderManifestModel, (game, board_id, 2))
        assert _digest(old.cells) == old_sha
        assert _digest(session.get(JobModel, seed.import_job_id).input_payload) == old_pin
        assert len(new.cells["cells"]) == 15
        assert all(
            a != b["renderedPixelChecksumSha256"]
            for a, b in zip(old_pixel_shas, new.cells["cells"], strict=True)
        )
        new_events = dict(session.execute(event_sql, {"game": game}).all())
        assert all(new_events.get(key) == value for key, value in old_events.items())
        assert {
            c["renderSpec"]["configuration"]["paddingFraction"] for c in new.cells["cells"]
        } == {0.0}
        cell = session.scalar(
            select(ImageSymbolReviewCellModel).where(
                ImageSymbolReviewCellModel.review_item_id == review_id,
                ImageSymbolReviewCellModel.cell_index == 0,
            )
        )
        assert cell.geometry_revision == 2
        assert cell.crop_checksum_sha256 != previous_crop
        assert cell.review_state == "pending"
    assert {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in tmp_path.rglob("*")
        if p.is_file()
    } == files
