"""TASK-0807: the D-484 geometry completeness gate in the pipeline (PostgreSQL).

Runs on a dedicated ``*_test`` database only (fixtures of
``test_virtual_deferred_resolution_postgres``: a game provisioned through the
real partition lifecycle, a real source file, deferred slots written by the
production repository). Boards are imported through the worker's import
writer (``SqlAlchemyImagePipelineStore.project_recognition``) with synthetic,
checksum-consistent render data; deferred slots are resolved and boards are
corrected through the real Reviewer endpoints, which render the cells.

The invariant checked after every public operation: an image whose persisted
status is ``geometry_incomplete`` gets no new symbol-review cell and no symbol
evidence in board search; complete images and images admitted by an operator
exception are cut in the same transaction.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
from game_predictor_api.domain.image_geometry_completeness import (
    SourceImageGeometryStatus,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewNotFoundError,
)
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.domain.symbol_model_snapshots import COLD_START_UNCLASSIFIED_INPUT_SIZE
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_geometry_completeness_repository import (
    SqlAlchemyImageGeometryCompletenessRepository,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    REPOINT_GEOMETRY_ENTRY_DIFFERS,
    SourceImageGeometryCompletenessBackfill,
    SqlAlchemyImageGeometryCompletenessStateRepository,
    recompute_source_image_geometry_completeness,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.models import (
    BoardRenderManifestModel,
    ImageBoardSearchCandidateModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_worker.images.orchestration import (
    ImageBatchCandidate,
    ImageFileExecution,
)
from game_predictor_worker.images.pipeline_contract import VIRTUAL_CELL_RENDERER_VERSION
from game_predictor_worker.images.pipeline_execution import StoredImageStageResult
from game_predictor_worker.images.pipeline_store import SqlAlchemyImagePipelineStore
from game_predictor_worker.images.virtual_cell_extraction import (
    VIRTUAL_CELL_INTERPOLATION_VERSION,
)
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker
from test_reviewer_operational_geometry_postgres import _add_symbols, _app
from test_virtual_deferred_resolution_postgres import (
    _PIPELINE,
    _corners,
    _Database,
    _factory,
    _provision_game,
    _Seed,
    _seed,
    database,  # noqa: F401  (pytest fixture)
    pytestmark,  # noqa: F401  (PostgreSQL opt-in)
)

# The renderer pin of the seeded import (the pending-slot path reuses it).
_EXTRACTOR = VIRTUAL_CELL_RENDERER_VERSION
_CONFIGURATION = {
    "extractorVersion": VIRTUAL_CELL_RENDERER_VERSION,
    "interpolation": VIRTUAL_CELL_INTERPOLATION_VERSION,
    "outputHeight": COLD_START_UNCLASSIFIED_INPUT_SIZE,
    "outputWidth": COLD_START_UNCLASSIFIED_INPUT_SIZE,
    "paddingFraction": 0.08,
    "preprocessingVersion": "symbol-rgb-preprocessing-test",
}
_QUAD = [
    {"x": 60.0, "y": 50.0},
    {"x": 560.0, "y": 50.0},
    {"x": 560.0, "y": 350.0},
    {"x": 60.0, "y": 350.0},
]


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _crop_cell(label: str, position: int, index: int) -> dict[str, object]:
    identity = f"{label}:{position}:{index}"
    spec: dict[str, object] = {
        "boardLabel": f"{label}:{position}",
        "cellIndex": index,
        "columnIndex": index % 5,
        "configuration": dict(_CONFIGURATION),
        "geometryRevision": 0,
        "logicalCellKeyV2Sha256": _sha(f"logical-v2:{identity}"),
        "renderIdentityV2Sha256": _sha(f"identity-v2:{identity}"),
        "rowIndex": index // 5,
    }
    pixels = _sha(f"pixels:{identity}")
    return {
        "assetMode": "virtual_source",
        "columnIndex": index % 5,
        "cropChecksumSha256": pixels,
        "extractorVersion": _EXTRACTOR,
        "logicalCellKeySha256": _sha(f"logical:{identity}"),
        "logicalCellKeyV2Sha256": spec["logicalCellKeyV2Sha256"],
        "renderIdentityV2Sha256": spec["renderIdentityV2Sha256"],
        "renderSpec": spec,
        "renderSpecChecksumSha256": sha256_canonical_json(spec),
        "renderedPixelChecksumSha256": pixels,
        "rowIndex": index // 5,
    }


def _stages(
    label: str, positions: Sequence[int], geometry_checksum: str, start: int
) -> dict[str, StoredImageStageResult]:
    def stage(payload: dict[str, object]) -> StoredImageStageResult:
        return StoredImageStageResult(adapter_version="task-0807-stage", payload=payload)

    return {
        "board_detection": stage(
            {
                "boards": [
                    {"confidence": 0.9, "geometry": {"quad": _QUAD}, "positionIndex": position}
                    for position in positions
                ]
            }
        ),
        "board_crops": stage(
            {
                "assetMode": "virtual_source",
                "geometryChecksumSha256": geometry_checksum,
                "boards": [
                    {
                        "assetMode": "virtual_source",
                        "cells": [_crop_cell(label, position, index) for index in range(15)],
                        "completenessStatus": "complete",
                        "cropperVersion": _EXTRACTOR,
                        "geometryChecksumSha256": geometry_checksum,
                        "geometryEngineName": "structured_opencv_v1",
                        "geometryEngineVersion": "task-0807-engine",
                        "gridColumns": 5,
                        "gridRows": 3,
                        "positionIndex": position,
                        "unavailableCellIndices": [],
                    }
                    for position in positions
                ],
            }
        ),
        "sequence_ocr": stage(
            {
                "boards": [
                    {
                        "confidence": 0.99,
                        "normalizedNumber": start + position,
                        "positionIndex": position,
                        "rawText": str(start + position),
                    }
                    for position in positions
                ]
            }
        ),
        "symbol_inference": stage(
            {
                "boards": [
                    {
                        "cells": [
                            {
                                "alternatives": [{"confidence": 0.9, "symbolCode": "CYTRYNA"}],
                                "columnIndex": index % 5,
                                "confidence": 0.9,
                                "rowIndex": index // 5,
                                "symbolCode": "CYTRYNA",
                            }
                            for index in range(15)
                        ],
                        "positionIndex": position,
                    }
                    for position in positions
                ],
                "inferenceMode": "unclassified",
                "modelChecksumSha256": _sha("task-0807-model"),
                "modelVersion": "task-0807-model",
            }
        ),
    }


def _import(
    factory: sessionmaker[Session], seed: _Seed, label: str, positions: Sequence[int]
) -> None:
    """Project the recognition of ``positions`` through the worker's import writer."""

    now = datetime.now(UTC)
    lease_token = uuid4()
    with game_storage_scope(seed.game_id), factory.begin() as session:
        job = session.get(JobModel, seed.import_job_id)
        source = session.get(SourceImageModel, seed.source_image_id)
        assert job is not None and source is not None
        revision = session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(ImageSourceGeometryRevisionModel.source_image_id == source.id)
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        assert revision is not None
        # The import's own source revision has an automatic grid for every
        # recognized position (the seed only wrote deferred slots).
        revision.board_geometries = [
            {
                "disposition": "automatic",
                "finalQuad": _QUAD,
                "positionIndex": entry["positionIndex"],
                "sequenceNumber": entry["sequenceNumber"],
            }
            if entry["positionIndex"] in positions
            else entry
            for entry in revision.board_geometries
        ]
        job.status = JobStatus.PROCESSING
        job.execution_slot = 1
        job.lease_owner = "task-0807-worker"
        job.lease_token = lease_token
        job.lease_expires_at = now + timedelta(hours=1)
        job.heartbeat_at = now
        execution = ImageFileExecution(
            file_execution_key=source.file_execution_key,
            source_checksum_sha256=source.checksum_sha256,
            pipeline_fingerprint=_PIPELINE,
            checkpoint_payload={},
            status="processing",
            review_required=True,
        )
        relative_path = source.relative_path
        geometry_checksum = revision.geometry_checksum_sha256
        start = int(revision.sequence_range_start)
    candidate = ImageBatchCandidate(
        execution=execution,
        order_index=0,
        source_relative_path=relative_path,
        job_id=seed.import_job_id,
        lease_token=lease_token,
        executed_at=now,
    )
    with game_storage_scope(seed.game_id):
        SqlAlchemyImagePipelineStore(factory).project_recognition(
            candidate, stage_results=_stages(label, positions, geometry_checksum, start)
        )
    with game_storage_scope(seed.game_id), factory.begin() as session:
        job = session.get(JobModel, seed.import_job_id)
        assert job is not None
        job.status = JobStatus.WAITING_FOR_REVIEW
        job.execution_slot = None
        job.lease_owner = None
        job.lease_token = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        session.flush()
        # The worker's pause for review refreshes the job's sequence documents.
        projection = SqlAlchemyBoardSearchProjectionRepository(session)
        projection.reconcile_import_job(seed.import_job_id)
        projection.mark_live_projection_ready(seed.game_id)


