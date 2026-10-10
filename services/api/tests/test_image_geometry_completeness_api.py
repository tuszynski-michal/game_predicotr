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
    SourceImageGeometryStatus,
    encode_geometry_image_cursor,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewNotFoundError,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.image_geometry_completeness_repository import (
    GeometryCompletenessReport,
    GeometryGateCounts,
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
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    SourceImageGeometryException,
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
            gate=GeometryGateCounts(
                geometry_complete=6,
                geometry_incomplete=3,
                geometry_exception=1,
                outside_gate=3,
                not_evaluated=1,
                withheld_boards=17,
            ),
        )

    def incomplete_images(
        self,
        game_id: UUID,
        *,
        import_job_id: UUID | None = None,
        image_state: GeometryImageState | None = None,
        after: GeometryImageCursor | None = None,
        limit: int = 100,
        completeness_status: SourceImageGeometryStatus | None = None,
        gaps_only: bool = False,
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
                    "completenessStatus": completeness_status,
                    "gapsOnly": gaps_only,
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
                            human_approved=True,
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
                    completeness_status=SourceImageGeometryStatus.GEOMETRY_INCOMPLETE,
                    completeness_evaluated_at=COMPUTED_AT,
                ),
            ),
            next_cursor=GeometryImageCursor("folder/seq_1-9.jpg", IMAGE_ID),
            completeness_status=completeness_status,
            gaps_only=gaps_only,
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


class _StateRepository:
    """Fake operator-exception repository (TASK-0807)."""

    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.error: Exception | None = None

    def set_exception(
        self, game_id: UUID, source_image_id: UUID, *, reason: str, actor: str
    ) -> SourceImageGeometryException | None:
        self.calls.append(
            (
                "set",
                {
                    "gameId": game_id,
                    "sourceImageId": source_image_id,
                    "reason": reason,
                    "actor": actor,
                },
            )
        )
        if game_id != self.game_id:
            return None
        if self.error is not None:
            raise self.error
        return SourceImageGeometryException(
            source_image_id=source_image_id,
            status=SourceImageGeometryStatus.GEOMETRY_EXCEPTION,
            image_state=GeometryImageState.INCOMPLETE_MISSING,
            reason=reason,
            exception_by=actor,
            exception_at=COMPUTED_AT,
            materialized_review_item_count=8,
        )

    def withdraw_exception(
        self, game_id: UUID, source_image_id: UUID, *, actor: str
    ) -> SourceImageGeometryException | None:
        self.calls.append(
            ("withdraw", {"gameId": game_id, "sourceImageId": source_image_id, "actor": actor})
        )
        if game_id != self.game_id:
            return None
        if self.error is not None:
            raise self.error
        return SourceImageGeometryException(
            source_image_id=source_image_id,
            status=SourceImageGeometryStatus.GEOMETRY_INCOMPLETE,
            image_state=GeometryImageState.INCOMPLETE_MISSING,
            reason=None,
            exception_by=None,
            exception_at=None,
            materialized_review_item_count=0,
        )


def _client(
    repository: _CompletenessRepository | None,
    artifact_root: Path | None = None,
    state_repository: _StateRepository | None = None,
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
                geometry_completeness_state_repository=state_repository,
            ),
        ),
        base_url="http://127.0.0.1:8000",
        client=("127.0.0.1", 42001),
    )


def _exception_headers(source_image_id: UUID) -> dict[str, str]:
    return {
        "Origin": "http://127.0.0.1:3000",
        "X-Admin-Intent": "local-owner",
        "X-Admin-Confirmation": "confirmed",
        "X-Admin-Target": f"source-image-geometry-exception:{source_image_id}",
    }


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
    # TASK-0807: the persisted gate state and the explicit withholding reason.
    assert body["gate"] == {
        "geometryComplete": 6,
        "geometryIncomplete": 3,
        "geometryException": 1,
        "outsideGate": 3,
        "notEvaluated": 1,
        "withheldBoards": 17,
        "withheldReasonCode": "SOURCE_IMAGE_GEOMETRY_INCOMPLETE",
    }
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
    assert body["completenessStatus"] is None
    assert body["gapsOnly"] is False
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
                "humanApproved": True,
            },
            {
                "positionIndex": 1,
                "sequenceNumber": 2,
                "state": "deferred",
                "reasonCode": "incomplete_lattice",
                "recognizedBoardId": None,
                "quad": None,
                "humanApproved": False,
            },
        ],
        "completenessStatus": "geometry_incomplete",
        "completenessEvaluatedAt": "2026-10-01T12:00:00Z",
        "gateReasonCode": "SOURCE_IMAGE_GEOMETRY_INCOMPLETE",
        "exceptionReason": None,
        "exceptionBy": None,
        "exceptionAt": None,
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
            "completenessStatus": None,
            "gapsOnly": False,
        },
    )


