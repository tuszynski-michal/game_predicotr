"""TASK-0796: the Reviewer's board geometry correction writes a virtual revision.

D-467 S6 removed the v19 file-crop correction.  The operational Reviewer
routes ``image-review-items/{id}/geometry-preview`` and ``.../geometry-revisions``
keep their contract and delegate to ``VirtualGridGeometryService``.  Runs on a
dedicated ``*_test`` database through the real application wiring: the board
is first created by resolving a deferred slot (TASK-0790), then corrected
through the operational endpoints.

TASK-0798 adds the partial qualification of the operational editor and the
refusal of a decision that moves a virtual board to another sequence number.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.main import create_app
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.models import (
    BoardRenderManifestModel,
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    ImageReviewResolutionEventModel,
    ImageSequenceCanonicalModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewStateModel,
    RecognizedBoardModel,
)
from sqlalchemy import func, select
from test_virtual_deferred_resolution_postgres import (
    _PARTIAL_CORNERS,
    _PARTIAL_MASK,
    _Database,
    _factory,
    _provision_game,
    _resolve_via_reviewer_endpoint,
    _seed,
    database,  # noqa: F401  (pytest fixture)
    pytestmark,  # noqa: F401  (PostgreSQL opt-in)
)

_SHIFTED_CORNERS = [
    {"x": 64, "y": 54},
    {"x": 556, "y": 52},
    {"x": 558, "y": 346},
    {"x": 62, "y": 348},
]


def _app(db: _Database, artifact_root: Path) -> Any:
    return create_app(
        ApiSettings.from_environment(
            {
                "GAME_PREDICTOR_DATABASE_URL": db.url,
                "GAME_PREDICTOR_ARTIFACT_ROOT": str(artifact_root),
            }
        )
    )


def _add_symbols(factory: Any, game_id: UUID) -> None:
    """The symbols of the seeded import's pinned model; cells need active symbols."""

    with factory() as session:
        catalog = CatalogService(SqlAlchemyCatalogRepository(session))
        for order, code in enumerate(("CYTRYNA", "WISNIA"), start=1):
            catalog.create_symbol(
                game_id,
                mobile_code=order,
                code=code,
                name=code.title(),
                image_path=None,
                is_wildcard=False,
                display_order=order,
                status=SymbolStatus.ACTIVE,
            )
        session.commit()