def _state(factory: sessionmaker[Session], game_id: UUID, source_image_id: UUID) -> dict[str, Any]:
    """Gate status, cells and search evidence of one image (the DB invariant)."""

    with game_storage_scope(game_id), factory() as session:
        source = session.get(SourceImageModel, source_image_id)
        assert source is not None
        board_ids = session.scalars(
            select(RecognizedBoardModel.id).where(
                RecognizedBoardModel.source_image_id == source_image_id,
                RecognizedBoardModel.status != "rejected",
            )
        ).all()
        cells = session.scalar(
            select(func.count())
            .select_from(ImageSymbolReviewCellModel)
            .where(ImageSymbolReviewCellModel.recognized_board_id.in_(board_ids))
        )
        distinct_cells = session.scalar(
            select(
                func.count(
                    func.distinct(
                        func.concat(
                            ImageSymbolReviewCellModel.review_item_id,
                            ":",
                            ImageSymbolReviewCellModel.cell_index,
                        )
                    )
                )
            ).where(ImageSymbolReviewCellModel.recognized_board_id.in_(board_ids))
        )
        candidates = session.scalars(
            select(ImageBoardSearchCandidateModel).where(
                ImageBoardSearchCandidateModel.recognized_board_id.in_(board_ids)
            )
        ).all()
        documents = session.execute(
            text(
                "SELECT count(*) FROM game_data_v2.image_board_search_fast_documents d "
                "WHERE d.game_id = :game_id AND d.recognized_board_id = ANY (:board_ids) "
                "AND EXISTS (SELECT 1 FROM unnest(d.primary_symbol_mobile_codes) code "
                "WHERE code IS NOT NULL)"
            ),
            {"game_id": game_id, "board_ids": list(board_ids)},
        ).scalar_one()
        return {
            "status": source.geometry_completeness_status,
            "evaluated": source.geometry_completeness_evaluated_at is not None,
            "exception_reason": source.geometry_exception_reason,
            "boards": len(board_ids),
            "cells": int(cells or 0),
            "distinct_cells": int(distinct_cells or 0),
            "candidates": len(candidates),
            "candidates_with_evidence": sum(
                bool(candidate.known_evidence_positions) for candidate in candidates
            ),
            "documents_with_evidence": int(documents),
        }


