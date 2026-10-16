"""TASK-0996: 0165 adds the grid-training job type, slot 3 and lane on a disposable database."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from _application_role_database import ALEMBIC_INI, application_role_database
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)

_INSERT = text(
    """
    INSERT INTO public.jobs (
        id, job_type, game_id, status, input_payload, input_key, progress_current,
        success_count, failure_count, review_count, attempt_count, execution_slot,
        lease_owner, lease_token, lease_expires_at, heartbeat_at, created_at, updated_at
    ) VALUES (
        :id, CAST(:job_type AS job_type), NULL, CAST(:status AS job_status),
        CAST(:payload AS jsonb), :key, 0, 0, 0, 0, 1, :slot,
        :owner, :token, :expires, :beat, now(), now()
    )
    """
)


def _job(connection, job_type: str, slot: int | None, *, status: str = "processing") -> None:
    processing = status == "processing"
    connection.execute(
        _INSERT,
        {
            "id": uuid4(),
            "job_type": job_type,
            "status": status,
            "payload": json.dumps({"schema_version": 1}),
            "key": uuid4().hex,
            "slot": slot,
            "owner": "w" if processing else None,
            "token": uuid4() if processing else None,
            "beat": datetime.now(UTC) if processing else None,
            "expires": datetime.now(UTC) + timedelta(minutes=1) if processing else None,
        },
    )


def test_grid_training_lane_constraints_and_guarded_downgrade() -> None:
    with application_role_database("t0996", ()) as db:
        config = Config(str(ALEMBIC_INI))
        config.set_main_option(
            "sqlalchemy.url",
            db.owner_url.render_as_string(hide_password=False).replace("%", "%%"),
        )
        with db.owner_engine.connect() as connection:
            labels = connection.scalars(
                text("SELECT unnest(enum_range(NULL::job_type))::text")
            ).all()
            assert "grid_training" in labels
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0165_grid_training_lane"
            )
        with db.owner_engine.begin() as connection:
            connection.execute(text("DELETE FROM public.jobs WHERE execution_slot = 3"))
        for job_type, slot, accepted in (
            ("grid_training", 3, True),
            ("grid_training", 1, False),
            ("import", 3, False),
        ):
            try:
                with db.owner_engine.begin() as connection:
                    _job(connection, job_type, slot)
                    connection.execute(
                        text("DELETE FROM public.jobs WHERE execution_slot = :s"), {"s": slot}
                    )
                assert accepted, (job_type, slot)
            except IntegrityError as error:
                assert not accepted, (job_type, slot)
                assert "ck_jobs_processing_lease_fields" in str(error.orig)
        with db.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.worker_lane_runtime (lane, instance_token, worker_id, "
                    "worker_version, process_id, thread_budget, started_at, heartbeat_at) "
                    "VALUES ('grid_training', :token, 'w', 'v', 1, 1, now(), now())"
                ),
                {"token": uuid4()},
            )
        with pytest.raises(DBAPIError, match="GRID_TRAINING_LANE_DOWNGRADE_HAS_HISTORY"):
            command.downgrade(config, "0164_merge_main_board_search_panels")
        with db.owner_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM public.worker_lane_runtime WHERE lane = 'grid_training'")
            )
            _job(connection, "grid_training", None, status="created")
        with pytest.raises(DBAPIError, match="GRID_TRAINING_LANE_DOWNGRADE_HAS_HISTORY"):
            command.downgrade(config, "0164_merge_main_board_search_panels")
        with db.owner_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM public.jobs WHERE job_type::text = 'grid_training'")
            )
        command.downgrade(config, "0164_merge_main_board_search_panels")
        with db.owner_engine.begin() as connection, pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO public.worker_lane_runtime (lane, instance_token, worker_id, "
                    "worker_version, process_id, thread_budget, started_at, heartbeat_at) "
                    "VALUES ('grid_training', :token, 'w', 'v', 1, 1, now(), now())"
                ),
                {"token": uuid4()},
            )
        command.upgrade(config, "head")
        with db.owner_engine.begin() as connection:
            _job(connection, "grid_training", 3)


def test_run_idempotency_key_is_found_exactly_and_serialized() -> None:
    from game_predictor_api.domain.jobs import JobType, create_job
    from game_predictor_api.storage.database import create_session_factory
    from game_predictor_api.storage.game_storage_routing import game_storage_scope
    from game_predictor_api.storage.grid_training_run_jobs import SqlAlchemyGridTrainingRunJobs
    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool

    with application_role_database("t0996key", ("runs",)) as db:
        engine = create_engine(db.app_url, poolclass=NullPool)
        factory = create_session_factory(engine)
        game = db.games["runs"]
        key = uuid4()
        job = create_job(
            JobType.GRID_TRAINING,
            game_id=game,
            input_payload={
                "schema_version": 1,
                "training_kind": "grid-training-run-v1",
                "idempotency_key": str(key),
            },
        )
        with game_storage_scope(game), factory.begin() as session:
            SqlAlchemyGridTrainingRunJobs(session).add_job(job)
        with game_storage_scope(game), factory() as session:
            repository = SqlAlchemyGridTrainingRunJobs(session)
            found = repository.find_by_idempotency(key)
            assert found is not None and found.id == job.id
            assert repository.find_by_idempotency(uuid4()) is None
        with game_storage_scope(game), factory.begin() as first, factory.begin() as second:
            SqlAlchemyGridTrainingRunJobs(first).lock_idempotency(key)
            second.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(OperationalError, match="lock timeout"):
                SqlAlchemyGridTrainingRunJobs(second).lock_idempotency(key)
        engine.dispose()


def test_worker_checkpoint_can_keep_a_cancel_pending_until_the_child_stops() -> None:
    from game_predictor_api.domain.jobs import (
        JobExecutionSlot,
        JobStatus,
        JobType,
        create_job,
        request_job_cancellation,
    )
    from game_predictor_api.storage.database import create_session_factory
    from game_predictor_api.storage.game_storage_routing import game_storage_scope
    from game_predictor_api.storage.job_repository import (
        apply_job_to_record,
        job_from_record,
        job_record_from_domain,
    )
    from game_predictor_api.storage.models import JobModel
    from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    with application_role_database("t0996ack", ("ack",)) as db:
        engine = create_engine(db.app_url, poolclass=NullPool)
        factory = create_session_factory(engine)
        game = db.games["ack"]
        job = create_job(
            JobType.GRID_TRAINING,
            game_id=game,
            input_payload={"schema_version": 1, "training_kind": "grid-training-run-v1"},
        )
        with game_storage_scope(game), factory.begin() as session:
            session.add(job_record_from_domain(job))
        store = SqlAlchemyWorkerJobStore(factory)
        with game_storage_scope(game):
            claimed = store.claim_next(
                worker_id="w",
                worker_version="v",
                lease_duration=timedelta(minutes=1),
                claimed_at=datetime.now(UTC),
                allowed_job_types=frozenset({JobType.GRID_TRAINING}),
                execution_slot=JobExecutionSlot.GRID_TRAINING,
            )
            assert claimed is not None and claimed.lease_token is not None
            with factory.begin() as session:
                record = session.get(JobModel, job.id)
                apply_job_to_record(record, request_job_cancellation(job_from_record(record)))

            def checkpoint(acknowledge: bool):
                return store.checkpoint(
                    job.id,
                    lease_token=claimed.lease_token,
                    lease_duration=timedelta(minutes=1),
                    checkpoint_payload={"schema_version": 1},
                    stage="training",
                    current=1,
                    total=2,
                    success_count=0,
                    failure_count=0,
                    review_count=0,
                    checkpointed_at=datetime.now(UTC),
                    acknowledge_cancellation=acknowledge,
                )

            pending = checkpoint(False)
            assert pending.status is JobStatus.PROCESSING
            assert pending.cancel_requested_at is not None
            assert checkpoint(True).status is JobStatus.CANCELLED
        engine.dispose()
