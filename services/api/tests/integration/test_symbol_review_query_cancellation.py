from __future__ import annotations

import os
import time
from threading import Event, Thread

import pytest
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewQueryRepository,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run PostgreSQL tests.",
)


def test_disconnect_cancel_stops_postgres_and_keeps_the_connection_reusable() -> None:
    engine = create_engine(
        ApiSettings.from_environment().database_url,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
    )
    session = Session(engine)
    repository = SqlAlchemySymbolCellReviewQueryRepository(session)
    query_started = Event()
    query_finished = Event()
    outcome: dict[str, object] = {}

    def run_query() -> None:
        try:
            with repository.bounded_read(timeout_ms=10_000, operation="integration"):
                query_started.set()
                session.execute(text("SELECT pg_sleep(5)"))
        except SymbolCellReviewError as error:
            outcome["error"] = error
        finally:
            session.rollback()
            outcome["reusable"] = session.scalar(text("SELECT 1"))
            query_finished.set()

    worker = Thread(target=run_query, daemon=True)
    started_at = time.monotonic()
    worker.start()
    try:
        assert query_started.wait(timeout=2.0)
        repository.mark_active_read_cancelled()
        while not query_finished.wait(timeout=0.02):
            repository.cancel_active_read()
            assert time.monotonic() - started_at < 3.0
        worker.join(timeout=0.5)

        error = outcome.get("error")
        assert isinstance(error, SymbolCellReviewError)
        assert error.code == "SYMBOL_CELL_REVIEW_QUERY_CANCELLED"
        assert outcome["reusable"] == 1
        assert time.monotonic() - started_at < 3.0
    finally:
        session.close()
        engine.dispose()
