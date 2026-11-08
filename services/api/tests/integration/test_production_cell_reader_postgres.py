"""Real read-only per-game routing, isolated from the publication transaction."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from _application_role_database import application_role_database
from game_predictor_api.storage.game_storage_routing import GameStorageRouter
from game_predictor_api.storage.production_cell_reference import production_reference_reader
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit task-owned disposable PostgreSQL only",
)


def test_independent_game_readers_leave_catalogue_connection_unbound():
    with application_role_database("t1166reader", ("reader-a", "reader-b")) as db:
        receipt = {
            "database": db.owner_url.database,
            "role": db.role,
            "capabilityRole": db.recording_capability.role,
        }
        Path("artifacts/TASK-1166-reader-owned.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )
        print("T1166 reader: own database migrated", flush=True)
        with (
            db.app_engine.connect() as connection,
            connection.begin(),
            Session(bind=connection) as catalogue,
        ):
            assert catalogue.scalar(text("SELECT current_database()")) == db.owner_url.database
            before = catalogue.scalar(text("SELECT current_setting('game_predictor.game_id',true)"))
            assert GameStorageRouter.bound_game_id(catalogue) is None
            for game in db.games.values():
                with production_reference_reader(catalogue, game) as reader:
                    assert reader.scalar(text("SELECT current_database()")) == db.owner_url.database
                    assert reader.scalar(text("SHOW transaction_read_only")) == "on"
                    assert reader.scalar(
                        text("SELECT current_setting('game_predictor.game_id')")
                    ) == str(game)
                    assert GameStorageRouter.bound_game_id(reader) == game
                    assert (
                        reader.scalar(
                            text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
                        )
                        is False
                    )
                    with pytest.raises(DBAPIError) as denied, reader.begin_nested():
                        reader.execute(
                            text("UPDATE public.games SET name=name WHERE id=:game"), {"game": game}
                        )
                    assert denied.value.orig.sqlstate == "25006"
                assert GameStorageRouter.bound_game_id(catalogue) is None
                assert (
                    catalogue.scalar(text("SELECT current_setting('game_predictor.game_id',true)"))
                    == before
                )
        print("T1166 reader: two isolated readonly scopes verified", flush=True)
        cleanup_env = db.subprocess_environment(
            TEST_DATABASE_URL=db.owner_url.set(database="postgres").render_as_string(
                hide_password=False
            ),
            TEST_DATABASE_NAME=db.owner_url.database,
            TEST_RUNTIME_ROLE=db.role,
            TEST_CAPABILITY_ROLE=db.recording_capability.role,
        )
    # Independent process, explicit maintenance URL and exact owned identifiers only.
    script = """import json,os
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
url=os.environ['TEST_DATABASE_URL']; name=os.environ['TEST_DATABASE_NAME']
assert make_url(url).database=='postgres' and name.startswith('game_predictor_t1166reader_')
engine=create_engine(url,connect_args={'connect_timeout':5})
with engine.connect() as c:
 assert c.scalar(text('SELECT current_database()'))=='postgres'
 result={'database':c.scalar(text('SELECT count(*) FROM pg_database WHERE datname=:n'),{'n':name}),
 'roles':c.scalar(text('SELECT count(*) FROM pg_roles WHERE rolname IN (:r,:o)'),
 {'r':os.environ['TEST_RUNTIME_ROLE'],'o':os.environ['TEST_CAPABILITY_ROLE']})}
 assert result=={'database':0,'roles':0}; print(json.dumps(result))
engine.dispose()
"""
    result = subprocess.run(
        [sys.executable, "-c", script], env=cleanup_env, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    proof = json.loads(result.stdout)
    Path("artifacts/TASK-1166-reader-cleanup.json").write_text(
        json.dumps({**receipt, **proof, "newProcess": True}), encoding="utf-8"
    )
    print("T1166 reader: fresh-process cleanup 0/0", flush=True)