def _report(factory: sessionmaker[Session], game_id: UUID, import_job_id: UUID | None) -> Any:
    with game_storage_scope(game_id), factory() as session:
        report = SqlAlchemyImageGeometryCompletenessRepository(session).completeness_report(
            game_id, import_job_id=import_job_id
        )
        page = SqlAlchemyImageGeometryCompletenessRepository(session).incomplete_images(
            game_id,
            import_job_id=import_job_id,
            completeness_status=SourceImageGeometryStatus.GEOMETRY_INCOMPLETE,
        )
        session.rollback()
    return report, page


def _resolve_slot(db: _Database, artifact_root: Path, seed: _Seed, index: int, key: str) -> Any:
    app = _app(db, artifact_root)
    path = (
        f"/api/v1/admin/games/{seed.game_id}/image-imports/{seed.import_job_id}/"
        f"board-cell-geometry-pending/{seed.pending_ids[index]}/manual-resolution"
    )
    try:
        with TestClient(app) as client:
            return client.post(
                path,
                json={
                    "corners": _corners(),
                    "correctedBy": "task-0807-operator",
                    "expectedGeometryRevision": 0,
                    "expectedManifestChecksumSha256": seed.manifest_checksums[index],
                    "expectedResolutionRevision": 0,
                    "idempotencyKey": key,
                },
            )
    finally:
        app.state.database_engine.dispose()


def _seeded(db: _Database, tmp_path: Path, code: str, slots: int) -> tuple[Any, _Seed, Path]:
    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(db.engine, code)
    factory = _factory(db.engine)
    seed = _seed(factory, game_id, artifact_root, label=code, slot_count=slots)
    _add_symbols(factory, game_id)
    return factory, seed, artifact_root


