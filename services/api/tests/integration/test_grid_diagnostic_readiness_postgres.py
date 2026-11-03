"""Real database protections; all fixture writes are in a disposable test database."""

from __future__ import annotations

import os
from uuid import UUID

import pytest
from _application_role_database import application_role_database
from game_predictor_api.storage import grid_diagnostic_readiness as readiness
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL tests only.",
)


@pytest.fixture(scope="module")
def database():
    with application_role_database("t1155readiness", ()) as value:
        with value.owner_engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE public.diagnostic_readiness_probe (value integer)")
            )
        yield value


@pytest.mark.parametrize("failure", ["write", "statement_timeout"])
def test_real_read_only_and_statement_deadline(database, failure, monkeypatch, tmp_path):
    # Isolate transaction protections from cohort/domain setup. Session, engine,
    # listener registration and all SQL below are real, including the failing SQL.
    monkeypatch.setattr(readiness.GameStorageRouter, "bind", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        readiness,
        "SOURCE_SELECTION",
        "SELECT '00000000-0000-0000-0000-000000000001'::uuid AS source_image_id, "
        "1 AS nominal_boards",
    )
    clock = {"now": 0.0}
    monkeypatch.setattr(readiness.time, "monotonic", lambda: clock["now"])

    def capture(reader, *args):
        assert reader.session.scalar(text("SHOW transaction_read_only")) == "on"
        if failure == "write":
            reader.session.execute(text("INSERT INTO public.diagnostic_readiness_probe VALUES (1)"))
        else:
            clock["now"] = 4.95
            reader.session.execute(text("SELECT pg_sleep(0.2)"))
        raise AssertionError("Database protection did not reject the statement")

    monkeypatch.setattr(readiness.GridCohortEvidenceReader, "capture", capture)
    with pytest.raises(DBAPIError) as caught:
        readiness.read_readiness(
            database.owner_engine, UUID(int=10), tmp_path, max_sources=1, timeout_seconds=5
        )
    assert caught.value.orig.sqlstate == ("25006" if failure == "write" else "57014")
    with database.owner_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT count(*) FROM public.diagnostic_readiness_probe")) == 0
        )
