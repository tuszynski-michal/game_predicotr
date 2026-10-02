"""TASK-0794: slimming and retention of prediction revisions, migration 0137.

Runs on a dedicated ``*_test`` database only (fixture from the TASK-0790
test).  A full and a partial board are resolved through the Reviewer
endpoint; prediction revisions in the pre-TASK-0794 shape (``virtualCell``
with the full ``renderSpec`` from the board render manifest) are inserted
with SQL, as the former writers stored them.  The partial board's review
item is then made a superseded item without cells (the retention case).

- the slim preview is read-only; ``--execute`` (the script itself, in
  batches of two) stores the v1 digest, removes ``renderSpec``, keeps the v2
  digest, the crop-manifest and model checksums; a second run changes nothing;
- retention never deletes the revisions of an item with a reference-library
  revision, and deletes the others;
- 0137 added a validated format CHECK; its downgrade refuses while a legacy
  digest exists and drops the column otherwise.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from game_predictor_api.domain.prediction_revisions import (
    has_virtual_render_spec,
    predictions_digest,
)
from game_predictor_api.storage.prediction_revision_slimming import (
    LIBRARY_MODEL_VERSION,
    preview_retention,
    preview_slim,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from test_cell_render_specs_postgres import _boards, _resolve_full_and_partial
from test_virtual_deferred_resolution_postgres import (
    _Database,
    _factory,
    _provision_game,
    _seed,
    database,  # noqa: F401
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

_REVISIONS = "game_data_v2.image_symbol_prediction_revisions"
_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "slim_prediction_revisions.py"


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("slim_prediction_revisions", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _old_digest(predictions: list[dict[str, Any]]) -> str:
    """The pre-TASK-0794 ``predictions_digest`` (v1), copied verbatim."""

    canonical = json.dumps(
        list(predictions), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _full_predictions(engine: Engine, game_id: UUID, board_id: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        manifest = connection.execute(
            text(
                """SELECT cells, extractor_version FROM game_data_v2.board_render_manifests
                WHERE game_id = :g AND recognized_board_id = :b"""
            ),
            {"g": game_id, "b": board_id},
        ).one()
    predictions: list[dict[str, Any]] = []
    for cell in manifest.cells["cells"]:
        spec = cell["renderSpec"]
        predictions.append(
            {
                "rowIndex": spec["rowIndex"],
                "columnIndex": spec["columnIndex"],
                "symbolCode": "CYTRYNA",
                "confidence": 0.6180339887,
                "alternatives": [{"symbolCode": "CYTRYNA", "confidence": 0.6180339887}],
                "virtualCell": {
                    "cropChecksumSha256": cell["renderedPixelChecksumSha256"],
                    "extractorVersion": manifest.extractor_version,
                    "logicalCellKeySha256": cell["logicalCellKeySha256"],
                    "renderSpec": spec,
                    "renderSpecChecksumSha256": cell["renderSpecChecksumSha256"],
                    "renderedPixelChecksumSha256": cell["renderedPixelChecksumSha256"],
                },
            }
        )
    return predictions


def _insert_revision(
    engine: Engine,
    *,
    game_id: UUID,
    item_id: UUID,
    board_id: UUID,
    job_id: UUID,
    predictions: list[dict[str, Any]],
    model_version: str = "symbol-model-test-v1",
) -> UUID:
    revision_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                f"""INSERT INTO {_REVISIONS} (id, game_id, review_item_id, recognized_board_id,
                    source_job_id, model_version, model_checksum_sha256,
                    crop_manifest_checksum_sha256, predictions)
                VALUES (:id, :g, :item, :board, :job, :model_version, :model, :crop,
                    CAST(:predictions AS jsonb))"""
            ),
            {
                "id": revision_id,
                "g": game_id,
                "item": item_id,
                "board": board_id,
                "job": job_id,
                "model_version": model_version,
                "model": hashlib.sha256(revision_id.bytes).hexdigest(),
                "crop": hashlib.sha256(b"crop" + revision_id.bytes).hexdigest(),
                "predictions": json.dumps(predictions),
            },
        )
    return revision_id


def _rows(engine: Engine, game_id: UUID) -> dict[UUID, dict[str, Any]]:
    with engine.connect() as connection:
        return {
            row.id: dict(row._mapping)
            for row in connection.execute(
                text(
                    f"""SELECT id, predictions, legacy_predictions_sha256,
                        model_checksum_sha256, crop_manifest_checksum_sha256
                    FROM {_REVISIONS} WHERE game_id = :g"""
                ),
                {"g": game_id},
            )
        }


def _make_superseded_without_cells(engine: Engine, game_id: UUID, item_id: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """DELETE FROM game_data_v2.image_symbol_review_events
                WHERE cell_review_id IN (SELECT id FROM game_data_v2.image_symbol_review_cells
                    WHERE game_id = :g AND review_item_id = :item)"""
            ),
            {"g": game_id, "item": item_id},
        )
        connection.execute(
            text(
                """DELETE FROM game_data_v2.image_symbol_review_cells
                WHERE game_id = :g AND review_item_id = :item"""
            ),
            {"g": game_id, "item": item_id},
        )
        connection.execute(
            text(
                """UPDATE game_data_v2.image_review_items
                SET status = 'superseded', resolved_value = '{}'::jsonb,
                    resolved_by = 'task-0794-test', resolved_at = now(),
                    resolution_revision = resolution_revision + 1
                WHERE game_id = :g AND id = :item"""
            ),
            {"g": game_id, "item": item_id},
        )


def test_slimming_retention_and_migration_0137(
    database: _Database,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = database.engine
    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(engine, "task0794-slim")
    factory = _factory(engine)
    seed = _seed(factory, game_id, artifact_root, label="task0794-source", slot_count=2)
    _resolve_full_and_partial(database, artifact_root, seed)
    with factory() as session:
        boards = _boards(session, game_id)
    (full_board, _p, full_item, job_id), (partial_board, _q, partial_item, _j) = boards

    full = _full_predictions(engine, game_id, full_board)
    partial = _full_predictions(engine, game_id, partial_board)
    kept_full = _insert_revision(
        engine,
        game_id=game_id,
        item_id=full_item,
        board_id=full_board,
        job_id=job_id,
        predictions=full,
    )
    retained = [
        _insert_revision(
            engine,
            game_id=game_id,
            item_id=partial_item,
            board_id=partial_board,
            job_id=job_id,
            predictions=partial,
        )
        for _ in range(2)
    ]
    anchor = _insert_revision(
        engine,
        game_id=game_id,
        item_id=partial_item,
        board_id=partial_board,
        job_id=job_id,
        predictions=partial,
        model_version=LIBRARY_MODEL_VERSION,
    )
    _make_superseded_without_cells(engine, game_id, partial_item)
    before = _rows(engine, game_id)
    assert len(before) == 4
    assert all(has_virtual_render_spec(row["predictions"]) for row in before.values())
    v1 = {revision_id: _old_digest(row["predictions"]) for revision_id, row in before.items()}
    v2 = {
        revision_id: predictions_digest(row["predictions"]) for revision_id, row in before.items()
    }

    # The ORM refuses a new revision with a render-spec copy.
    from game_predictor_api.domain.prediction_revisions import PredictionRevisionShapeError
    from game_predictor_api.storage.models import ImageSymbolPredictionRevisionModel

    with pytest.raises(PredictionRevisionShapeError):
        ImageSymbolPredictionRevisionModel(predictions=full)

    # Read-only previews.
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        plan = preview_slim(connection, game_id=game_id, sample_size=10)
        retention = preview_retention(connection, game_id=game_id)
        connection.rollback()
    assert plan["legacyDigestColumnPresent"] is True
    assert plan["revisions"] == plan["pendingRevisions"] == 4
    assert plan["sample"]["digestV2Mismatches"] == 0
    assert retention["revisions"] == 0  # the library revision anchors the item
    assert _rows(engine, game_id) == before

    # Execute the script in batches of two; the report and checkpoint go to tmp.
    monkeypatch.setenv("GAME_PREDICTOR_DATABASE_URL", database.url)
    monkeypatch.setenv("GAME_PREDICTOR_ARTIFACT_ROOT", str(artifact_root))
    script = _script()
    report_dir = tmp_path / "reports"
    assert (
        script.main(
            [
                "--game-id",
                str(game_id),
                "--execute",
                "--batch-size",
                "2",
                "--report-dir",
                str(report_dir),
            ]
        )
        == 0
    )
    after = _rows(engine, game_id)
    for revision_id, row in after.items():
        assert not has_virtual_render_spec(row["predictions"])
        assert row["legacy_predictions_sha256"] == v1[revision_id]
        assert predictions_digest(row["predictions"]) == v2[revision_id]
        assert row["model_checksum_sha256"] == before[revision_id]["model_checksum_sha256"]
        assert (
            row["crop_manifest_checksum_sha256"]
            == before[revision_id]["crop_manifest_checksum_sha256"]
        )
        assert [entry["symbolCode"] for entry in row["predictions"]] == [
            entry["symbolCode"] for entry in before[revision_id]["predictions"]
        ]
    reports = sorted(report_dir.glob("*-slim-execute.json"))
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert report["completed"] is True and report["error"] is None
    assert report["totals"] == {"alreadySlim": 0, "batches": 2, "scanned": 4, "slimmed": 4}
    assert report["storedPredictionBytesAfter"] < report["storedPredictionBytesBefore"]
    checkpoint = json.loads((report_dir / "slim-checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["completed"] is True and checkpoint["lastId"] is None

    # A second run changes nothing.
    assert (
        script.main(["--game-id", str(game_id), "--execute", "--report-dir", str(report_dir)]) == 0
    )
    again = json.loads(sorted(report_dir.glob("*-slim-execute.json"))[-1].read_text("utf-8"))
    assert again["totals"]["scanned"] == 0
    assert _rows(engine, game_id) == after

    # Retention: removing the anchor makes the item's revisions removable.
    with engine.begin() as connection:
        connection.execute(text(f"DELETE FROM {_REVISIONS} WHERE id = :id"), {"id": anchor})
    with engine.connect() as connection:
        assert preview_retention(connection, game_id=game_id)["revisions"] == 2
    assert (
        script.main(
            [
                "--game-id",
                str(game_id),
                "--mode",
                "retention",
                "--execute",
                "--report-dir",
                str(report_dir),
            ]
        )
        == 0
    )
    remaining = _rows(engine, game_id)
    assert set(remaining) == {kept_full}
    assert not set(retained) & set(remaining)

    # 0137: validated CHECK; downgrade refuses while a legacy digest exists.
    with engine.connect() as connection:
        validated = connection.execute(
            text(
                """SELECT convalidated FROM pg_constraint
                WHERE conname = 'ck_image_symbol_prediction_revisions_legacy_digest'
                  AND conrelid = 'game_data_v2.image_symbol_prediction_revisions'::regclass"""
            )
        ).scalar_one()
    assert validated is True
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(
            text(f"UPDATE {_REVISIONS} SET legacy_predictions_sha256 = 'x' WHERE id = :id"),
            {"id": kept_full},
        )
    with pytest.raises(Exception, match="PREDICTION_REVISION_LEGACY_DIGEST_PRESENT"):
        command.downgrade(database.config, "0136_drop_cell_render_spec")
    with engine.begin() as connection:
        connection.execute(text(f"UPDATE {_REVISIONS} SET legacy_predictions_sha256 = NULL"))
    command.downgrade(database.config, "0136_drop_cell_render_spec")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    """SELECT count(*) FROM information_schema.columns
                    WHERE table_schema = 'game_data_v2'
                      AND column_name = 'legacy_predictions_sha256'"""
                )
            ).scalar_one()
            == 0
        )
    command.upgrade(database.config, "head")
