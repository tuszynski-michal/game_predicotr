from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.image_grid_reviews import create_image_grid_reviews_router
from game_predictor_api.application.image_grid_reviews import (
    ImageGridReviewListSlice,
    ImageGridReviewService,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.grid_cut_suspicion import assess_grid_cut
from game_predictor_api.domain.image_grid_reviews import (
    GridCutReviewCell,
    ImageGridReviewListItem,
    ImageGridReviewSlotKind,
    ImageGridReviewState,
    ImageGridReviewView,
)


def test_suspicious_scan_keeps_cursor_after_empty_batch_and_returns_explicit_cell(tmp_path):
    game, job, review, board, source, cell = (uuid4() for _ in range(6))
    nodes = [{"x": c * 40, "y": r * 30} for r in range(4) for c in range(6)]
    checked_owner = (101, str(uuid4()))
    candidate = ImageGridReviewListItem(
        slot_id=review,
        slot_kind=ImageGridReviewSlotKind.CURRENT_REVIEW,
        review_item_id=review,
        game_id=game,
        import_job_id=job,
        recognized_board_id=board,
        pending_geometry_id=None,
        source_image_id=source,
        position_index=1,
        sequence_number=102,
        source_checksum_sha256="a" * 64,
        source_width=600,
        source_height=400,
        geometry_revision=3,
        approved_geometry_revision=None,
        resolution_revision=0,
        topology=BoardTopology(3, 5),
        geometry={"latticeNodes": nodes},
        asset_mode="virtual_source",
        geometry_engine_name="neural_grid_v1",
        geometry_engine_version="v1",
        board_confidence=0.9,
        reason_codes=(),
        state=ImageGridReviewState.NEEDS_VALIDATION,
        cut_suspicion=assess_grid_cut(nodes),
        cut_review_cells=(GridCutReviewCell(cell, 2, 7, "b" * 64, "c" * 64, True),),
    )

    class Repository:
        def require_game(self, game_id: UUID) -> None:
            assert game_id == game

        def list_grid_reviews(self, *, review_filter, after_key, before_key, limit):
            assert review_filter.game_id == game
            assert review_filter.view is ImageGridReviewView.SUSPICIOUS
            assert review_filter.import_job_id == job
            assert before_key is None
            assert limit == 500
            if after_key is None:
                return ImageGridReviewListSlice((), False, True, 500, checked_owner)
            assert after_key == checked_owner
            return ImageGridReviewListSlice((candidate,), False, False, 1, candidate.cursor_key)

    app = FastAPI()
    app.include_router(
        create_image_grid_reviews_router(
            lambda: ImageGridReviewService(Repository()),
            lambda: None,
            lambda: None,
            tmp_path,
        )
    )
    client = TestClient(app)
    url = f"/admin/games/{game}/grid-reviews"
    params = {"view": "suspicious", "importJobId": str(job), "limit": 500}
    first = client.get(url, params=params)
    assert first.status_code == 200, first.text
    assert first.json()["scannedCount"] == 500
    assert first.json()["items"] == []
    cursor = first.json()["nextCursor"]
    assert cursor is not None
    second = client.get(url, params={**params, "afterCursor": cursor})
    assert second.status_code == 200, second.text
    assert second.json()["nextCursor"] is None
    item = second.json()["items"][0]
    assert item["sequenceNumber"] == 102
    assert item["latticeNodes"] == nodes
    assert item["cutSuspicion"]["reason"] == "board_aspect"
    assert item["cutSuspicion"]["cells"][0] == {
        "cellIndex": 2,
        "pending": True,
        "target": {
            "cellReviewId": str(cell),
            "expectedRevision": 7,
            "expectedGeometryRevision": 3,
            "expectedCropSampleId": "b" * 64,
            "expectedCropChecksumSha256": "c" * 64,
        },
    }