def test_import_of_eight_of_nine_grids_cuts_nothing_until_the_ninth_is_drawn(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _seeded(database, tmp_path, "task0807-eight", 9)
    # The deferred writer already evaluated the image (all nine deferred).
    assert _state(factory, seed.game_id, seed.source_image_id)["status"] == "geometry_incomplete"

    _import(factory, seed, "task0807-eight", range(8))

    imported = _state(factory, seed.game_id, seed.source_image_id)
    assert imported["status"] == "geometry_incomplete"
    assert imported["boards"] == 8
    assert imported["cells"] == 0
    # The boards keep their sequence document (the current-owner registry the
    # grid correction needs), but no symbol evidence reaches search.
    assert imported["candidates"] == 8
    assert imported["candidates_with_evidence"] == 0
    assert imported["documents_with_evidence"] == 0
    report, page = _report(factory, seed.game_id, seed.import_job_id)
    assert report is not None and report.gate is not None
    assert report.gate.geometry_incomplete == 1
    assert report.gate.withheld_boards == 8
    assert report.gate.withheld_reason_code == "SOURCE_IMAGE_GEOMETRY_INCOMPLETE"
    assert page is not None
    [queued] = page.images
    assert queued.source_image_id == seed.source_image_id
    assert queued.gate_reason_code == "SOURCE_IMAGE_GEOMETRY_INCOMPLETE"

    key = str(uuid4())
    resolved = _resolve_slot(database, artifact_root, seed, 8, key)
    assert resolved.status_code == 200, resolved.text
    complete = _state(factory, seed.game_id, seed.source_image_id)
    assert complete["status"] == "geometry_complete"
    assert complete["boards"] == 9
    # One operation cut all nine boards: 135 cells, no duplicate key.
    assert complete["cells"] == 135
    assert complete["distinct_cells"] == 135
    # The imported boards' symbols now reach search; the drawn board was
    # predicted by the seeded cold-start model, which knows no symbol.
    assert complete["candidates"] == 9
    assert complete["candidates_with_evidence"] == 8

    replay = _resolve_slot(database, artifact_root, seed, 8, key)
    assert replay.status_code == 200, replay.text
    assert replay.json()["created"] is False
    assert _state(factory, seed.game_id, seed.source_image_id)["cells"] == 135


@pytest.mark.parametrize("slots", [9, 4])
def test_a_complete_image_is_cut_like_before(
    database: _Database,  # noqa: F811
    tmp_path: Path,
    slots: int,
) -> None:
    factory, seed, _artifact_root = _seeded(database, tmp_path, f"task0807-full-{slots}", slots)

    _import(factory, seed, f"task0807-full-{slots}", range(slots))

    state = _state(factory, seed.game_id, seed.source_image_id)
    assert state["status"] == "geometry_complete"
    assert state["boards"] == slots
    assert state["cells"] == 15 * slots
    assert state["distinct_cells"] == 15 * slots
    assert state["candidates_with_evidence"] == slots
    assert state["documents_with_evidence"] == slots


def test_operator_exception_cuts_eight_boards_and_is_withdrawn_without_deleting(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, _artifact_root = _seeded(database, tmp_path, "task0807-exception", 9)
    _import(factory, seed, "task0807-exception", range(8))
    game_id = seed.game_id

    with game_storage_scope(game_id), factory.begin() as session:
        exception = SqlAlchemyImageGeometryCompletenessStateRepository(session).set_exception(
            game_id, seed.source_image_id, reason="Plansza 9 poza kadrem", actor="task-0807"
        )
    assert exception is not None
    assert exception.status is SourceImageGeometryStatus.GEOMETRY_EXCEPTION
    assert exception.materialized_review_item_count == 8
    excepted = _state(factory, game_id, seed.source_image_id)
    assert excepted["status"] == "geometry_exception"
    assert excepted["exception_reason"] == "Plansza 9 poza kadrem"
    assert excepted["cells"] == 120
    assert excepted["candidates_with_evidence"] == 8

    with game_storage_scope(game_id), factory.begin() as session:
        withdrawn = SqlAlchemyImageGeometryCompletenessStateRepository(session).withdraw_exception(
            game_id, seed.source_image_id, actor="task-0807"
        )
    assert withdrawn is not None
    assert withdrawn.status is SourceImageGeometryStatus.GEOMETRY_INCOMPLETE
    after = _state(factory, game_id, seed.source_image_id)
    assert after["status"] == "geometry_incomplete"
    assert after["exception_reason"] is None
    # Nothing is deleted: the cells cut under the exception stay.
    assert after["cells"] == 120

    # An exception is refused for an image that is not incomplete, and a
    # withdrawal is refused after a human symbol decision.
    with game_storage_scope(game_id), factory.begin() as session:
        repository = SqlAlchemyImageGeometryCompletenessStateRepository(session)
        repository.set_exception(game_id, seed.source_image_id, reason="again", actor="task-0807")
        cell = session.scalar(
            select(ImageSymbolReviewCellModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageSymbolReviewCellModel.recognized_board_id,
            )
            .where(RecognizedBoardModel.source_image_id == seed.source_image_id)
            .limit(1)
        )
        assert cell is not None
        cell.assignment_source = "human"
    with (
        game_storage_scope(game_id),
        factory.begin() as session,
        pytest.raises(ImageReviewConflictError) as refused,
    ):
        SqlAlchemyImageGeometryCompletenessStateRepository(session).withdraw_exception(
            game_id, seed.source_image_id, actor="task-0807"
        )
    assert refused.value.code == "IMAGE_GEOMETRY_EXCEPTION_HUMAN_DECISIONS_PRESENT"
    assert _state(factory, game_id, seed.source_image_id)["status"] == "geometry_exception"


def test_uncertain_boards_block_the_image_until_a_human_approves_the_geometry(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _seeded(database, tmp_path, "task0807-uncertain", 9)
    game_id = seed.game_id
    with game_storage_scope(game_id), factory.begin() as session:
        # The engine wrote the grids with reservations: every board is uncertain.
        session.execute(
            text(
                "UPDATE game_data_v2.image_source_geometry_revisions SET status = 'needs_review' "
                "WHERE game_id = :game_id AND source_image_id = :source_image_id"
            ),
            {"game_id": game_id, "source_image_id": seed.source_image_id},
        )
    _import(factory, seed, "task0807-uncertain", range(9))
    blocked = _state(factory, game_id, seed.source_image_id)
    assert blocked["status"] == "geometry_incomplete"
    assert (blocked["boards"], blocked["cells"], blocked["candidates_with_evidence"]) == (9, 0, 0)

    with game_storage_scope(game_id), factory() as session:
        item_id = session.scalar(
            select(ImageReviewItemModel.id)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .where(
                RecognizedBoardModel.source_image_id == seed.source_image_id,
                RecognizedBoardModel.position_index == 0,
            )
        )
    assert item_id is not None
    query = {"gameId": str(game_id), "importJobId": str(seed.import_job_id)}
    base = f"/api/v1/admin/image-review-items/{item_id}"
    app = _app(database, artifact_root)
    try:
        with TestClient(app) as client:
            item = client.get(base, params=query)
            assert item.status_code == 200, item.text
            saved = client.post(
                f"{base}/geometry-revisions",
                params=query,
                json={
                    "corners": _corners(),
                    "expectedGeometryRevision": item.json()["geometryRevision"],
                    "expectedResolutionRevision": item.json()["resolutionRevision"],
                    "idempotencyKey": str(uuid4()),
                    "correctedBy": "task-0807-operator",
                },
            )
    finally:
        app.state.database_engine.dispose()
    assert saved.status_code == 200, saved.text

    approved = _state(factory, game_id, seed.source_image_id)
    # The new manual revision repeats the other eight grids exactly, so they
    # were re-pointed to it (accepted); with the approved board the image is
    # complete and all nine boards were cut in the same request.
    assert approved["status"] == "geometry_complete"
    assert approved["cells"] == 135
    with game_storage_scope(game_id), factory() as session:
        newest = session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id)
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        assert newest is not None and newest.status == "accepted"
        boards = session.scalars(
            select(RecognizedBoardModel).where(
                RecognizedBoardModel.source_image_id == seed.source_image_id
            )
        ).all()
        assert {board.source_geometry_revision_id for board in boards} == {newest.id}
        assert {board.geometry_checksum_sha256 for board in boards} == {
            newest.geometry_checksum_sha256
        }
        stale_cells = session.scalar(
            select(func.count())
            .select_from(ImageSymbolReviewCellModel)
            .where(
                ImageSymbolReviewCellModel.recognized_board_id.in_([board.id for board in boards]),
                ImageSymbolReviewCellModel.source_geometry_revision_id != newest.id,
            )
        )
        assert stale_cells == 0


# -- backfill ------------------------------------------------------------------


def _add_image(
    session: Session,
    *,
    game_id: UUID,
    job_id: UUID,
    label: str,
    positions: Sequence[int],
    start: int,
    revision_status: str = "accepted",
    newer_revision: str | None = None,
) -> UUID:
    """One source image with boards on revision 0 (status NULL: before the gate).

    ``newer_revision`` appends an accepted revision 1: ``"identical"`` repeats
    every grid, ``"differs"`` changes the grid of position 4.
    """

    from _virtual_board_fixtures import (
        add_board_render_manifest_for,
        ensure_source_geometry,
        virtual_board_columns,
    )

    key = _sha(f"{label}-execution")
    source = SourceImageModel(
        import_job_id=job_id,
        file_execution_key=key,
        relative_path=f"originals/{label}.jpg",
        checksum_sha256=_sha(f"{label}-checksum"),
        width=1920,
        height=1080,
        status="waiting_for_review",
    )
    session.add(source)
    session.flush()
    revision = ensure_source_geometry(
        session,
        game_id=game_id,
        source=source,
        sequence_range_start=start,
        created_at=datetime.now(UTC),
        quad=_QUAD,
    )
    revision.status = revision_status
    for position in positions:
        board = RecognizedBoardModel(
            source_image_id=source.id,
            position_index=position,
            sequence_number_raw=str(start + position),
            sequence_number=start + position,
            sequence_confidence=1.0,
            board_geometry={"quad": _QUAD},
            cells_prediction={
                "cells": [
                    {
                        "alternatives": [{"confidence": 1.0, "symbolCode": "CYTRYNA"}],
                        "columnIndex": index % 5,
                        "confidence": 1.0,
                        "rowIndex": index // 5,
                        "symbolCode": "CYTRYNA",
                    }
                    for index in range(15)
                ]
            },
            board_confidence=1.0,
            pipeline_fingerprint=_PIPELINE,
            status="pending_review",
            **virtual_board_columns(revision),
        )
        session.add(board)
        session.flush()
        item = ImageReviewItemModel(
            game_id=game_id,
            import_job_id=job_id,
            sequence_number=start + position,
            recognized_board_id=board.id,
            status="pending",
            snapshot={"sequenceNumber": start + position},
            resolution_revision=0,
        )
        session.add(item)
        session.flush()
        add_board_render_manifest_for(session, game_id=game_id, board=board)
    if newer_revision is not None:
        entries = [dict(entry) for entry in revision.board_geometries]
        if newer_revision == "differs":
            entries[4] = {**entries[4], "finalQuad": [{"x": 61.0, "y": 50.0}, *_QUAD[1:]]}
        session.add(
            ImageSourceGeometryRevisionModel(
                game_id=game_id,
                source_image_id=source.id,
                topology_rules_version_id=revision.topology_rules_version_id,
                revision=1,
                sequence_range_start=revision.sequence_range_start,
                sequence_range_end=revision.sequence_range_end,
                active_board_slots=list(revision.active_board_slots),
                coordinate_space=revision.coordinate_space,
                source_checksum_sha256=revision.source_checksum_sha256,
                normalized_pixel_checksum_sha256=revision.normalized_pixel_checksum_sha256,
                oriented_width=revision.oriented_width,
                oriented_height=revision.oriented_height,
                normalization_adapter_version=revision.normalization_adapter_version,
                global_initialization={},
                board_geometries=entries,
                engine_kind="manual_v1",
                engine_version="manual-source-geometry-v1",
                geometry_source="manual",
                status="accepted",
                geometry_checksum_sha256=_sha(f"{label}-revision-1"),
                processing_time_ms=1,
                warnings=[],
                created_by="system:legacy-board-conversion-v1",
            )
        )
    session.flush()
    return source.id


def _backfill_world(factory: sessionmaker[Session], game_id: UUID) -> dict[str, UUID]:
    with game_storage_scope(game_id), factory.begin() as session:
        job = JobModel(
            game_id=game_id,
            job_type="import",
            status="waiting_for_review",
            input_payload={"import_kind": "image_directory", "pipeline_fingerprint": _PIPELINE},
            input_key=uuid4().hex,
        )
        session.add(job)
        session.flush()
        from game_predictor_api.storage.models import (
            ImageFileExecutionModel,
            ImageImportJobFileModel,
        )

        images = {
            "complete": dict(positions=range(9), start=1000),
            "incomplete": dict(positions=(0, 1), start=1100),
            "repoint": dict(
                positions=range(9),
                start=1200,
                revision_status="needs_review",
                newer_revision="identical",
            ),
            "differs": dict(
                positions=range(9),
                start=1300,
                revision_status="needs_review",
                newer_revision="differs",
            ),
        }
        ids: dict[str, UUID] = {}
        for label, spec in [*images.items(), ("empty", None)]:
            key = _sha(f"backfill-{label}-execution")
            session.add(
                ImageFileExecutionModel(
                    file_execution_key=key,
                    source_checksum_sha256=_sha(f"backfill-{label}-checksum"),
                    pipeline_fingerprint=_PIPELINE,
                    checkpoint_payload={},
                    status="waiting_for_review",
                    review_required=True,
                )
            )
            session.flush()
            session.add(
                ImageImportJobFileModel(
                    job_id=job.id,
                    file_execution_key=key,
                    order_index=len(ids),
                    source_relative_path=f"originals/backfill-{label}.jpg",
                    workflow_checkpoint_payload={},
                    workflow_status="waiting_for_review",
                    review_required=True,
                )
            )
            session.flush()
            if spec is None:
                source = SourceImageModel(
                    import_job_id=job.id,
                    file_execution_key=key,
                    relative_path="originals/backfill-empty.jpg",
                    checksum_sha256=_sha("backfill-empty-checksum"),
                    width=1920,
                    height=1080,
                    status="processing",
                )
                session.add(source)
                session.flush()
                ids[label] = source.id
                continue
            ids[label] = _add_image(
                session, game_id=game_id, job_id=job.id, label=f"backfill-{label}", **spec
            )
    # Cut every board while the images are not evaluated (behaviour before the gate).
    with game_storage_scope(game_id), factory.begin() as session:
        coordinator = SymbolCellReviewWriteThroughCoordinator(session)
        for item_id in session.scalars(
            select(ImageReviewItemModel.id).order_by(ImageReviewItemModel.id)
        ).all():
            coordinator.synchronize_after_prediction_refresh(
                game_id=game_id, review_item_id=item_id, actor="task-0807"
            )
        # One human approval on a board that will be re-pointed.
        approved = session.scalar(
            select(ImageSymbolReviewCellModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageSymbolReviewCellModel.recognized_board_id,
            )
            .where(RecognizedBoardModel.source_image_id == ids["repoint"])
            .limit(1)
        )
        assert approved is not None
        approved.approved_crop_sample_id = approved.crop_sample_id
        approved.approved_crop_checksum_sha256 = approved.crop_checksum_sha256
        approved.approved_geometry_revision = approved.geometry_revision
        approved.approved_asset_mode = "virtual_source"
        approved.approved_source_geometry_revision_id = approved.source_geometry_revision_id
        approved.approved_render_spec_checksum_sha256 = approved.render_spec_checksum_sha256
        approved.approved_rendered_pixel_checksum_sha256 = approved.rendered_pixel_checksum_sha256
    return ids


def _row_counts(factory: sessionmaker[Session], game_id: UUID) -> dict[str, int]:
    with game_storage_scope(game_id), factory() as session:
        return {
            table: int(
                session.execute(
                    text(f"SELECT count(*) FROM game_data_v2.{table} WHERE game_id = :game_id"),
                    {"game_id": game_id},
                ).scalar_one()
            )
            for table in (
                "source_images",
                "recognized_boards",
                "image_review_items",
                "image_symbol_review_cells",
                "board_render_manifests",
                "image_source_geometry_revisions",
                "image_board_search_candidates",
            )
        }


def test_backfill_preview_writes_nothing_and_apply_resumes_without_double_counting(
    database: _Database,  # noqa: F811
) -> None:
    game_id = _provision_game(database.engine, "task0807-backfill")
    factory = _factory(database.engine)
    _add_symbols(factory, game_id)
    ids = _backfill_world(factory, game_id)
    before = _row_counts(factory, game_id)
    assert before["image_symbol_review_cells"] == 15 * (9 + 2 + 9 + 9)

    with game_storage_scope(game_id), factory() as session:
        session.connection().execute(text("SET TRANSACTION READ ONLY"))
        preview = SourceImageGeometryCompletenessBackfill(session).next_batch(
            game_id, after_source_image_id=None, apply=False
        )
        session.rollback()
    assert preview.processed_image_count == 5
    assert preview.has_more is False
    assert dict(preview.status_counts) == {
        "geometry_complete": 2,
        "geometry_incomplete": 2,
        "null": 1,
    }
    assert preview.incomplete_with_cells_count == 2
    assert preview.repointed_board_count == 9 + 8
    [kept] = preview.not_repointable
    assert kept.source_image_id == ids["differs"]
    assert kept.position_index == 4
    assert kept.reason_code == REPOINT_GEOMETRY_ENTRY_DIFFERS
    assert _row_counts(factory, game_id) == before
    with game_storage_scope(game_id), factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceImageModel)
                .where(SourceImageModel.geometry_completeness_evaluated_at.is_not(None))
            )
            == 0
        )

    # Apply in two runs; the second starts over and skips what is evaluated.
    totals: dict[str, int] = {}
    with game_storage_scope(game_id), factory.begin() as session:
        first = SourceImageGeometryCompletenessBackfill(session).next_batch(
            game_id, after_source_image_id=None, limit=2, apply=True
        )
    assert first.processed_image_count == 2 and first.has_more
    for key, value in first.status_counts.items():
        totals[key] = totals.get(key, 0) + value
    with game_storage_scope(game_id), factory.begin() as session:
        second = SourceImageGeometryCompletenessBackfill(session).next_batch(
            game_id, after_source_image_id=None, apply=True
        )
    assert second.processed_image_count == 3 and not second.has_more
    for key, value in second.status_counts.items():
        totals[key] = totals.get(key, 0) + value
    assert totals == dict(preview.status_counts)
    assert first.repointed_board_count + second.repointed_board_count == 17
    with game_storage_scope(game_id), factory.begin() as session:
        third = SourceImageGeometryCompletenessBackfill(session).next_batch(
            game_id, after_source_image_id=None, apply=True
        )
    assert third.processed_image_count == 0

    assert _row_counts(factory, game_id) == before
    states = {label: _state(factory, game_id, image_id) for label, image_id in ids.items()}
    assert states["complete"]["status"] == "geometry_complete"
    assert states["incomplete"]["status"] == "geometry_incomplete"
    assert states["incomplete"]["cells"] == 30
    assert states["repoint"]["status"] == "geometry_complete"
    assert states["differs"]["status"] == "geometry_incomplete"
    assert states["empty"]["status"] is None and states["empty"]["evaluated"] is True
    with game_storage_scope(game_id), factory() as session:
        summary = SourceImageGeometryCompletenessBackfill(session).summary(game_id)
        session.rollback()
    assert summary.not_evaluated_count == 0
    assert summary.incomplete_with_cells_count == 2
    assert dict(summary.status_counts) == dict(preview.status_counts)

    with game_storage_scope(game_id), factory() as session:
        revisions = {
            revision.revision: revision
            for revision in session.scalars(
                select(ImageSourceGeometryRevisionModel).where(
                    ImageSourceGeometryRevisionModel.source_image_id == ids["repoint"]
                )
            )
        }
        boards = session.scalars(
            select(RecognizedBoardModel).where(
                RecognizedBoardModel.source_image_id.in_((ids["repoint"], ids["differs"]))
            )
        ).all()
        moved = [board for board in boards if board.source_image_id == ids["repoint"]]
        assert {board.source_geometry_revision_id for board in moved} == {revisions[1].id}
        assert {board.geometry_checksum_sha256 for board in moved} == {
            revisions[1].geometry_checksum_sha256
        }
        kept_board = next(
            board
            for board in boards
            if board.source_image_id == ids["differs"] and board.position_index == 4
        )
        assert kept_board.geometry_checksum_sha256 != revisions[1].geometry_checksum_sha256
        moved_ids = [board.id for board in moved]
        manifests = session.scalars(
            select(BoardRenderManifestModel.source_geometry_revision_id).where(
                BoardRenderManifestModel.recognized_board_id.in_(moved_ids)
            )
        ).all()
        assert set(manifests) == {revisions[1].id}
        cells = session.scalars(
            select(ImageSymbolReviewCellModel).where(
                ImageSymbolReviewCellModel.recognized_board_id.in_(moved_ids)
            )
        ).all()
        assert len(cells) == 135
        assert {cell.source_geometry_revision_id for cell in cells} == {revisions[1].id}
        [approved] = [cell for cell in cells if cell.approved_crop_sample_id is not None]
        assert approved.approved_source_geometry_revision_id == revisions[1].id
        assert approved.approved_crop_sample_id == approved.crop_sample_id

    # An incomplete image keeps its historical cells: a write-through keeps
    # maintaining them and never deletes them.
    with game_storage_scope(game_id), factory.begin() as session:
        coordinator = SymbolCellReviewWriteThroughCoordinator(session)
        for item_id in session.scalars(
            select(ImageReviewItemModel.id)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .where(RecognizedBoardModel.source_image_id == ids["incomplete"])
        ).all():
            coordinator.synchronize_after_prediction_refresh(
                game_id=game_id, review_item_id=item_id, actor="task-0807"
            )
        assert not coordinator.geometry_withheld_review_item_ids
    assert _state(factory, game_id, ids["incomplete"])["cells"] == 30

    # Another game neither sees nor reaches this game's state.
    other_game = _provision_game(database.engine, "task0807-other")
    report, _page = _report(factory, other_game, None)
    assert report is not None and report.gate is not None
    assert report.images.total == 0
    assert (report.gate.geometry_complete, report.gate.geometry_incomplete) == (0, 0)
    with (
        game_storage_scope(other_game),
        factory.begin() as session,
        pytest.raises(ImageReviewNotFoundError),
    ):
        recompute_source_image_geometry_completeness(session, other_game, ids["complete"])


