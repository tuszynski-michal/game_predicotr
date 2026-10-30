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


@pytest.mark.parametrize("patterns", [[], [PATTERN], [PATTERN, PATTERN]])
def test_removed_post_never_runs_search(client, monkeypatch, patterns):
    def forbidden(**kwargs):
        raise AssertionError("Removed search must not execute")

    monkeypatch.setattr(Repository, "search", forbidden)
    assert client.post(PATH, json={"patterns": patterns}).status_code == 405


def test_single_get_still_searches(client):
    response = client.get(PATH, params={"cell": "0:A", "limit": 40})
    assert response.status_code == 200
    assert response.json()["results"][0]["sequenceNumber"] == 1


def test_openapi_only_exposes_get(client):
    schema = client.get("/openapi.json").json()
    assert "post" not in schema["paths"]["/api/v1/admin/games/{game_id}/board-search"]
