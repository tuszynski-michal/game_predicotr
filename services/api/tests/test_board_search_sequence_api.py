from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.board_search import BoardSearchService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search import (
    BoardSearchAssetMode,
    BoardSearchResult,
    BoardSearchScore,
)
from game_predictor_api.domain.board_search_sequence import BoardSearchSequenceResult
from game_predictor_api.main import create_app

GAME = UUID(int=1)
PATH = f"/api/v1/admin/games/{GAME}/board-search"
PATTERN = {"cells": [{"cellIndex": 0, "symbolCode": "A"}]}


def result(position=1):
    return BoardSearchResult(
        BoardSearchAssetMode.OPERATIONAL_REVIEW,
        UUID(int=10),
        UUID(int=11),
        UUID(int=12),
        position,
        "pending",
        "a" * 64,
        BoardSearchScore(100, 1, 0, 0, 0, 0),
    )


class Repository:
    def search(self, **kwargs):
        return (result(),)

    def search_sequence(self, **kwargs):
        return (
            BoardSearchSequenceResult((result(1), result(2)), BoardSearchScore(100, 2, 0, 0, 0, 0)),
        )


@pytest.fixture(scope="module")
def client():
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
        ),
        board_search_service_dependency=lambda: BoardSearchService(Repository()),
    )
    with TestClient(app) as value:
        yield value


def test_single_post_delegates_to_get(client):
    old = client.get(PATH, params={"cell": "0:A"})
    new = client.post(PATH, json={"patterns": [PATTERN]})
    assert old.status_code == new.status_code == 200
    assert new.json()["results"][0]["boards"] == old.json()["results"]


def test_sequence_contract_and_per_board_scores(client):
    response = client.post(PATH, json={"patterns": [PATTERN, PATTERN]})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["patternCount"] == data["queryCellCount"] == 2
    assert data["results"][0]["endSequenceNumber"] == 2
    assert data["results"][0]["score"]["exactMatchCount"] == 2


@pytest.mark.parametrize(
    "patterns",
    [[], [PATTERN] * 5, [{"cells": []}], [{"cells": [{"cellIndex": 0, "symbolCode": "?"}]}]],
)
def test_invalid_patterns_have_stable_error(client, patterns):
    response = client.post(PATH, json={"patterns": patterns})
    assert response.status_code == 422
    assert response.json()["code"] == "BOARD_SEARCH_SEQUENCE_INVALID"


def test_actual_body_limit_and_content_type(client):
    assert (
        client.post(
            PATH, content=b"x" * 32769, headers={"content-type": "application/json"}
        ).status_code
        == 413
    )
    assert (
        client.post(PATH, content=b"{}", headers={"content-type": "text/plain"}).status_code == 415
    )
    assert client.post(PATH + "?limit=1", json={"patterns": [PATTERN]}).status_code == 422
