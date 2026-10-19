from uuid import uuid4

import pytest
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage import create_database_engine, create_session_factory
from game_predictor_api.storage.database import GameStorageSession, _pending_game_id
from game_predictor_api.storage.models import BoardSearchShareSessionModel, SymbolModel
from sqlalchemy import create_engine


def test_database_engine_uses_psycopg_without_opening_connection() -> None:
    settings = ApiSettings.from_environment({})

    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.host == "127.0.0.1"
        assert engine.pool._pre_ping is True
        assert session_factory.kw["expire_on_commit"] is False
    finally:
        engine.dispose()


def test_multi_game_share_metadata_does_not_bind_a_game_store() -> None:
    with GameStorageSession(create_engine("sqlite://")) as session:
        session.add_all([BoardSearchShareSessionModel(game_id=uuid4()) for _ in range(3)])
        assert _pending_game_id(session) is None


def test_share_metadata_does_not_override_actual_game_data_routing() -> None:
    game_id = uuid4()
    with GameStorageSession(create_engine("sqlite://")) as session:
        session.add_all(
            [BoardSearchShareSessionModel(game_id=uuid4()), SymbolModel(game_id=game_id)]
        )
        assert _pending_game_id(session) == game_id


def test_multiple_actual_game_stores_remain_forbidden() -> None:
    with GameStorageSession(create_engine("sqlite://")) as session:
        session.add_all([SymbolModel(game_id=uuid4()) for _ in range(2)])
        with pytest.raises(RuntimeError, match="cannot mutate multiple game stores"):
            _pending_game_id(session)
