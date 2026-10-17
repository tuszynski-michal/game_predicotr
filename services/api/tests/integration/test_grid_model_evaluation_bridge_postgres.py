"""TASK-0997 migration 0166: notice watermark trigger, exact grants and downgrade guard."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from _application_role_database import ALEMBIC_INI, application_role_database, provision_game
from alembic import command
from alembic.config import Config
from game_predictor_api.domain.grid_model_registry import historical_catalogue
from game_predictor_api.storage.database_roles import describe_application_role
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
)
from game_predictor_api.storage.grid_model_evaluation_repository import cohort_currentness
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

MANIFEST = "SELECT manifest_version FROM public.game_storage_locations WHERE game_id=:g"
pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def _config(db) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url", db.owner_url.render_as_string(hide_password=False).replace("%", "%%")
    )
    return config


def _scope(connection, game) -> None:
    connection.execute(
        text("SELECT set_config('game_predictor.game_id', :g, true)"), {"g": str(game)}
    )
    connection.execute(text("SELECT set_config('search_path', 'game_data_v2, public', true)"))


def test_notice_marks_are_trigger_only_and_proofs_are_append_only() -> None:
    with application_role_database("t0997b", ("marks",)) as db:
        game, cohort = db.games["marks"], uuid4()
        config = _config(db)
        with db.owner_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0168_source_crop_runs"
            )
            assert (
                "grid_model_evaluation"
                in connection.scalars(text("SELECT unnest(enum_range(NULL::job_type))::text")).all()
            )
            assert (
                connection.scalar(
                    text(MANIFEST),
                    {"g": game},
                )
                == "game-data-v2-manifest-v19"
            )
            report = describe_application_role(connection, db.role)
            assert report.compliant, report.as_dict()
        # A clean downgrade and upgrade keep the manifest chain intact.
        command.downgrade(config, "0165_grid_training_lane")
        with db.owner_engine.connect() as connection:
            assert (
                connection.scalar(
                    text(MANIFEST),
                    {"g": game},
                )
                == "game-data-v2-manifest-v16"
            )
            assert (
                connection.scalar(
                    text("SELECT to_regclass('public.grid_model_cohort_notice_marks')")
                )
                is None
            )
        command.upgrade(config, "head")
        with db.owner_engine.begin() as connection:
            # Default privileges grant DML to every new table; 0166 itself revokes the
            # watermark writes again, before any provisioning re-run.
            privileges = connection.execute(
                text(
                    "SELECT has_table_privilege(:r,:marks,'INSERT'),"
                    "has_table_privilege(:r,:marks,'SELECT'),"
                    "has_table_privilege(:r,:proofs,'INSERT')"
                ),
                {
                    "r": db.role,
                    "marks": "public.grid_model_cohort_notice_marks",
                    "proofs": "public.grid_model_evaluation_cohort_proofs",
                },
            ).one()
            assert tuple(privileges) == (False, True, True)
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            connection.execute(
                text(
                    "INSERT INTO game_data_v2.grid_training_cohorts"
                    "(game_id,id,status,document,created_by) "
                    "VALUES(:g,:c,'preparing','{}'::jsonb,'fixture-human:0997')"
                ),
                {"g": game, "c": cohort},
            )
            for kind in ("prepared", "currentness_notice", "currentness_notice"):
                connection.execute(
                    text(
                        "INSERT INTO game_data_v2.grid_training_cohort_events"
                        "(game_id,id,cohort_id,kind,document) "
                        "VALUES(:g,:i,:c,:k,'{}'::jsonb)"
                    ),
                    {"g": game, "i": uuid4(), "c": cohort, "k": kind},
                )
        with db.app_engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM public.grid_model_cohort_notice_marks "
                        "WHERE game_id=:g AND cohort_id=:c"
                    ),
                    {"g": game, "c": cohort},
                )
                == 2
            )
        for statement in (
            "INSERT INTO public.grid_model_cohort_notice_marks(game_id,cohort_id) VALUES(:g,:c)",
            "UPDATE public.grid_model_cohort_notice_marks SET cohort_id=:c WHERE game_id=:g",
            "DELETE FROM public.grid_model_cohort_notice_marks WHERE game_id=:g AND cohort_id=:c",
        ):
            with db.app_engine.begin() as connection, pytest.raises(DBAPIError, match="permission"):
                connection.execute(text(statement), {"g": game, "c": cohort})
        report_id, version = uuid4(), historical_catalogue()[0]["versionId"]
        with db.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.grid_model_evaluation_reports"
                    "(id,version_id,producer,report_json,report_sha256) "
                    "VALUES(:i,:v,'server:grid-model-evaluator-v1','{}',:s)"
                ),
                {"i": report_id, "v": version, "s": "a" * 64},
            )
        proof = uuid4()
        with db.app_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.grid_model_evaluation_cohort_proofs(id,report_id,game_id,"
                    "cohort_id,manifest_sha256,notice_count,storage_generation,"
                    "bind_receipt_sha256,eligibility_sha256,actor) "
                    "VALUES(:i,:r,:g,:c,:s,2,2,:s,:s,'server:test')"
                ),
                {"i": proof, "r": report_id, "g": game, "c": cohort, "s": "b" * 64},
            )
        for statement in (
            "UPDATE public.grid_model_evaluation_cohort_proofs SET notice_count=3 WHERE id=:i",
            "DELETE FROM public.grid_model_evaluation_cohort_proofs WHERE id=:i",
        ):
            with db.app_engine.begin() as connection, pytest.raises(DBAPIError):
                connection.execute(text(statement), {"i": proof})
        # A real game deletion drops its partitions without row triggers; the barrier
        # still sees it through the removed shared storage location.
        gone, gone_cohort = provision_game(db.owner_engine, "gone"), uuid4()
        with db.app_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.grid_model_evaluation_cohort_proofs(id,report_id,game_id,"
                    "cohort_id,manifest_sha256,notice_count,storage_generation,"
                    "bind_receipt_sha256,eligibility_sha256,actor) "
                    "VALUES(:i,:r,:g,:c,:s,0,2,:s,:s,'server:test')"
                ),
                {"i": uuid4(), "r": report_id, "g": gone, "c": gone_cohort, "s": "b" * 64},
            )
        pin = [{"gameId": str(gone), "cohortId": str(gone_cohort), "manifestSha256": "b" * 64}]
        with Session(db.app_engine) as session:
            assert [s["state"] for s in cohort_currentness(session, report_id, pin)] == ["current"]
        with Session(db.owner_engine) as session, session.begin():
            operation = (
                GamePartitionLifecycleRepository(session)
                .start_or_resume(game_id=gone, kind=GamePartitionLifecycleKind.DELETE)
                .operation_id
            )
        for _ in range(200):
            with Session(db.owner_engine) as session, session.begin():
                if GamePartitionLifecycleRepository(session).run_next(operation).status == "done":
                    break
        else:
            raise AssertionError("game deletion did not finish")
        with Session(db.app_engine) as session:
            states = cohort_currentness(session, report_id, pin)
        assert [state["state"] for state in states] == ["unavailable"]
        with pytest.raises(DBAPIError, match="GRID_MODEL_EVALUATION_DOWNGRADE_HAS_HISTORY"):
            command.downgrade(config, "0165_grid_training_lane")
