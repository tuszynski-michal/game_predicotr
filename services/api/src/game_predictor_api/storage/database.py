"""Synchronous SQLAlchemy infrastructure for the local Admin API."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.config import ApiSettings


def create_database_engine(settings: ApiSettings, *, echo: bool = False) -> Engine:
    """Create an engine without opening a database connection."""

    return create_engine(
        settings.database_url,
        echo=echo,
        pool_pre_ping=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the transaction boundary used by future repositories."""

    return sessionmaker(bind=engine, expire_on_commit=False)
