"""Only expected read projection failures degrade; programming errors still surface."""

from uuid import uuid4

import pytest
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
from game_predictor_api.schemas.grid_recognition_status import GameRecognitionStatus
from game_predictor_api.storage.game_storage_routing import (
    GameStorageRoutingError,
    current_game_storage_scope,
)
from game_predictor_api.storage.grid_recognition_status import routed_game_recognition_status
from sqlalchemy.exc import DataError, DBAPIError, OperationalError


class DriverFailure(Exception):
    def __init__(self, sqlstate):
        self.sqlstate = sqlstate


@pytest.mark.parametrize(
    "error,code",
    [
        (
            GridModelRegistryError("GRID_MODEL_FORMAT_UNSUPPORTED", "missing"),
            "GRID_MODEL_FORMAT_UNSUPPORTED",
        ),
        (
            GameStorageRoutingError("GAME_STORAGE_BLOCKED", "blocked", details={}),
            "GAME_STORAGE_BLOCKED",
        ),
        (
            OperationalError("read", {}, DriverFailure("08006")),
            "NEURAL_GRID_STATUS_STORAGE_UNAVAILABLE",
        ),
        (DataError("read", {}, DriverFailure("22000")), "NEURAL_GRID_STATUS_DATA_UNAVAILABLE"),
        (DBAPIError("read", {}, DriverFailure("42P01")), "NEURAL_GRID_STATUS_STORAGE_UNAVAILABLE"),
    ],
)
def test_expected_projection_failures_have_nullable_typed_unavailable_status(tmp_path, error, code):
    def broken_sessions():
        raise error

    result = routed_game_recognition_status(broken_sessions, tmp_path, uuid4(), {})
    assert GameRecognitionStatus.model_validate(result).model_dump() == {
        "scope": "current_game",
        "capabilities": None,
        "evaluation": {"state": "unavailable", "reasonCodes": [code]},
        "automatic": {"state": "unavailable", "reasonCodes": [code]},
    }
    assert current_game_storage_scope() is None


@pytest.mark.parametrize(
    "error",
    [
        TypeError("bug"),
        ValueError("bug"),
        RuntimeError("bug"),
        DBAPIError("bad sql", {}, DriverFailure("42601")),
    ],
)
def test_programming_errors_are_not_disguised_as_unavailable(tmp_path, error):
    def broken_sessions():
        raise error

    with pytest.raises(type(error)) as caught:
        routed_game_recognition_status(broken_sessions, tmp_path, uuid4(), {})
    assert caught.value is error
    assert current_game_storage_scope() is None
