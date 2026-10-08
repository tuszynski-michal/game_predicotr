"""Real app-role capability persistence, rollback, public scope and code-failure commits."""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from fastapi.testclient import TestClient
from game_predictor_api.application.management_access import ManagementAccessService
from game_predictor_api.application.management_ingress import stop_unused_shared_ingress
from game_predictor_api.application.management_public import ManagementPublicGuard
from game_predictor_api.domain.management import (
    ManagementAssignmentCommand,
    ManagementError,
    ManagementMachineCommand,
    ManagementPointCommand,
)
from game_predictor_api.domain.management_sessions import ManagementAccessError
from game_predictor_api.domain.management_stakes import ManagementClearCommand
from game_predictor_api.main import create_app
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.management_models import (
    ManagementJournalModel,
    ManagementOperationModel,
    ManagementPointModel,
)
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
from game_predictor_api.storage.management_session_models import ManagementSessionAuditModel
from game_predictor_api.storage.management_session_repository import (
    SqlAlchemyManagementSessionRepository,
)
from game_predictor_api.storage.management_stake_models import ManagementSearchContextModel
from game_predictor_api.storage.management_stake_repository import (
    SqlAlchemyManagementStakeRepository,
)
from game_predictor_api.storage.models import GameModel
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Requires disposable PostgreSQL.",
)


@contextmanager
def public_client(settings):
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.state.database_engine.dispose()


