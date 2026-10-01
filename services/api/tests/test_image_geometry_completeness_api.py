from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.image_reviews import (
    OperationalImageReviewRepository,
    OperationalImageReviewService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_geometry_completeness import (
    GeometryImageCursor,
    GeometryImageState,
    GeometryPositionState,
    LowQualityThresholds,
    encode_geometry_image_cursor,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewNotFoundError,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.image_geometry_completeness_repository import (
    GeometryCompletenessReport,
    GeometryImageCounts,
    GeometryImagePosition,
    GeometryImageSourceStatusCount,
    GeometryPositionCount,
    GeometrySourceImageAsset,
    IncompleteGeometryImage,
    IncompleteGeometryImagePage,
    LowQualityBoard,
    LowQualityBoardsReport,
)

COMPUTED_AT = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
IMAGE_ID = UUID(int=11)
JOB_ID = UUID(int=22)
BOARD_ID = UUID(int=33)
OTHER_GAME_IMAGE_ID = UUID(int=55)


class _NoopOperationalRepository(OperationalImageReviewRepository):
    """The endpoints under test never touch the main review repository."""


class _CompletenessRepository:
    def __init__(self) -> None:
        self.game_id = uuid4()
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.timeout = False
        self.assets: dict[UUID, GeometrySourceImageAsset] = {}

    def completeness_report(
        self, game_id: UUID, *, import_job_id: UUID | None = None
    ) -> GeometryCompletenessReport | None:
        self.calls.append(("report", {"gameId": game_id, "importJobId": import_job_id}))
        if game_id != self.game_id:
            return None
        return GeometryCompletenessReport(
            game_id=game_id,
            import_job_id=import_job_id,
            images=GeometryImageCounts(
                total=14,
                complete=6,
                incomplete_missing=1,
                incomplete_partial=1,
                incomplete_uncertain=1,
                no_source_geometry=1,
                import_failed=1,
                superseded=2,
            ),
            expected_board_count=81,
            positions=(
                GeometryPositionCount(GeometryPositionState.OK, None, 77),
                GeometryPositionCount(GeometryPositionState.SUPERSEDED, None, 18),
                GeometryPositionCount(GeometryPositionState.MISSING, None, 2),
                GeometryPositionCount(GeometryPositionState.DEFERRED, "residual_too_high", 1),
                GeometryPositionCount(GeometryPositionState.PARTIAL, None, 1),
            ),
            source_statuses=(
                GeometryImageSourceStatusCount(
                    GeometryImageState.COMPLETE, "waiting_for_review", 6
                ),
                GeometryImageSourceStatusCount(
                    GeometryImageState.NO_SOURCE_GEOMETRY, "processing", 1
                ),
            ),
            computed_at=COMPUTED_AT,
        )

    def incomplete_images(
        self,
        game_id: UUID,
        *,
        import_job_id: UUID | None = None,
        image_state: GeometryImageState | None = None,
        after: GeometryImageCursor | None = None,
        limit: int = 100,
    ) -> IncompleteGeometryImagePage | None:
        self.calls.append(
            (
                "list",
                {
                    "gameId": game_id,
                    "importJobId": import_job_id,
                    "imageState": image_state,
                    "after": after,
                    "limit": limit,
                },
            )
        )
        if game_id != self.game_id:
            return None
        quad = ((10.0, 20.0), (110.0, 20.0), (110.0, 90.0), (10.0, 90.0))
        return IncompleteGeometryImagePage(
            game_id=game_id,
            import_job_id=import_job_id,
            image_state=image_state,
            images=(
                IncompleteGeometryImage(
                    source_image_id=IMAGE_ID,
                    import_job_id=JOB_ID,
                    relative_path="folder/seq_1-9.jpg",
                    source_status="waiting_for_review",
                    image_state=GeometryImageState.INCOMPLETE_MISSING,
                    source_revision=1,
                    sequence_range_start=1,
                    sequence_range_end=2,
                    expected_board_count=2,
                    oriented_width=1080,
                    oriented_height=652,
                    import_error_code="IMAGE_STAGE_EXECUTION_FAILED",
                    positions=(
                        GeometryImagePosition(
                            position_index=0,
                            sequence_number=1,
                            state=GeometryPositionState.OK,
                            reason_code=None,
                            recognized_board_id=BOARD_ID,
                            quad=quad,
                        ),
                        GeometryImagePosition(
                            position_index=1,
                            sequence_number=2,
                            state=GeometryPositionState.DEFERRED,
                            reason_code="incomplete_lattice",
                            recognized_board_id=None,
                            quad=None,
                        ),
                    ),
                ),
            ),
            next_cursor=GeometryImageCursor("folder/seq_1-9.jpg", IMAGE_ID),
        )

    def source_image_asset(
        self, game_id: UUID, source_image_id: UUID
    ) -> GeometrySourceImageAsset | None:
        self.calls.append(("sourceAsset", {"gameId": game_id, "sourceImageId": source_image_id}))
        if game_id != self.game_id:
            return None
        asset = self.assets.get(source_image_id)
        if asset is None:
            raise ImageReviewNotFoundError(
                "IMAGE_GEOMETRY_COMPLETENESS_SOURCE_IMAGE_NOT_FOUND",
                "The selected source image does not belong to this game.",
            )
        return asset

    def low_quality_boards(
        self,
        game_id: UUID,
        *,
        import_job_id: UUID | None = None,
        thresholds: LowQualityThresholds,
        limit: int = 100,
    ) -> LowQualityBoardsReport | None:
        self.calls.append(
            (
                "lowQuality",
                {
                    "gameId": game_id,
                    "importJobId": import_job_id,
                    "maxConfidence": thresholds.max_confidence,
                    "minCells": thresholds.min_cells,
                    "limit": limit,
                },
            )
        )
        if game_id != self.game_id:
            return None
        if self.timeout:
            raise ImageReviewConflictError(
                "IMAGE_GEOMETRY_LOW_QUALITY_TIMEOUT", "Too slow.", details={"timeoutMs": 10000}
            )
        return LowQualityBoardsReport(
            game_id=game_id,
            import_job_id=import_job_id,
            max_confidence=thresholds.max_confidence,
            min_cells=thresholds.min_cells,
            total_boards=3,
            boards=(
                LowQualityBoard(
                    recognized_board_id=BOARD_ID,
                    source_image_id=IMAGE_ID,
                    import_job_id=JOB_ID,
                    relative_path="folder/seq_1-9.jpg",
                    position_index=4,
                    sequence_number=5,
                    low_cell_count=7,
                    min_confidence=0.31,
                ),
            ),
            computed_at=COMPUTED_AT,
        )


def _client(
    repository: _CompletenessRepository | None, artifact_root: Path | None = None
) -> TestClient:
    settings = ApiSettings.from_environment({})
    if artifact_root is not None:
        settings = replace(settings, artifact_root=artifact_root)
    return TestClient(
        create_app(
            settings,
            image_review_service_dependency=lambda: OperationalImageReviewService(
                _NoopOperationalRepository(),
                geometry_completeness_repository=repository,
            ),
        )
    )


def _url(game_id: UUID, suffix: str = "") -> str:
    return f"/api/v1/admin/image-review-items/geometry-completeness/{game_id}{suffix}"


def test_report_returns_counters_by_image_state_position_state_and_source_status() -> None:
    repository = _CompletenessRepository()
    response = _client(repository).get(_url(repository.game_id))

    assert response.status_code == 200
    body = response.json()
    assert body["gameId"] == str(repository.game_id)
    assert body["importJobId"] is None
    assert body["images"] == {
        "total": 14,
        "complete": 6,
        "incomplete": 6,
        "incompleteMissing": 1,
        "incompletePartial": 1,
        "incompleteUncertain": 1,
        "noSourceGeometry": 1,
        "superseded": 2,
        "importFailed": 1,
    }
    assert body["expectedBoardCount"] == 81
    assert body["positions"] == [
        {"state": "ok", "reasonCode": None, "count": 77},
        {"state": "superseded", "reasonCode": None, "count": 18},
        {"state": "missing", "reasonCode": None, "count": 2},
        {"state": "deferred", "reasonCode": "residual_too_high", "count": 1},
        {"state": "partial", "reasonCode": None, "count": 1},
    ]
    assert body["sourceStatuses"] == [
        {"imageState": "complete", "sourceStatus": "waiting_for_review", "count": 6},
        {"imageState": "no_source_geometry", "sourceStatus": "processing", "count": 1},
    ]
    assert body["computedAt"] == "2026-10-01T12:00:00Z"
    assert repository.calls == [("report", {"gameId": repository.game_id, "importJobId": None})]


def test_report_passes_the_import_filter_through() -> None:
    repository = _CompletenessRepository()
    response = _client(repository).get(
        _url(repository.game_id), params={"importJobId": str(JOB_ID)}
    )

    assert response.status_code == 200
    assert response.json()["importJobId"] == str(JOB_ID)
    assert repository.calls[-1] == (
        "report",
        {"gameId": repository.game_id, "importJobId": JOB_ID},
    )


def test_report_returns_404_for_an_unknown_game() -> None:
    response = _client(_CompletenessRepository()).get(_url(uuid4()))

    assert response.status_code == 404
    assert response.json()["code"] == "IMAGE_REVIEW_GAME_NOT_FOUND"


def test_report_returns_409_when_the_repository_is_not_configured() -> None:
    response = _client(None).get(_url(uuid4()))

    assert response.status_code == 409
    assert response.json()["code"] == "IMAGE_GEOMETRY_COMPLETENESS_UNAVAILABLE"


def test_list_returns_images_with_positions_quads_and_the_import_error_code() -> None:
    repository = _CompletenessRepository()
    response = _client(repository).get(_url(repository.game_id, "/incomplete-images"))

    assert response.status_code == 200
    body = response.json()
    assert body["imageState"] is None
    assert body["nextCursor"] is not None
    [image] = body["images"]
    assert image == {
        "sourceImageId": str(IMAGE_ID),
        "importJobId": str(JOB_ID),
        "relativePath": "folder/seq_1-9.jpg",
        "sourceStatus": "waiting_for_review",
        "imageState": "incomplete_missing",
        "sourceRevision": 1,
        "sequenceRangeStart": 1,
        "sequenceRangeEnd": 2,
        "expectedBoardCount": 2,
        "orientedWidth": 1080,
        "orientedHeight": 652,
        "importErrorCode": "IMAGE_STAGE_EXECUTION_FAILED",
        "positions": [
            {
                "positionIndex": 0,
                "sequenceNumber": 1,
                "state": "ok",
                "reasonCode": None,
                "recognizedBoardId": str(BOARD_ID),
                "quad": [
                    {"x": 10.0, "y": 20.0},
                    {"x": 110.0, "y": 20.0},
                    {"x": 110.0, "y": 90.0},
                    {"x": 10.0, "y": 90.0},
                ],
            },
            {
                "positionIndex": 1,
                "sequenceNumber": 2,
                "state": "deferred",
                "reasonCode": "incomplete_lattice",
                "recognizedBoardId": None,
                "quad": None,
            },
        ],
    }
    assert repository.calls[-1][1]["limit"] == 25


def test_list_passes_filters_cursor_and_limit_to_the_repository() -> None:
    repository = _CompletenessRepository()
    cursor = encode_geometry_image_cursor(GeometryImageCursor("a/b.jpg", IMAGE_ID))
    response = _client(repository).get(
        _url(repository.game_id, "/incomplete-images"),
        params={
            "importJobId": str(JOB_ID),
            "imageState": "incomplete_partial",
            "afterCursor": cursor,
            "limit": 10,
        },
    )

    assert response.status_code == 200
    assert response.json()["imageState"] == "incomplete_partial"
    assert repository.calls[-1] == (
        "list",
        {
            "gameId": repository.game_id,
            "importJobId": JOB_ID,
            "imageState": GeometryImageState.INCOMPLETE_PARTIAL,
            "after": GeometryImageCursor("a/b.jpg", IMAGE_ID),
            "limit": 10,
        },
    )


@pytest.mark.parametrize("limit", [0, 101])
def test_list_rejects_a_limit_outside_one_to_one_hundred(limit: int) -> None:
    repository = _CompletenessRepository()
    response = _client(repository).get(
        _url(repository.game_id, "/incomplete-images"), params={"limit": limit}
    )

    assert response.status_code == 422
    assert repository.calls == []


@pytest.mark.parametrize("state", ["superseded", "import_failed", "no_source_geometry"])
def test_list_accepts_the_new_image_states_as_filters(state: str) -> None:
    repository = _CompletenessRepository()
    response = _client(repository).get(
        _url(repository.game_id, "/incomplete-images"), params={"imageState": state}
    )

    assert response.status_code == 200
    assert response.json()["imageState"] == state
    assert repository.calls[-1][1]["imageState"] == GeometryImageState(state)


def test_list_rejects_the_complete_state_filter() -> None:
    repository = _CompletenessRepository()
    response = _client(repository).get(
        _url(repository.game_id, "/incomplete-images"), params={"imageState": "complete"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "IMAGE_GEOMETRY_COMPLETENESS_STATE_INVALID"
    assert repository.calls == []


def test_list_rejects_an_unknown_state_and_a_garbage_cursor() -> None:
    repository = _CompletenessRepository()
    client = _client(repository)

    assert (
        client.get(
            _url(repository.game_id, "/incomplete-images"), params={"imageState": "bogus"}
        ).status_code
        == 422
    )
    garbage = client.get(
        _url(repository.game_id, "/incomplete-images"), params={"afterCursor": "%%%"}
    )
    assert garbage.status_code == 422
    assert garbage.json()["code"] == "IMAGE_GEOMETRY_COMPLETENESS_CURSOR_INVALID"
    assert repository.calls == []


def test_list_returns_404_for_an_unknown_game() -> None:
    response = _client(_CompletenessRepository()).get(_url(uuid4(), "/incomplete-images"))

    assert response.status_code == 404
    assert response.json()["code"] == "IMAGE_REVIEW_GAME_NOT_FOUND"


def test_low_quality_uses_the_documented_default_thresholds() -> None:
    repository = _CompletenessRepository()
    response = _client(repository).get(_url(repository.game_id, "/low-quality-boards"))

    assert response.status_code == 200
    assert response.json() == {
        "gameId": str(repository.game_id),
        "importJobId": None,
        "maxConfidence": 0.8,
        "minCells": 5,
        "totalBoards": 3,
        "boards": [
            {
                "recognizedBoardId": str(BOARD_ID),
                "sourceImageId": str(IMAGE_ID),
                "importJobId": str(JOB_ID),
                "relativePath": "folder/seq_1-9.jpg",
                "positionIndex": 4,
                "sequenceNumber": 5,
                "lowCellCount": 7,
                "minConfidence": 0.31,
            }
        ],
        "computedAt": "2026-10-01T12:00:00Z",
    }
    assert repository.calls[-1][1]["maxConfidence"] == 0.8
    assert repository.calls[-1][1]["minCells"] == 5


def test_low_quality_passes_explicit_thresholds_and_the_import_filter() -> None:
    repository = _CompletenessRepository()
    response = _client(repository).get(
        _url(repository.game_id, "/low-quality-boards"),
        params={
            "importJobId": str(JOB_ID),
            "maxConfidence": 0.6,
            "minCells": 3,
            "limit": 20,
        },
    )

    assert response.status_code == 200
    assert repository.calls[-1] == (
        "lowQuality",
        {
            "gameId": repository.game_id,
            "importJobId": JOB_ID,
            "maxConfidence": 0.6,
            "minCells": 3,
            "limit": 20,
        },
    )


@pytest.mark.parametrize(
    "params",
    [
        {"maxConfidence": -0.1},
        {"maxConfidence": 1.1},
        {"minCells": 0},
        {"minCells": 16},
        {"limit": 0},
        {"limit": 101},
    ],
)
def test_low_quality_rejects_out_of_range_thresholds_and_limits(
    params: dict[str, float],
) -> None:
    repository = _CompletenessRepository()
    response = _client(repository).get(
        _url(repository.game_id, "/low-quality-boards"), params=params
    )

    assert response.status_code == 422
    assert repository.calls == []


def test_low_quality_timeout_is_an_explicit_error_not_an_empty_result() -> None:
    repository = _CompletenessRepository()
    repository.timeout = True
    response = _client(repository).get(_url(repository.game_id, "/low-quality-boards"))

    assert response.status_code == 409
    assert response.json()["code"] == "IMAGE_GEOMETRY_LOW_QUALITY_TIMEOUT"
    assert response.json()["details"] == {"timeoutMs": 10000}


def test_low_quality_returns_404_for_an_unknown_game() -> None:
    response = _client(_CompletenessRepository()).get(_url(uuid4(), "/low-quality-boards"))

    assert response.status_code == 404


def _source_url(game_id: UUID, source_image_id: UUID) -> str:
    return _url(game_id, f"/images/{source_image_id}/source")


def test_source_asset_serves_the_checksum_bound_file_of_any_image_of_the_game(
    tmp_path: Path,
) -> None:
    repository = _CompletenessRepository()
    content = b"geometry-completeness-source-image"
    path = tmp_path / "data" / "originals" / "ab" / "photo.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    repository.assets[IMAGE_ID] = GeometrySourceImageAsset(
        source_image_id=IMAGE_ID,
        relative_path="originals/ab/photo.jpg",
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )

    response = _client(repository, tmp_path).get(_source_url(repository.game_id, IMAGE_ID))

    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, immutable, max-age=31536000"
    assert repository.calls == [
        ("sourceAsset", {"gameId": repository.game_id, "sourceImageId": IMAGE_ID})
    ]


def test_source_asset_fails_closed_on_checksum_drift(tmp_path: Path) -> None:
    repository = _CompletenessRepository()
    path = tmp_path / "data" / "photo.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"original")
    repository.assets[IMAGE_ID] = GeometrySourceImageAsset(
        source_image_id=IMAGE_ID,
        relative_path="photo.png",
        checksum_sha256=hashlib.sha256(b"original").hexdigest(),
    )
    client = _client(repository, tmp_path)
    assert client.get(_source_url(repository.game_id, IMAGE_ID)).status_code == 200

    path.write_bytes(b"changed")
    drifted = client.get(_source_url(repository.game_id, IMAGE_ID))

    assert drifted.status_code == 404
    assert drifted.json()["code"] == "IMAGE_REVIEW_ASSET_CHECKSUM_DRIFT"


@pytest.mark.parametrize(
    ("relative_path", "code"),
    [
        ("../escape.png", "IMAGE_REVIEW_ASSET_PATH_UNSAFE"),
        ("missing.png", "IMAGE_REVIEW_ASSET_NOT_FOUND"),
        ("document.pdf", "IMAGE_REVIEW_ASSET_MEDIA_TYPE_UNSUPPORTED"),
    ],
)
def test_source_asset_rejects_unsafe_missing_and_unsupported_files(
    tmp_path: Path, relative_path: str, code: str
) -> None:
    repository = _CompletenessRepository()
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "document.pdf").write_bytes(b"pdf")
    repository.assets[IMAGE_ID] = GeometrySourceImageAsset(
        IMAGE_ID, relative_path, hashlib.sha256(b"pdf").hexdigest()
    )

    response = _client(repository, tmp_path).get(_source_url(repository.game_id, IMAGE_ID))

    assert response.status_code == 404
    assert response.json()["code"] == code


def test_source_asset_returns_404_for_an_image_of_another_game_or_an_unknown_one(
    tmp_path: Path,
) -> None:
    repository = _CompletenessRepository()
    client = _client(repository, tmp_path)

    unknown_image = client.get(_source_url(repository.game_id, OTHER_GAME_IMAGE_ID))
    unknown_game = client.get(_source_url(uuid4(), IMAGE_ID))

    assert unknown_image.status_code == 404
    assert unknown_image.json()["code"] == "IMAGE_GEOMETRY_COMPLETENESS_SOURCE_IMAGE_NOT_FOUND"
    assert unknown_game.status_code == 404
    assert unknown_game.json()["code"] == "IMAGE_REVIEW_GAME_NOT_FOUND"


def test_source_asset_returns_409_when_the_repository_is_not_configured() -> None:
    response = _client(None).get(_source_url(uuid4(), IMAGE_ID))

    assert response.status_code == 409
    assert response.json()["code"] == "IMAGE_GEOMETRY_COMPLETENESS_UNAVAILABLE"