def test_list_gaps_only_passes_the_flag_and_echoes_it() -> None:
    """TASK-0961: one request for the four real-gap states."""

    repository = _CompletenessRepository()
    response = _client(repository).get(
        _url(repository.game_id, "/incomplete-images"), params={"gapsOnly": "true", "limit": 5}
    )

    assert response.status_code == 200, response.text
    assert response.json()["gapsOnly"] is True
    assert response.json()["imageState"] is None
    assert repository.calls[-1][1]["gapsOnly"] is True
    assert repository.calls[-1][1]["imageState"] is None
    assert repository.calls[-1][1]["limit"] == 5


@pytest.mark.parametrize(
    "params",
    [
        {"gapsOnly": "true", "imageState": "incomplete_missing"},
        {"gapsOnly": "true", "completenessStatus": "geometry_incomplete"},
    ],
)
def test_list_gaps_only_conflicts_with_the_other_filters(params: dict[str, str]) -> None:
    repository = _CompletenessRepository()
    response = _client(repository).get(
        _url(repository.game_id, "/incomplete-images"), params=params
    )

    assert response.status_code == 422
    assert response.json()["code"] == "IMAGE_GEOMETRY_COMPLETENESS_FILTER_CONFLICT"
    assert repository.calls == []


@pytest.mark.parametrize("status", ["geometry_incomplete", "geometry_exception"])
def test_list_selects_the_gate_queue_by_the_persisted_status(status: str) -> None:
    repository = _CompletenessRepository()
    response = _client(repository).get(
        _url(repository.game_id, "/incomplete-images"), params={"completenessStatus": status}
    )

    assert response.status_code == 200
    assert response.json()["completenessStatus"] == status
    assert repository.calls[-1][1]["completenessStatus"] == SourceImageGeometryStatus(status)


def test_list_rejects_an_unknown_persisted_status() -> None:
    repository = _CompletenessRepository()
    response = _client(repository).get(
        _url(repository.game_id, "/incomplete-images"), params={"completenessStatus": "done"}
    )

    assert response.status_code == 422
    assert repository.calls == []


def test_exception_is_a_confirmed_high_impact_operation_with_a_required_reason() -> None:
    repository = _CompletenessRepository()
    state = _StateRepository(repository.game_id)
    client = _client(repository, state_repository=state)
    url = _url(repository.game_id, f"/images/{IMAGE_ID}/exception")

    unconfirmed = client.post(
        url,
        headers={"Origin": "http://127.0.0.1:3000", "X-Admin-Intent": "local-owner"},
        json={"reason": "Plansza 9 poza kadrem"},
    )
    empty_reason = client.post(url, headers=_exception_headers(IMAGE_ID), json={"reason": ""})
    assert state.calls == []
    response = client.post(
        url, headers=_exception_headers(IMAGE_ID), json={"reason": "Plansza 9 poza kadrem"}
    )

    assert unconfirmed.status_code == 403
    assert unconfirmed.json()["code"] == "ADMIN_CONFIRMATION_REQUIRED"
    assert empty_reason.status_code == 422
    assert response.status_code == 200, response.text
    assert response.json() == {
        "sourceImageId": str(IMAGE_ID),
        "completenessStatus": "geometry_exception",
        "imageState": "incomplete_missing",
        "exceptionReason": "Plansza 9 poza kadrem",
        "exceptionBy": "local-admin",
        "exceptionAt": "2026-10-01T12:00:00Z",
        "materializedReviewItemCount": 8,
    }
    assert state.calls == [
        (
            "set",
            {
                "gameId": repository.game_id,
                "sourceImageId": IMAGE_ID,
                "reason": "Plansza 9 poza kadrem",
                "actor": "local-admin",
            },
        )
    ]


def test_exception_withdrawal_and_domain_errors_pass_through() -> None:
    repository = _CompletenessRepository()
    state = _StateRepository(repository.game_id)
    client = _client(repository, state_repository=state)
    url = _url(repository.game_id, f"/images/{IMAGE_ID}/exception")

    withdrawn = client.delete(url, headers=_exception_headers(IMAGE_ID))
    unknown_game = client.delete(
        _url(uuid4(), f"/images/{IMAGE_ID}/exception"), headers=_exception_headers(IMAGE_ID)
    )
    state.error = ImageReviewConflictError(
        "IMAGE_GEOMETRY_EXCEPTION_HUMAN_DECISIONS_PRESENT", "Human decisions exist."
    )
    refused = client.delete(url, headers=_exception_headers(IMAGE_ID))

    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["completenessStatus"] == "geometry_incomplete"
    assert withdrawn.json()["exceptionReason"] is None
    assert unknown_game.status_code == 404
    assert refused.status_code == 409
    assert refused.json()["code"] == "IMAGE_GEOMETRY_EXCEPTION_HUMAN_DECISIONS_PRESENT"
    assert state.calls[0] == (
        "withdraw",
        {"gameId": repository.game_id, "sourceImageId": IMAGE_ID, "actor": "local-admin"},
    )


def test_exception_returns_409_when_the_state_repository_is_not_configured() -> None:
    repository = _CompletenessRepository()
    response = _client(repository).post(
        _url(repository.game_id, f"/images/{IMAGE_ID}/exception"),
        headers=_exception_headers(IMAGE_ID),
        json={"reason": "Wyjątek"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "IMAGE_GEOMETRY_COMPLETENESS_UNAVAILABLE"


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
