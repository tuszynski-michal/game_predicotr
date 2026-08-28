from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.board_search import BoardSearchService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search import (
    BoardSearchError,
    BoardSearchQueryCell,
    BoardSearchResult,
    BoardSearchScope,
    BoardSearchScore,
)
from game_predictor_api.main import create_app


class MemoryBoardSearchRepository:
    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id
        self.calls: list[tuple[tuple[BoardSearchQueryCell, ...], BoardSearchScope, int]] = []

    def search(
        self,
        *,
        game_id: UUID,
        query: tuple[BoardSearchQueryCell, ...],
        scope: BoardSearchScope,
        limit: int,
    ) -> tuple[BoardSearchResult, ...]:
        if game_id != self.game_id:
            raise BoardSearchError("GAME_NOT_FOUND", "The selected game does not exist.")
        self.calls.append((query, scope, limit))
        return (
            BoardSearchResult(
                review_item_id=uuid4(),
                recognized_board_id=uuid4(),
                import_job_id=uuid4(),
                sequence_number=37,
                status="pending",
                board_checksum_sha256="a" * 64,
                score=BoardSearchScore(
                    score=80.0,
                    exact_match_count=2,
                    alternative_match_count=1,
                    weighted_alternative_score=0.6,
                    mismatch_count=0,
                    unknown_count=0,
                ),
            ),
        )


def _client(repository: MemoryBoardSearchRepository) -> TestClient:
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
        ),
        board_search_service_dependency=lambda: BoardSearchService(repository),
    )
    return TestClient(app)


def test_board_search_endpoint_parses_cells_and_returns_score() -> None:
    game_id = uuid4()
    repository = MemoryBoardSearchRepository(game_id)

    with _client(repository) as client:
        response = client.get(
            f"/api/v1/admin/games/{game_id}/board-search",
            params=[
                ("cell", "7:cherry"),
                ("cell", "1:lemon"),
                ("scope", "all_searchable"),
                ("limit", "10"),
            ],
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["gameId"] == str(game_id)
    assert payload["scope"] == "all_searchable"
    assert payload["queryCellCount"] == 2
    assert payload["results"][0]["sequenceNumber"] == 37
    assert payload["results"][0]["score"] == {
        "score": 80.0,
        "exactMatchCount": 2,
        "alternativeMatchCount": 1,
        "weightedAlternativeScore": 0.6,
        "mismatchCount": 0,
        "unknownCount": 0,
    }
    assert repository.calls == [
        (
            (
                BoardSearchQueryCell(cell_index=1, symbol_code="lemon"),
                BoardSearchQueryCell(cell_index=7, symbol_code="cherry"),
            ),
            BoardSearchScope.ALL_SEARCHABLE,
            10,
        )
    ]


def test_board_search_endpoint_returns_stable_query_errors() -> None:
    game_id = uuid4()
    repository = MemoryBoardSearchRepository(game_id)

    with _client(repository) as client:
        empty = client.get(f"/api/v1/admin/games/{game_id}/board-search")
        duplicate = client.get(
            f"/api/v1/admin/games/{game_id}/board-search",
            params=[("cell", "2:orange"), ("cell", "2:lemon")],
        )
        invalid = client.get(
            f"/api/v1/admin/games/{game_id}/board-search",
            params={"cell": "middle:orange"},
        )

    assert empty.status_code == 422
    assert empty.json()["code"] == "BOARD_SEARCH_QUERY_EMPTY"
    assert duplicate.status_code == 422
    assert duplicate.json()["code"] == "BOARD_SEARCH_CELL_DUPLICATE"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "BOARD_SEARCH_CELL_INVALID"


def test_board_search_endpoint_maps_projection_not_ready_to_conflict() -> None:
    game_id = uuid4()

    class RebuildingRepository(MemoryBoardSearchRepository):
        def search(self, **_kwargs: object) -> tuple[BoardSearchResult, ...]:
            raise BoardSearchError(
                "BOARD_SEARCH_PROJECTION_INCOMPLETE",
                "The board-search projection is not ready for this game.",
            )

    with _client(RebuildingRepository(game_id)) as client:
        response = client.get(
            f"/api/v1/admin/games/{game_id}/board-search",
            params={"cell": "0:orange"},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "BOARD_SEARCH_PROJECTION_INCOMPLETE"
