"""Real app-role migration, atomic history and concurrent exact-retry verification."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.management import (
    ManagementAssignmentCommand,
    ManagementError,
    ManagementMachineCommand,
    ManagementPointCommand,
)
from game_predictor_api.storage.management_models import (
    ManagementJournalModel,
    ManagementPointModel,
)
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 for disposable app-role database tests.",
)


def test_management_migration_application_role_concurrency_and_process_restart() -> None:
    with application_role_database("t0921", ("management-game",)) as db:
        with db.owner_engine.begin() as connection:
            connection.execute(
                text("UPDATE public.games SET status='active' WHERE id=:id"),
                {"id": db.games["management-game"]},
            )
        command = ManagementPointCommand(
            operation_id=uuid4(), expected_revision=0, name="Punkt", city="Miasto", street="Ulica 1"
        )

        def create():
            with Session(db.app_engine) as session, session.begin():
                session.execute(text("SET LOCAL statement_timeout=10000"))
                return SqlAlchemyManagementRepository(session).point(None, command, "local-owner")

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = [
                future.result(timeout=20) for future in [pool.submit(create), pool.submit(create)]
            ]
        assert first == second
        with Session(db.app_engine) as session, session.begin():
            repo = SqlAlchemyManagementRepository(session)
            assert session.scalar(select(func.count()).select_from(ManagementPointModel)) == 1
            assert session.scalar(select(func.count()).select_from(ManagementJournalModel)) == 1
            machine = repo.machine(
                first.id,
                None,
                ManagementMachineCommand(operation_id=uuid4(), expected_revision=0, name="Maszyna"),
                "local-owner",
            )
            assigned = repo.assignments(
                machine.id,
                ManagementAssignmentCommand(
                    operation_id=uuid4(),
                    expected_revision=machine.revision,
                    game_ids=[db.games["management-game"]],
                ),
                "local-owner",
            )
            assert assigned.assignments[0].attached
        # Status changes between screen read and mutation are re-read under locks.
        with db.owner_engine.begin() as connection:
            connection.execute(
                text("UPDATE public.games SET status='archived' WHERE id=:id"),
                {"id": db.games["management-game"]},
            )
        with Session(db.app_engine) as session, session.begin():
            repo = SqlAlchemyManagementRepository(session)
            detach = ManagementAssignmentCommand(
                operation_id=uuid4(), expected_revision=assigned.revision, game_ids=[]
            )
            preview = repo.update_preview(machine.id, detach, "local-owner")
            detached = repo.assignments(
                machine.id,
                detach.model_copy(update={"preview_token": preview.preview_token}),
                "local-owner",
            )
        with Session(db.app_engine) as session:
            repo = SqlAlchemyManagementRepository(session)
            with pytest.raises(ManagementError, match="active games"):
                repo.assignments(
                    machine.id,
                    ManagementAssignmentCommand(
                        operation_id=uuid4(),
                        expected_revision=detached.revision,
                        game_ids=[db.games["management-game"]],
                    ),
                    "local-owner",
                )
            session.rollback()
            assert len(repo.snapshot().points) == 1
            with pytest.raises(DBAPIError, match="immutable"):
                session.execute(text("DELETE FROM public.management_journal"))
            session.rollback()

        # Two separate revisions compete; only one update can commit.
        def edit(name: str) -> str:
            try:
                with Session(db.app_engine) as session, session.begin():
                    repo = SqlAlchemyManagementRepository(session)
                    repo.point(
                        first.id,
                        ManagementPointCommand(
                            operation_id=uuid4(),
                            expected_revision=first.revision,
                            name=name,
                            city="Miasto",
                            street="Ulica",
                        ),
                        "local-owner",
                    )
                return "ok"
            except ManagementError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                future.result(timeout=20)
                for future in [pool.submit(edit, "A"), pool.submit(edit, "B")]
            ]
        assert sorted(results) == ["MANAGEMENT_REVISION_CONFLICT", "ok"]
        env = db.subprocess_environment(
            MANAGEMENT_TEST_URL=db.app_url.render_as_string(hide_password=False)
        )
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
engine = create_engine(os.environ["MANAGEMENT_TEST_URL"])
with Session(engine) as session:
    points = SqlAlchemyManagementRepository(session).snapshot().points
    assert len(points) == 1 and points[0].revision == 2
    assert len(points[0].machines) == 1
    assert points[0].machines[0].assignments == []
engine.dispose()
""",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert process.returncode == 0, process.stderr