def test_migration_0139_downgrade_refuses_an_exception_and_restores_the_columns(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    from alembic import command

    factory, seed, _artifact_root = _seeded(database, tmp_path, "task0807-migration", 2)
    game_id = seed.game_id
    with game_storage_scope(game_id), factory.begin() as session:
        SqlAlchemyImageGeometryCompletenessStateRepository(session).set_exception(
            game_id, seed.source_image_id, reason="both slots deferred", actor="task-0807"
        )

    def columns() -> set[str]:
        with database.engine.connect() as connection:
            return {
                str(row[0])
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'game_data_v2' AND table_name = 'source_images' "
                        "AND column_name LIKE 'geometry_%'"
                    )
                )
            }

    assert len(columns()) == 5
    # An operator exception is a human decision a recompute cannot recreate.
    with pytest.raises(Exception, match="SOURCE_IMAGE_GEOMETRY_EXCEPTION_PRESENT"):
        command.downgrade(database.config, "0138_rls_policy_function_parallel_safe")
    assert len(columns()) == 5

    with game_storage_scope(game_id), factory.begin() as session:
        SqlAlchemyImageGeometryCompletenessStateRepository(session).withdraw_exception(
            game_id, seed.source_image_id, actor="task-0807"
        )
    command.downgrade(database.config, "0138_rls_policy_function_parallel_safe")
    assert columns() == set()
    command.upgrade(database.config, "head")
    assert len(columns()) == 5
    with database.engine.connect() as connection:
        statuses = connection.execute(
            text(
                "SELECT count(*) FILTER (WHERE geometry_completeness_status IS NULL), count(*) "
                "FROM game_data_v2.source_images WHERE game_id = :game_id"
            ),
            {"game_id": game_id},
        ).one()
        indexes = connection.execute(
            text(
                "SELECT count(*) FROM pg_indexes WHERE schemaname = 'game_data_v2' "
                "AND indexname IN ('ix_source_images_geometry_completeness_queue', "
                "'ix_source_images_geometry_completeness_unevaluated')"
            )
        ).scalar_one()
    # After a round trip every image is not evaluated again (the backfill restores it).
    assert statuses == (1, 1)
    assert indexes == 2