def test_real_public_sessions_durability_scope_and_atomic_expiry(tmp_path):
    with application_role_database("t5management", ("attached", "other")) as db:
        game, other = db.games["attached"], db.games["other"]
        with Session(db.owner_engine) as session, session.begin():
            for game_id in (game, other):
                session.get(GameModel, game_id).status = "active"
        with Session(db.app_engine) as session, session.begin():
            metadata = SqlAlchemyManagementRepository(session)
            point = metadata.point(
                None,
                ManagementPointCommand(
                    operationId=uuid4(),
                    expectedRevision=0,
                    name="Point",
                    city="City",
                    street="Street",
                ),
                "local-owner",
            )
            machine = metadata.machine(
                point.id,
                None,
                ManagementMachineCommand(operationId=uuid4(), expectedRevision=0, name="Machine"),
                "local-owner",
            )
            machine = metadata.assignments(
                machine.id,
                ManagementAssignmentCommand(
                    operationId=uuid4(), expectedRevision=machine.revision, gameIds=[game]
                ),
                "local-owner",
            )
            access = ManagementAccessService(SqlAlchemyManagementSessionRepository(session))
            record, code = access.create("Same recipient", 4320)
            second, second_code = access.create("Same recipient", 480)

        headers = {
            "X-Management-Public-Proxy": "reviewer-management-v1",
            "X-Management-Session": str(record.id),
        }
        with public_client(db.settings(tmp_path)) as client:
            unlock = client.post(
                f"/api/v1/management-public/sessions/{record.id}/unlock",
                json={"accessCode": code},
                headers=headers,
            )
            assert unlock.status_code == 200, unlock.text
            assert "accessCode" not in unlock.json()
            token = unlock.cookies["gp_management_token"]
            headers["Cookie"] = f"gp_management_token={token}"
            assert client.get("/api/v1/management-public", headers=headers).status_code == 200
            assert (
                client.get(
                    "/api/v1/management-public",
                    headers={**headers, "X-Management-Session": str(second.id)},
                ).status_code
                == 401
            )
            old_only = {key: value for key, value in headers.items() if key != "Cookie"}
            old_only["Cookie"] = f"gp_board_search_token={token}"
            assert client.get("/api/v1/management-public", headers=old_only).status_code == 401
            forged = f"/api/v1/management-public/machines/{machine.id}/game/{other}/symbols"
            assert client.get(forged, headers=headers).status_code == 404
            assert (
                client.get(
                    f"/api/v1/management-public/machines/{machine.id}/journal?gameId={other}",
                    headers=headers,
                ).status_code
                == 404
            )
            body = {
                "operationId": str(uuid4()),
                "expectedRevision": 0,
                "name": "Remote point",
                "city": "City",
                "street": "Street",
            }
            first = client.post("/api/v1/management-public/points", json=body, headers=headers)
            assert first.status_code == 200, first.text
            assert (
                client.post("/api/v1/management-public/points", json=body, headers=headers).json()
                == first.json()
            )
            assert (
                client.get("/api/v1/management-public/sessions", headers=headers).status_code == 404
            )

            other_unlock = client.post(
                f"/api/v1/management-public/sessions/{second.id}/unlock",
                json={"accessCode": second_code},
                headers=headers,
            )
            other_headers = {
                **headers,
                "X-Management-Session": str(second.id),
                "Cookie": f"gp_management_token={other_unlock.cookies['gp_management_token']}",
            }
            conflict = client.post(
                "/api/v1/management-public/points", json=body, headers=other_headers
            )
            assert (
                conflict.status_code == 409
                and conflict.json()["code"] == "MANAGEMENT_OPERATION_CONFLICT"
            )

            # Failed codes must commit through the actual FastAPI error dependency.
            for _attempt in range(5):
                response = client.post(
                    f"/api/v1/management-public/sessions/{second.id}/unlock",
                    json={"accessCode": "wrong"},
                    headers=headers,
                )
                assert response.status_code == 401
            with Session(db.app_engine) as fresh:
                persisted = SqlAlchemyManagementSessionRepository(fresh).get(second.id)
                assert persisted.failed_attempts == 5 and persisted.locked_at is not None
                assert (
                    fresh.scalar(
                        select(func.count(ManagementSessionAuditModel.id)).where(
                            ManagementSessionAuditModel.session_id == second.id
                        )
                    )
                    == 7
                )

        # A fresh database session reads the persisted capability; expiry occurs during final flush.
        clock = [datetime.now(UTC)]
        with Session(db.app_engine) as session:
            access = ManagementAccessService(
                SqlAlchemyManagementSessionRepository(session), now=lambda: clock[0]
            )
            guard = ManagementPublicGuard(session, access, token, record.id)
            operation = uuid4()
            SqlAlchemyManagementRepository(session).point(
                None,
                ManagementPointCommand(
                    operationId=operation,
                    expectedRevision=0,
                    name="Rolled back",
                    city="City",
                    street="Street",
                ),
                guard.context.actor,
            )

            def expire_during_final_flush(*_args):
                clock[0] = record.expires_at

            session.get(ManagementPointModel, point.id).name = "Pending expiry flush"
            event.listen(session, "after_flush", expire_during_final_flush, once=True)
            with pytest.raises(ManagementAccessError):
                guard.before_commit()
            session.rollback()
        with Session(db.app_engine) as fresh:
            assert fresh.get(ManagementOperationModel, operation) is None
            assert (
                fresh.scalar(
                    select(ManagementPointModel.id).where(
                        ManagementPointModel.name == "Rolled back"
                    )
                )
                is None
            )
            assert (
                fresh.scalar(
                    select(ManagementJournalModel.id).where(
                        ManagementJournalModel.operation_id == operation
                    )
                )
                is None
            )

        # The same commit guard covers T2, without stale-success or receipt leakage.
        factory = create_session_factory(db.app_engine)
        clock[0] = datetime.now(UTC)
        with factory() as session:
            guard = ManagementPublicGuard(
                session,
                ManagementAccessService(
                    SqlAlchemyManagementSessionRepository(session), now=lambda: clock[0]
                ),
                token,
                record.id,
            )
            repository = SqlAlchemyManagementStakeRepository(session, revalidate=guard.revalidate)
            operation = uuid4()
            repository.clear(
                machine.id,
                game,
                120,
                ManagementClearCommand(operationId=operation, expectedRevision=0, confirmed=True),
                guard.context.actor,
            )
            clock[0] = record.expires_at
            with pytest.raises(ManagementAccessError):
                repository.before_commit()
            session.rollback()
        with Session(db.app_engine) as fresh:
            assert fresh.get(ManagementOperationModel, operation) is None

        # Same human label never gives a second link an unsaved search context.
        context_id = __import__("uuid").UUID(body["operationId"])
        with Session(db.app_engine) as session, session.begin():
            session.add(
                ManagementSearchContextModel(
                    id=context_id,
                    machine_id=machine.id,
                    game_id=game,
                    stake_grosze=120,
                    actor=record.actor,
                    query={},
                    sequence_numbers=[],
                )
            )
        with (
            factory() as session,
            pytest.raises(ManagementError, match="own validated search context"),
        ):
            SqlAlchemyManagementStakeRepository(session)._context(
                context_id, machine.id, game, 120, second.actor
            )

        # No real ingress is touched. A retained link prevents the old last-close stop.
        class FakeIngress:
            def __init__(self):
                self.stopped = []
                self.instance = uuid4()

            def status(self):
                return SimpleNamespace(instance_id=self.instance)

            def stop_if_current(self, instance):
                self.stopped.append(instance)

        ingress = FakeIngress()
        stop_unused_shared_ingress(db.app_engine, ingress)
        assert not ingress.stopped
        # Revoke and rotate own the row first. A waiting mutation rechecks the new
        # committed state and cannot write its point/receipt after invalidation.
        for change in ("revoke", "rotate"):
            with Session(db.app_engine) as session, session.begin():
                access = ManagementAccessService(SqlAlchemyManagementSessionRepository(session))
                race_record, race_code = access.create("Race", 480)
                _, race_token = access.unlock(race_record.id, race_code)
            operation = uuid4()
            locked, release, started = Event(), Event(), Event()
            with ThreadPoolExecutor(max_workers=2) as pool:

                def invalidate(
                    change=change,
                    race_record=race_record,
                    race_code=race_code,
                    locked=locked,
                    release=release,
                ):
                    with Session(db.app_engine) as session, session.begin():
                        access = ManagementAccessService(
                            SqlAlchemyManagementSessionRepository(session)
                        )
                        if change == "revoke":
                            access.revoke(race_record.id)
                        else:
                            access.unlock(race_record.id, race_code)
                        locked.set()
                        assert release.wait(5)

                def mutate(
                    started=started,
                    race_token=race_token,
                    race_record=race_record,
                    operation=operation,
                ):
                    with Session(db.app_engine) as session, session.begin():
                        started.set()
                        guard = ManagementPublicGuard(
                            session,
                            ManagementAccessService(SqlAlchemyManagementSessionRepository(session)),
                            race_token,
                            race_record.id,
                        )
                        SqlAlchemyManagementRepository(session).point(
                            None,
                            ManagementPointCommand(
                                operationId=operation,
                                expectedRevision=0,
                                name="Forbidden race",
                                city="City",
                                street="Street",
                            ),
                            guard.context.actor,
                        )
                        guard.before_commit()

                invalidating = pool.submit(invalidate)
                assert locked.wait(5)
                mutation = pool.submit(mutate)
                assert started.wait(5)
                release.set()
                invalidating.result(10)
                with pytest.raises(ManagementAccessError):
                    mutation.result(10)
            with Session(db.app_engine) as fresh:
                assert fresh.get(ManagementOperationModel, operation) is None
                assert (
                    fresh.scalar(
                        select(ManagementPointModel.id).where(
                            ManagementPointModel.name == "Forbidden race"
                        )
                    )
                    is None
                )

        with Session(db.app_engine) as session, session.begin():
            ManagementAccessService(SqlAlchemyManagementSessionRepository(session)).revoke(
                race_record.id
            )

        with Session(db.app_engine) as session, session.begin():
            SqlAlchemyManagementRepository(session).assignments(
                machine.id,
                ManagementAssignmentCommand(
                    operationId=uuid4(), expectedRevision=machine.revision, gameIds=[]
                ),
                "local-owner",
            )
        with public_client(db.settings(tmp_path)) as client:
            base = f"/api/v1/management-public/machines/{machine.id}/game/{game}"
            assert client.get(base + "/stakes", headers=headers).status_code == 200
            assert client.get(base + "/symbols", headers=headers).status_code == 409
            assert (
                client.get(
                    f"/api/v1/management-public/machines/{machine.id}/journal?gameId={game}",
                    headers=headers,
                ).status_code
                == 200
            )
        with Session(db.app_engine) as session, session.begin():
            ManagementAccessService(SqlAlchemyManagementSessionRepository(session)).revoke(
                record.id
            )
        with public_client(db.settings(tmp_path)) as client:
            assert client.get("/api/v1/management-public", headers=headers).status_code == 401
        with ThreadPoolExecutor(max_workers=2) as pool:
            locked = Event()
            release = Event()
            started = Event()

            def create_while_closing():
                with Session(db.app_engine) as session, session.begin():
                    access = ManagementAccessService(SqlAlchemyManagementSessionRepository(session))
                    access.lock_ingress()
                    retained, _ = access.create("Concurrent retained", 480)
                    locked.set()
                    assert release.wait(5)
                    return retained

            def close_old():
                started.set()
                stop_unused_shared_ingress(db.app_engine, ingress)

            creation = pool.submit(create_while_closing)
            assert locked.wait(5)
            closing = pool.submit(close_old)
            assert started.wait(5)
            deadline = time.monotonic() + 2
            with db.app_engine.connect() as connection:
                while not connection.scalar(
                    text("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND NOT granted")
                ):
                    assert time.monotonic() < deadline, "closing must wait on creation ingress lock"
                    time.sleep(0.01)
            release.set()
            retained = creation.result(10)
            closing.result(10)
        assert not ingress.stopped

        with Session(db.app_engine) as session, session.begin():
            ManagementAccessService(SqlAlchemyManagementSessionRepository(session)).revoke(
                retained.id
            )
        stop_unused_shared_ingress(db.app_engine, ingress)
        assert ingress.stopped == [ingress.instance]
