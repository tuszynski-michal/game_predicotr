"""Exact-owned PostgreSQL proof of freeze selection and retained row locks."""

import os
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.grid_training_cohort_freeze import _lock_inputs
from game_predictor_api.domain.grid_correction_policy import CORRECTION_POLICY
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortMemberModel,
    GridTrainingCohortModel,
)
from game_predictor_api.storage.grid_training_cohort_repository import (
    CohortDeadline,
    SqlAlchemyGridTrainingCohortRepository,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_grid_training_cohort_e2e_postgres import _save_source

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)

TABLES = {
    "recognized_boards": "board_ids",
    "image_review_items": "review_ids",
    "image_symbol_review_cells": "cell_ids",
}


def _identities(db, game, source, job):
    with Session(db.app_engine) as session:
        GameStorageRouter().bind(session, game, intent=GameStorageIntent.READ)
        return {
            table: list(
                session.scalars(
                    text(
                        f"SELECT id FROM {table} WHERE game_id=:g AND "
                        + (
                            "source_image_id=:s"
                            if table == "recognized_boards"
                            else "import_job_id=:j"
                        )
                        + " ORDER BY id"
                    ),
                    {"g": game, "s": source, "j": job},
                )
            )
            for table in TABLES
        }


def _assert_lock(session, table, game, identifier, *, blocked):
    if blocked:
        with pytest.raises(DBAPIError) as error, session.begin_nested():
            session.execute(
                text(f"SELECT id FROM {table} WHERE game_id=:g AND id=:id FOR UPDATE NOWAIT"),
                {"g": game, "id": identifier},
            ).one()
        assert error.value.orig.sqlstate == "55P03"
    else:
        with session.begin_nested():
            assert (
                session.scalar(
                    text(f"SELECT id FROM {table} WHERE game_id=:g AND id=:id FOR UPDATE NOWAIT"),
                    {"g": game, "id": identifier},
                )
                == identifier
            )


def test_freeze_locks_only_deduplicated_used_member_targets(tmp_path, monkeypatch):
    with application_role_database("t1135", ("freeze-a", "freeze-b")) as db:
        game, foreign = db.games.values()
        selected_source, _, selected_job = _save_source(db, tmp_path, game, 1, 2, {})
        unused_source, _, unused_job = _save_source(db, tmp_path, game, 2, 1, {})
        foreign_source, _, foreign_job = _save_source(db, tmp_path, foreign, 3, 1, {})
        selected = _identities(db, game, selected_source, selected_job)
        unused = _identities(db, game, unused_source, unused_job)
        elsewhere = _identities(db, foreign, foreign_source, foreign_job)
        assert {table: len(ids) for table, ids in selected.items()} == {
            "recognized_boards": 2,
            "image_review_items": 2,
            "image_symbol_review_cells": 30,
        }
        cohort, other_cohort = uuid4(), uuid4()
        with Session(db.owner_engine) as owner, owner.begin():
            GameStorageRouter().bind(owner, game, intent=GameStorageIntent.WRITE)
            owner.add_all(
                GridTrainingCohortModel(
                    game_id=game,
                    id=identifier,
                    status="preparing",
                    document={"policyVersion": CORRECTION_POLICY},
                    summary={},
                    created_by="fixture:1135-metadata",
                )
                for identifier in (cohort, other_cohort)
            )
            owner.flush()

            def member(identifier, source, ordinal, used, targets):
                return GridTrainingCohortMemberModel(
                    game_id=game,
                    cohort_id=identifier,
                    source_id=source,
                    ordinal=ordinal,
                    role="TRAIN",
                    frozen={"used": used},
                    **{column: targets[table] for table, column in TABLES.items()},
                )

            # A dangling retained identity is valid metadata. It does not claim a
            # human label; this test exercises row selection, not eligibility.
            mixed = {
                table: list(reversed(ids)) + ids[:1] + elsewhere[table]
                for table, ids in selected.items()
            }
            owner.add_all(
                [
                    member(cohort, selected_source, 0, True, mixed),
                    member(cohort, uuid4(), 1, True, selected),
                    member(cohort, unused_source, 2, False, unused),
                    member(other_cohort, unused_source, 0, True, unused),
                ]
            )
        observed = {}
        with Session(db.app_engine) as locker:
            repo = SqlAlchemyGridTrainingCohortRepository(locker, tmp_path)
            repo.bind(game, write=True)
            execute = locker.execute

            def trace(statement, *args, **kwargs):
                result = execute(statement, *args, **kwargs)
                sql = str(statement)
                if not sql.startswith("SELECT r.id FROM "):
                    return result
                table = sql.split()[3]

                def rows():
                    observed[table] = []
                    for row in result:
                        observed[table].append(row.id)
                        yield row

                return rows()

            monkeypatch.setattr(locker, "execute", trace)
            _lock_inputs(repo, game, cohort, CohortDeadline())
            assert observed == selected  # Exact set, one row each, ascending UUID.
            with Session(db.app_engine) as probe:
                GameStorageRouter().bind(probe, game, intent=GameStorageIntent.READ)
                for table in TABLES:
                    for identifier in selected[table]:
                        _assert_lock(probe, table, game, identifier, blocked=True)
                    _assert_lock(probe, table, game, unused[table][0], blocked=False)
            with Session(db.app_engine) as probe:
                GameStorageRouter().bind(probe, foreign, intent=GameStorageIntent.READ)
                for table in TABLES:
                    _assert_lock(probe, table, foreign, elsewhere[table][0], blocked=False)
            locker.rollback()
        # New connection sees no retained locks after the transaction ends.
        with Session(db.app_engine) as probe:
            GameStorageRouter().bind(probe, game, intent=GameStorageIntent.READ)
            for table in TABLES:
                _assert_lock(probe, table, game, selected[table][0], blocked=False)
