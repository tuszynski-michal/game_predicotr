from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.image_reviews import (
    OperationalImageReviewRepository,
    OperationalImageReviewService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_import_coverage import (
    CoveragePage,
    CoverageSegment,
    MissingReason,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.board_import_coverage_repository import (
    BoardImportCoverageCounts,
    BoardImportCoverageNotices,
    BoardImportCoverageReport,
)


class _NoopOperationalRepository(OperationalImageReviewRepository):
    """The endpoint under test never touches the main review repository."""


class _CoverageRepository:
    def __init__(self) -> None:
        self.game_id = uuid4()
        self.last_call: dict[str, object] | None = None

    def board_import_coverage(
        self,
        game_id: UUID,
        *,
        view: str,
        range_from: int | None,
        range_to: int | None,
        after_sequence_number: int | None,
        limit: int,
    ) -> BoardImportCoverageReport | None:
        self.last_call = {
            "gameId": game_id,
            "view": view,
            "rangeFrom": range_from,
            "rangeTo": range_to,
            "afterSequenceNumber": after_sequence_number,
            "limit": limit,
        }
        if game_id != self.game_id:
            return None
        page = CoveragePage(
            segments=(
                CoverageSegment(start=1, end=2, state=MissingReason.NO_SOURCE.value),
                CoverageSegment(
                    start=8,
                    end=9,
                    state=MissingReason.IMPORT_IN_PROGRESS.value,
                    import_job_id=UUID(int=42),
                ),
            ),
            next_after_sequence_number=9,
        )
        return BoardImportCoverageReport(
            game_id=game_id,
            expected_layout_count=20,
            counts=BoardImportCoverageCounts(
                expected=20, added=17, missing=3, approved=10, out_of_range=1
            ),
            missing_by_reason={
                MissingReason.NO_SOURCE: 2,
                MissingReason.IMPORT_IN_PROGRESS: 1,
            },
            notices=BoardImportCoverageNotices(
                unnumbered_cut_board_count=4,
                failed_sources_without_range_count=1,
                active_import_job_count=1,
                active_sources_without_range_count=0,
            ),
            view=view,
            range_from=range_from,
            range_to=range_to,
            range_counts=(3, 2) if range_from is not None or range_to is not None else None,
            page=page,
            computed_at=datetime(2026, 9, 24, 12, 0, 0, tzinfo=UTC),
        )


def _client(repository: _CoverageRepository) -> TestClient:
    return TestClient(
        create_app(
            ApiSettings.from_environment({}),
            image_review_service_dependency=lambda: OperationalImageReviewService(
                _NoopOperationalRepository(),
                board_import_coverage_repository=repository,
            ),
        )
    )


def _url(game_id: UUID) -> str:
    return f"/api/v1/admin/image-review-items/board-import-coverage/{game_id}"


def test_returns_full_camel_case_response_for_known_game() -> None:
    repository = _CoverageRepository()
    response = _client(repository).get(_url(repository.game_id))

    assert response.status_code == 200
    body = response.json()
    assert body["gameId"] == str(repository.game_id)
    assert body["expectedLayoutCount"] == 20
    assert body["counts"] == {
        "expected": 20,
        "added": 17,
        "missing": 3,
        "approved": 10,
        "outOfRange": 1,
    }
    assert body["missingByReason"] == {"no_source": 2, "import_in_progress": 1}
    assert body["notices"] == {
        "unnumberedCutBoardCount": 4,
        "failedSourcesWithoutRangeCount": 1,
        "activeImportJobCount": 1,
        "activeSourcesWithoutRangeCount": 0,
    }
    assert body["view"] == "missing"
    assert body["range"] is None
    assert body["rangeCounts"] is None
    assert body["segments"] == [
        {
            "start": 1,
            "end": 2,
            "count": 2,
            "state": "no_source",
            "errorCode": None,
            "geometryReasonCode": None,
            "importJobId": None,
        },
        {
            "start": 8,
            "end": 9,
            "count": 2,
            "state": "import_in_progress",
            "errorCode": None,
            "geometryReasonCode": None,
            "importJobId": str(UUID(int=42)),
        },
    ]
    assert body["nextAfterSequenceNumber"] == 9
    assert body["computedAt"] == "2026-09-24T12:00:00Z"
    assert repository.last_call == {
        "gameId": repository.game_id,
        "view": "missing",
        "rangeFrom": None,
        "rangeTo": None,
        "afterSequenceNumber": None,
        "limit": 100,
    }


def test_passes_through_view_range_and_cursor_query_params() -> None:
    repository = _CoverageRepository()
    response = _client(repository).get(
        _url(repository.game_id),
        params={
            "view": "added",
            "from": 100,
            "to": 200,
            "afterSequenceNumber": 150,
            "limit": 25,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["view"] == "added"
    assert body["range"] == {"from": 100, "to": 200}
    assert body["rangeCounts"] == {"added": 3, "missing": 2}
    assert repository.last_call == {
        "gameId": repository.game_id,
        "view": "added",
        "rangeFrom": 100,
        "rangeTo": 200,
        "afterSequenceNumber": 150,
        "limit": 25,
    }


def test_returns_404_for_unknown_game() -> None:
    repository = _CoverageRepository()
    response = _client(repository).get(_url(uuid4()))

    assert response.status_code == 404
    assert response.json()["code"] == "IMAGE_REVIEW_GAME_NOT_FOUND"


def test_returns_422_when_from_is_greater_than_to() -> None:
    repository = _CoverageRepository()
    response = _client(repository).get(
        _url(repository.game_id), params={"from": 10, "to": 5}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "BOARD_IMPORT_COVERAGE_RANGE_INVALID"


def test_returns_422_for_limit_zero() -> None:
    repository = _CoverageRepository()
    response = _client(repository).get(_url(repository.game_id), params={"limit": 0})

    assert response.status_code == 422


def test_returns_422_for_limit_above_maximum() -> None:
    repository = _CoverageRepository()
    response = _client(repository).get(_url(repository.game_id), params={"limit": 101})

    assert response.status_code == 422


def test_returns_422_for_unknown_view() -> None:
    repository = _CoverageRepository()
    response = _client(repository).get(
        _url(repository.game_id), params={"view": "everything"}
    )

    assert response.status_code == 422
