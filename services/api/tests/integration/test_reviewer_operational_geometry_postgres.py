"""TASK-0796: the Reviewer's board geometry correction writes a virtual revision.

D-467 S6 removed the v19 file-crop correction.  The operational Reviewer
routes ``image-review-items/{id}/geometry-preview`` and ``.../geometry-revisions``
keep their contract and delegate to ``VirtualGridGeometryService``.  Runs on a
dedicated ``*_test`` database through the real application wiring: the board
is first created by resolving a deferred slot (TASK-0790), then corrected
through the operational endpoints.
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
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    RecognizedBoardModel,
)
from sqlalchemy import select
from test_virtual_deferred_resolution_postgres import (
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