def test_operational_geometry_correction_writes_a_virtual_revision_with_manifest(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0796-reviewer-geometry")
    factory = _factory(database.engine)
    seed = _seed(factory, game_id, artifact_root, label="operational-source", slot_count=1)
    _add_symbols(factory, game_id)
    resolution = _resolve_via_reviewer_endpoint(database, artifact_root, seed)
    review_item_id = UUID(str(resolution["reviewItemId"]))
    query = {"gameId": str(game_id), "importJobId": str(seed.import_job_id)}
    base = f"/api/v1/admin/image-review-items/{review_item_id}"
    files_before = sorted(path for path in artifact_root.rglob("*") if path.is_file())

    app = _app(database, artifact_root)
    try:
        with TestClient(app) as client:
            loaded = client.get(base, params=query)
            assert loaded.status_code == 200, loaded.text
            item = loaded.json()
            assert item["geometryRevision"] == 1
            command = {
                "corners": _SHIFTED_CORNERS,
                "expectedGeometryRevision": item["geometryRevision"],
                "expectedResolutionRevision": item["resolutionRevision"],
            }
            preview = client.post(f"{base}/geometry-preview", params=query, json=command)
            key = str(uuid4())
            saved = client.post(
                f"{base}/geometry-revisions",
                params=query,
                json={**command, "idempotencyKey": key, "correctedBy": "task-0796-operator"},
            )
            replay = client.post(
                f"{base}/geometry-revisions",
                params=query,
                json={**command, "idempotencyKey": key, "correctedBy": "task-0796-operator"},
            )
            other_command = client.post(
                f"{base}/geometry-revisions",
                params=query,
                json={
                    **command,
                    "corners": [{"x": 65, "y": 54}, *_SHIFTED_CORNERS[1:]],
                    "idempotencyKey": key,
                    "correctedBy": "task-0796-operator",
                },
            )
            stale = client.post(
                f"{base}/geometry-revisions",
                params=query,
                json={**command, "idempotencyKey": str(uuid4()), "correctedBy": "late"},
            )
    finally:
        app.state.database_engine.dispose()

    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"] == "image/png"
    assert preview.headers["x-board-cell-count"] == "15"
    assert preview.headers["x-board-cell-preview-kind"] == "contact-sheet-5x3"
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["created"] is True
    assert body["item"]["id"] == str(review_item_id)
    assert body["item"]["geometryRevision"] == 2
    assert body["item"]["status"] == "pending"
    revision_body = body["geometryRevision"]
    assert revision_body["revision"] == 2
    assert revision_body["correctedBy"] == "task-0796-operator"
    assert len(revision_body["cells"]) == 15
    assert "boardChecksumSha256" not in revision_body
    assert "decisionChecksumSha256" not in revision_body
    assert replay.status_code == 200, replay.text
    assert replay.json()["created"] is False
    assert replay.json()["geometryRevision"]["id"] == revision_body["id"]
    assert other_command.status_code == 409
    assert other_command.json()["code"] == "IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT"
    assert stale.status_code == 409
    assert stale.json()["code"] == "IMAGE_GRID_REVIEW_REVISION_CONFLICT"

    with game_storage_scope(game_id), factory() as session:
        board = session.scalar(
            select(RecognizedBoardModel)
            .join(
                ImageReviewItemModel,
                ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
            )
            .where(ImageReviewItemModel.id == review_item_id)
        )
        assert board is not None
        record = session.scalar(
            select(ImageBoardGeometryRevisionModel).where(
                ImageBoardGeometryRevisionModel.recognized_board_id == board.id,
                ImageBoardGeometryRevisionModel.revision == 2,
            )
        )
        manifest = session.get(BoardRenderManifestModel, (game_id, board.id, 2))
        cells = session.scalars(
            select(ImageSymbolReviewCellModel)
            .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
            .order_by(ImageSymbolReviewCellModel.cell_index)
        ).all()
        source_revisions = session.scalars(
            select(ImageSourceGeometryRevisionModel.revision)
            .where(ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id)
            .order_by(ImageSourceGeometryRevisionModel.revision)
        ).all()

    assert board.asset_mode == "virtual_source"
    assert board.geometry_revision == 2
    assert board.board_relative_path is None and board.board_checksum_sha256 is None
    assert record is not None
    assert str(record.id) == revision_body["id"]
    assert record.asset_mode == "virtual_source"
    assert record.crop_artifacts is None and record.board_relative_path is None
    assert (
        record.virtual_render_spec_checksum_sha256
        == (revision_body["virtualRenderSpecChecksumSha256"])
    )
    assert manifest is not None
    render_cells = cast(list[dict[str, Any]], record.virtual_render_spec["cells"])
    manifest_cells = cast(dict[str, Any], manifest.cells)["cells"]
    assert [(cell["cellIndex"], cell["renderSpecChecksumSha256"]) for cell in manifest_cells] == [
        (cell["cellIndex"], cell["renderSpecChecksumSha256"]) for cell in render_cells
    ]
    assert [cell.cell_index for cell in cells] == list(range(15))
    assert {cell.asset_mode for cell in cells} == {"virtual_source"}
    assert {cell.geometry_revision for cell in cells} == {2}
    assert all(cell.crop_relative_path is None for cell in cells)
    assert [cell.crop_sample_id for cell in cells] == [
        cell["cropSampleId"] for cell in revision_body["cells"]
    ]
    # The resolution appended revision 1, the operational correction revision 2.
    assert source_revisions == [0, 1, 2]
    # Rendering is metadata-only: no crop file is written.
    assert sorted(path for path in artifact_root.rglob("*") if path.is_file()) == files_before


def test_operational_geometry_correction_refuses_a_superseded_board(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0796-superseded")
    factory = _factory(database.engine)
    seed = _seed(factory, game_id, artifact_root, label="superseded-source", slot_count=1)
    _add_symbols(factory, game_id)
    resolution = _resolve_via_reviewer_endpoint(database, artifact_root, seed)
    review_item_id = UUID(str(resolution["reviewItemId"]))
    with game_storage_scope(game_id), factory.begin() as session:
        item = session.get(ImageReviewItemModel, review_item_id)
        assert item is not None
        item.status = "superseded"
        item.resolved_value = {
            "action": "superseded",
            "canonicalReviewItemId": str(uuid4()),
            "reason": "test",
            "sequenceNumber": 100,
        }
        item.resolved_by = "system:test-superseded"
        item.resolved_at = item.created_at
        item.resolution_revision += 1
        resolution_revision = item.resolution_revision
    query = {"gameId": str(game_id), "importJobId": str(seed.import_job_id)}
    app = _app(database, artifact_root)
    try:
        with TestClient(app) as client:
            refused = client.post(
                f"/api/v1/admin/image-review-items/{review_item_id}/geometry-revisions",
                params=query,
                json={
                    "corners": _SHIFTED_CORNERS,
                    "expectedGeometryRevision": 1,
                    "expectedResolutionRevision": resolution_revision,
                    "idempotencyKey": str(uuid4()),
                    "correctedBy": "task-0796-operator",
                },
            )
    finally:
        app.state.database_engine.dispose()

    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "IMAGE_REVIEW_SUPERSEDED"
    with game_storage_scope(game_id), factory() as session:
        board = session.scalar(
            select(RecognizedBoardModel)
            .join(
                ImageReviewItemModel,
                ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
            )
            .where(ImageReviewItemModel.id == review_item_id)
        )
        assert board is not None and board.geometry_revision == 1


def _resolution_command(item: dict[str, Any], *, sequence_number: int) -> dict[str, Any]:
    return {
        "idempotencyKey": str(uuid4()),
        "expectedRevision": item["resolutionRevision"],
        "action": "corrected",
        "sequenceNumber": sequence_number,
        "geometryRevision": item["geometryRevision"],
        "cells": [
            {
                "cellIndex": cell["cellIndex"],
                "cropSampleId": cell["cropSampleId"],
                "symbolCode": "CYTRYNA",
            }
            for cell in item["cells"]
        ],
        "resolvedBy": "task-0798-operator",
    }


def _resolution_event_revisions(factory: Any, game_id: UUID, review_item_id: UUID) -> list[int]:
    with game_storage_scope(game_id), factory() as session:
        return list(
            session.scalars(
                select(ImageReviewResolutionEventModel.revision)
                .where(ImageReviewResolutionEventModel.review_item_id == review_item_id)
                .order_by(ImageReviewResolutionEventModel.revision)
            )
        )


def test_corrected_resolution_cannot_move_a_virtual_board_to_another_sequence(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """TASK-0798: the number is pinned by the source geometry slot.

    Before the fix the symbol-cell write-through raised ``ValueError`` (pinned
    slot does not own the sequence) after the canonical claim, and the API
    answered 500.  The decision is now refused with 409 before any write.
    """

    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0798-corrected-sequence")
    factory = _factory(database.engine)
    seed = _seed(factory, game_id, artifact_root, label="sequence-source", slot_count=1)
    _add_symbols(factory, game_id)
    resolution = _resolve_via_reviewer_endpoint(database, artifact_root, seed)
    review_item_id = UUID(str(resolution["reviewItemId"]))
    query = {"gameId": str(game_id), "importJobId": str(seed.import_job_id)}
    base = f"/api/v1/admin/image-review-items/{review_item_id}"
    events_before = _resolution_event_revisions(factory, game_id, review_item_id)
    app = _app(database, artifact_root)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            item = client.get(base, params=query).json()
            attested = item["suggestedSequenceNumber"]
            moved = client.post(
                f"{base}/resolution",
                params=query,
                json=_resolution_command(item, sequence_number=attested + 7),
            )
            after_refusal = client.get(base, params=query).json()
            kept = client.post(
                f"{base}/resolution",
                params=query,
                json=_resolution_command(item, sequence_number=attested),
            )
    finally:
        app.state.database_engine.dispose()

    assert item["status"] == "pending"
    assert moved.status_code == 409, moved.text
    body = moved.json()
    assert body["code"] == "IMAGE_REVIEW_SEQUENCE_PINNED_BY_SOURCE"
    assert body["details"] == {
        "boardSequenceNumber": attested,
        "requestedSequenceNumber": attested + 7,
    }
    # Full rollback: the item, its events and the canonical claim are unchanged.
    assert after_refusal["status"] == "pending"
    assert after_refusal["resolutionRevision"] == item["resolutionRevision"]
    with game_storage_scope(game_id), factory() as session:
        claims = session.scalars(
            select(ImageSequenceCanonicalModel.sequence_number).where(
                ImageSequenceCanonicalModel.game_id == game_id
            )
        ).all()
        moved_cells = session.scalar(
            select(func.count())
            .select_from(ImageSymbolReviewCellModel)
            .where(
                ImageSymbolReviewCellModel.game_id == game_id,
                ImageSymbolReviewCellModel.sequence_number == attested + 7,
            )
        )
    assert attested + 7 not in claims
    assert moved_cells == 0
    # The same command at the attested number is the ordinary correction.
    assert kept.status_code == 200, kept.text
    assert kept.json()["item"]["status"] == "corrected"
    assert kept.json()["item"]["sequenceNumber"] == attested
    assert _resolution_event_revisions(factory, game_id, review_item_id) == [
        *events_before,
        kept.json()["event"]["revision"],
    ]


_PARTIAL_QUALIFICATION = {
    "completenessStatus": "pending_partial",
    "excludeFromGeometryTraining": True,
    "exclusionReason": "missing_pixels",
    "unavailableCellIndices": list(_PARTIAL_MASK),
    "version": "manual-geometry-qualification-v1",
}


def _finalize_cell_count(factory: Any, game_id: UUID) -> None:
    """Emulate a finished symbol-cell backfill of the fixture game.

    The write-through creates the state as ``rebuilding`` with ``cell_count``
    0 and only the backfill finalization recounts it; a geometry revision then
    applies an availability delta to that count (production games are
    finalized).
    """

    with game_storage_scope(game_id), factory.begin() as session:
        state = session.get(ImageSymbolReviewStateModel, game_id)
        assert state is not None
        state.cell_count = session.scalar(
            select(func.count())
            .select_from(ImageSymbolReviewCellModel)
            .where(
                ImageSymbolReviewCellModel.game_id == game_id,
                ImageSymbolReviewCellModel.source_available.is_(True),
            )
        )


def test_operational_geometry_correction_saves_a_partial_qualification(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """TASK-0798: the operational editor corrects a board into a partial one."""

    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0798-partial")
    factory = _factory(database.engine)
    seed = _seed(factory, game_id, artifact_root, label="partial-source", slot_count=1)
    _add_symbols(factory, game_id)
    resolution = _resolve_via_reviewer_endpoint(database, artifact_root, seed)
    review_item_id = UUID(str(resolution["reviewItemId"]))
    _finalize_cell_count(factory, game_id)
    query = {"gameId": str(game_id), "importJobId": str(seed.import_job_id)}
    base = f"/api/v1/admin/image-review-items/{review_item_id}"
    app = _app(database, artifact_root)
    try:
        with TestClient(app) as client:
            item = client.get(base, params=query).json()
            command = {
                "corners": _PARTIAL_CORNERS,
                "expectedGeometryRevision": item["geometryRevision"],
                "expectedResolutionRevision": item["resolutionRevision"],
                "geometryQualification": _PARTIAL_QUALIFICATION,
            }
            unqualified = client.post(
                f"{base}/geometry-preview",
                params=query,
                json={
                    key: value for key, value in command.items() if key != "geometryQualification"
                },
            )
            preview = client.post(f"{base}/geometry-preview", params=query, json=command)
            saved = client.post(
                f"{base}/geometry-revisions",
                params=query,
                json={**command, "idempotencyKey": str(uuid4()), "correctedBy": "task-0798"},
            )
            reloaded = client.get(base, params=query).json()
            complete_again = client.post(
                f"{base}/geometry-revisions",
                params=query,
                json={
                    "corners": _SHIFTED_CORNERS,
                    "expectedGeometryRevision": reloaded["geometryRevision"],
                    "expectedResolutionRevision": reloaded["resolutionRevision"],
                    "idempotencyKey": str(uuid4()),
                    "correctedBy": "task-0798",
                },
            )
    finally:
        app.state.database_engine.dispose()

    assert item["geometryQualification"] is None
    assert (item["sourceWidth"], item["sourceHeight"]) == (620, 420)
    # Signed corners without a partial declaration are a validation error.
    assert unqualified.status_code == 422, unqualified.text
    assert preview.status_code == 200, preview.text
    assert preview.headers["x-board-cell-count"] == str(15 - len(_PARTIAL_MASK))
    assert saved.status_code == 200, saved.text
    revision_body = saved.json()["geometryRevision"]
    assert revision_body["revision"] == 2
    assert revision_body["corners"] == _PARTIAL_CORNERS
    assert revision_body["geometryQualification"]["completenessStatus"] == "pending_partial"
    assert revision_body["geometryQualification"]["unavailableCellIndices"] == list(_PARTIAL_MASK)
    assert [cell["cellIndex"] for cell in revision_body["cells"]] == [
        index for index in range(15) if index not in _PARTIAL_MASK
    ]
    assert reloaded["geometryRevision"] == 2
    assert reloaded["geometryQualification"]["completenessStatus"] == "pending_partial"
    # A partial board keeps its qualification: an unqualified command is refused.
    assert complete_again.status_code == 422, complete_again.text
    assert complete_again.json()["code"] == "IMAGE_GRID_REVIEW_QUALIFICATION_REQUIRED"

    with game_storage_scope(game_id), factory() as session:
        board = session.scalar(
            select(RecognizedBoardModel)
            .join(
                ImageReviewItemModel,
                ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
            )
            .where(ImageReviewItemModel.id == review_item_id)
        )
        assert board is not None
        record = session.scalar(
            select(ImageBoardGeometryRevisionModel).where(
                ImageBoardGeometryRevisionModel.recognized_board_id == board.id,
                ImageBoardGeometryRevisionModel.revision == 2,
            )
        )
        manifest = session.get(BoardRenderManifestModel, (game_id, board.id, 2))
        cells = session.scalars(
            select(ImageSymbolReviewCellModel)
            .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
            .order_by(ImageSymbolReviewCellModel.cell_index)
        ).all()

    assert board.asset_mode == "virtual_source"
    assert board.geometry_revision == 2
    assert board.completeness_status == "pending_partial"
    assert list(board.unavailable_cell_indices) == list(_PARTIAL_MASK)
    assert board.geometry_qualification is not None
    assert board.geometry_qualification["completenessStatus"] == "pending_partial"
    assert record is not None and record.asset_mode == "virtual_source"
    assert manifest is not None
    assert [cell["cellIndex"] for cell in cast(dict[str, Any], manifest.cells)["cells"]] == [
        index for index in range(15) if index not in _PARTIAL_MASK
    ]
    # Every logical position stays; the missing ones have no render.
    assert [cell.cell_index for cell in cells] == list(range(15))
    assert {cell.cell_index for cell in cells if cell.crop_sample_id is None} == set(_PARTIAL_MASK)
