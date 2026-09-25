from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from game_predictor_api.storage.game_data_v2_manifest_v1 import VERSION
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageLocation,
    GameStorageRouter,
    GameStorageRoutingError,
    GameStorageSchema,
    GameStorageStatus,
    current_game_storage_scope,
    game_id_from_path,
    game_storage_scope,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_in_memory_adapter_is_v2_and_safe_raw_table_name() -> None:
    game_id = uuid4()
    router = GameStorageRouter()
    with Session(create_engine("sqlite+pysqlite:///:memory:")) as session:
        location = router.bind(session, game_id, intent=GameStorageIntent.WRITE)

    assert location == GameStorageLocation(
        game_id=game_id,
        store_schema=GameStorageSchema.V2,
        generation=2,
        manifest_version=VERSION,
        status=GameStorageStatus.ACTIVE,
        revision=0,
    )
    assert location.storage_version == VERSION
    assert location.write_available is True
    assert router.qualified_game_table(location, "recognized_boards") == (
        '"game_data_v2"."recognized_boards"'
    )


def test_unknown_raw_table_is_rejected() -> None:
    router = GameStorageRouter()
    location = router._in_memory_v2(uuid4())
    with pytest.raises(GameStorageRoutingError) as raised:
        router.qualified_game_table(location, "jobs")
    assert raised.value.code == "GAME_STORAGE_TABLE_NOT_OWNED"


def test_missing_greenfield_registry_is_visible_but_not_writable() -> None:
    location = GameStorageRouter._from_row(uuid4(), None)

    assert location.store_schema is GameStorageSchema.V2
    assert location.generation == 2
    assert location.status is GameStorageStatus.BLOCKED
    assert location.write_available is False


@pytest.mark.parametrize(
    ("store_schema", "generation"),
    [("public", 1), ("public", 2), ("game_data_v2", 1)],
)
def test_schema_generation_mismatch_is_rejected(store_schema: str, generation: int) -> None:
    with pytest.raises(GameStorageRoutingError) as raised:
        GameStorageRouter._from_row(
            uuid4(),
            {
                "store_schema": store_schema,
                "generation": generation,
                "manifest_version": VERSION,
                "status": "active",
                "revision": 1,
            },
        )
    assert raised.value.code == "GAME_STORAGE_LOCATION_INVALID"


def test_one_transaction_cannot_switch_game_scope() -> None:
    router = GameStorageRouter()
    first = uuid4()
    second = uuid4()
    with Session(create_engine("sqlite+pysqlite:///:memory:")) as session:
        router.bind(session, first, intent=GameStorageIntent.READ)
        with pytest.raises(GameStorageRoutingError) as raised:
            router.bind(session, second, intent=GameStorageIntent.READ)
    assert raised.value.code == "GAME_STORAGE_SESSION_SCOPE_CONFLICT"


def test_scope_context_and_path_parser_are_bounded() -> None:
    game_id = uuid4()
    assert game_id_from_path(f"/api/v1/admin/games/{game_id}/symbols") == game_id
    assert game_id_from_path(f"/api/v1/jobs/{game_id}") is None
    assert game_id_from_path("/api/v1/admin/games/not-a-uuid/symbols") is None
    assert current_game_storage_scope() is None
    with game_storage_scope(game_id, expected_generation=4):
        scope = current_game_storage_scope()
        assert scope is not None
        assert scope.game_id == game_id
        assert scope.expected_generation == 4
    assert current_game_storage_scope() is None


@pytest.mark.parametrize(
    ("status", "available"),
    [
        (GameStorageStatus.ACTIVE, True),
        (GameStorageStatus.MIGRATING, False),
        (GameStorageStatus.DELETING, False),
        (GameStorageStatus.BLOCKED, False),
    ],
)
def test_write_availability_follows_registry_status(
    status: GameStorageStatus, available: bool
) -> None:
    location = GameStorageLocation(
        game_id=UUID(int=1),
        store_schema=GameStorageSchema.V2,
        generation=2,
        manifest_version=VERSION,
        status=status,
        revision=1,
    )
    assert location.write_available is available
