from game_predictor_api.config import ApiSettings
from game_predictor_api.storage import create_database_engine, create_session_factory


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
