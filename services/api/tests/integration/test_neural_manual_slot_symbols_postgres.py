"""A real manual neural crop save must not depend on sibling slot review."""

from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
    SourceImageModel,
    SymbolModel,
)
from sqlalchemy import func, select
from test_reviewer_operational_geometry_postgres import _add_symbols, _app
from test_virtual_deferred_resolution_postgres import (
    _PARTIAL_CORNERS,
    _PARTIAL_MASK,
    _corners,
    _Database,
    _factory,
    _provision_game,
    _seed,
    database,  # noqa: F401
    pytestmark,  # noqa: F401
)


def test_manual_neural_slot_approves_only_selected_current_crop_and_replays_cold(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0885-neural-save")
    factory = _factory(database.engine)
    seed = _seed(factory, game_id, root, label="neural-save", slot_count=2, sequence_base=1405)
    _add_symbols(factory, game_id)
    nodes = [
        {"x": float(60 + column * 100), "y": float(50 + row * 100)}
        for row in range(4)
        for column in range(6)
    ]
    # The slot binding retains the neural proposal checksum. Interior nodes
    # intentionally differ from the interpolated outline.
    nodes[8]["x"] += 7.25
    proposal = "a" * 64
    with game_storage_scope(game_id), factory.begin() as session:
        revision = session.scalar(
            select(ImageSourceGeometryRevisionModel).where(
                ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id
            )
        )
        assert revision is not None
        entries = [dict(entry) for entry in revision.board_geometries]
        entries[0].update(latticeNodes=nodes, neuralProposalChecksumSha256=proposal)
        revision.board_geometries = entries
        symbol = session.scalar(
            select(SymbolModel.id).where(
                SymbolModel.game_id == game_id, SymbolModel.code == "WISNIA"
            )
        )
        assert symbol is not None
    base = (
        f"/api/v1/admin/games/{game_id}/image-imports/{seed.import_job_id}/"
        f"board-cell-geometry-pending/{seed.pending_ids[0]}"
    )
    command = {
        "corners": _corners(),
        "latticeNodes": nodes,
        "expectedProposalChecksumSha256": proposal,
        "expectedGeometryRevision": 0,
        "expectedResolutionRevision": 0,
        "expectedManifestChecksumSha256": seed.manifest_checksums[0],
        "geometryQualification": None,
        "correctedBy": "reviewer-operator",
        "idempotencyKey": str(uuid4()),
        "cellSymbols": [{"cellIndex": 3, "symbolId": str(symbol)}],
    }
    app = _app(database, root)
    try:
        with TestClient(app) as client:
            preview = client.post(
                f"{base}/geometry-preview",
                json={
                    key: value
                    for key, value in command.items()
                    if key not in {"correctedBy", "idempotencyKey", "cellSymbols"}
                },
            )
            assert preview.status_code == 200, preview.text
            assert preview.headers["x-board-cell-count"] == "15"
            saved = client.post(f"{base}/manual-resolution", json=command)
            assert saved.status_code == 200, saved.text
    finally:
        app.state.database_engine.dispose()

    def snapshot():
        with game_storage_scope(game_id), factory() as session:
            cells = session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.game_id == game_id)
                .order_by(ImageSymbolReviewCellModel.cell_index)
            ).all()
            assert len(cells) == 15
            selected = cells[3]
            assert selected.assigned_symbol_id == symbol
            assert selected.review_state == "approved" and selected.assignment_source == "human"
            assert selected.approved_crop_sample_id == selected.crop_sample_id
            assert (
                selected.approved_rendered_pixel_checksum_sha256
                == selected.rendered_pixel_checksum_sha256
            )
            assert all(cell.review_state == "pending" for cell in cells if cell.cell_index != 3)
            assert (
                session.get(ImageBoardGeometryPendingModel, seed.pending_ids[1]).status == "pending"
            )
            source = session.get(SourceImageModel, seed.source_image_id)
            assert source.geometry_completeness_status == "geometry_incomplete"
            assert source.geometry_exception_reason is None
            events = session.scalar(select(func.count()).select_from(ImageSymbolReviewEventModel))
            return [(cell.id, cell.revision, cell.crop_sample_id) for cell in cells], events

    before = snapshot()
    # Lost-response replay through a newly created app and fresh DB sessions.
    app = _app(database, root)
    try:
        with TestClient(app) as client:
            replay = client.post(f"{base}/manual-resolution", json=command)
            assert replay.status_code == 200, replay.text
            assert replay.json()["created"] is False
            assert UUID(replay.json()["reviewItemId"]) == UUID(saved.json()["reviewItemId"])
    finally:
        app.state.database_engine.dispose()
    assert snapshot() == before

    # The exception does not approve positions with no source pixels. A
    # failed symbol save must roll back the newly materialized partial board.
    partial = _seed(
        factory, game_id, root, label="neural-outside", slot_count=2, sequence_base=2405
    )
    outside_nodes = [
        {"x": float(-200 + column * 100), "y": float(50 + row * 100)}
        for row in range(4)
        for column in range(6)
    ]
    with game_storage_scope(game_id), factory.begin() as session:
        revision = session.scalar(
            select(ImageSourceGeometryRevisionModel).where(
                ImageSourceGeometryRevisionModel.source_image_id == partial.source_image_id
            )
        )
        entries = [dict(entry) for entry in revision.board_geometries]
        entries[0].update(latticeNodes=outside_nodes, neuralProposalChecksumSha256=proposal)
        revision.board_geometries = entries
    partial_base = (
        f"/api/v1/admin/games/{game_id}/image-imports/{partial.import_job_id}/"
        f"board-cell-geometry-pending/{partial.pending_ids[0]}/manual-resolution"
    )
    partial_command = {
        **command,
        "corners": _PARTIAL_CORNERS,
        "latticeNodes": outside_nodes,
        "expectedManifestChecksumSha256": partial.manifest_checksums[0],
        "idempotencyKey": str(uuid4()),
        "geometryQualification": {
            "completenessStatus": "pending_partial",
            "excludeFromGeometryTraining": True,
            "exclusionReason": "missing_pixels",
            "unavailableCellIndices": list(_PARTIAL_MASK),
            "version": "manual-geometry-qualification-v1",
        },
        "cellSymbols": [{"cellIndex": 0, "symbolId": str(symbol)}],
    }
    app = _app(database, root)
    try:
        with TestClient(app) as client:
            unavailable = client.post(partial_base, json=partial_command)
            assert unavailable.status_code == 422, unavailable.text
            assert unavailable.json()["code"] == "IMAGE_GRID_REVIEW_SYMBOL_CELL_UNAVAILABLE"
            with game_storage_scope(game_id), factory() as session:
                pending = session.get(ImageBoardGeometryPendingModel, partial.pending_ids[0])
                assert pending.status == "pending" and pending.recognized_board_id is None
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(ImageSymbolReviewCellModel)
                        .where(ImageSymbolReviewCellModel.sequence_number >= 2405)
                    )
                    == 0
                )
            partial_command["cellSymbols"] = [{"cellIndex": 3, "symbolId": str(symbol)}]
            partial_command["idempotencyKey"] = str(uuid4())
            visible = client.post(partial_base, json=partial_command)
            assert visible.status_code == 200, visible.text
    finally:
        app.state.database_engine.dispose()
    with game_storage_scope(game_id), factory() as session:
        cells = session.scalars(
            select(ImageSymbolReviewCellModel).where(
                ImageSymbolReviewCellModel.sequence_number == 2405
            )
        ).all()
        assert len(cells) == 15
        assert [cell.cell_index for cell in cells if cell.review_state == "approved"] == [3]
        assert all(
            not cell.source_available and cell.crop_sample_id is None
            for cell in cells
            if cell.cell_index in _PARTIAL_MASK
        )
