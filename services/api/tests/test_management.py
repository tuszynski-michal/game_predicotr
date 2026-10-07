"""Control-plane retention, conflict, response-loss and fresh-engine regressions."""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.management import create_management_router
from game_predictor_api.application.management import ManagementError, ManagementService
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.management import (
    ManagementAssignmentCommand,
    ManagementMachineCommand,
    ManagementPointCommand,
)
from game_predictor_api.storage.management_models import (
    ManagementAssignmentModel,
    ManagementJournalModel,
    ManagementMachineModel,
    ManagementOperationModel,
    ManagementPointModel,
)
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
from game_predictor_api.storage.models import GameModel
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

TABLES = [
    GameModel.__table__,
    ManagementPointModel.__table__,
    ManagementMachineModel.__table__,
    ManagementAssignmentModel.__table__,
    ManagementOperationModel.__table__,
    ManagementJournalModel.__table__,
]


def point_command(revision: int = 0, **changes: object) -> ManagementPointCommand:
    return ManagementPointCommand.model_validate(
        dict(
            operation_id=uuid4(),
            expected_revision=revision,
            name="Punkt",
            city="Warszawa",
            street="Długa 1",
            **changes,
        )
    )


@pytest.fixture
def database(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'management.sqlite'}",
        execution_options={"schema_translate_map": {"public": None}},
    )
    for table in TABLES:
        table.create(engine)
    yield engine
    engine.dispose()


def test_response_loss_retry_conflict_and_new_engine_persistence(database) -> None:
    command = point_command()
    with Session(database) as session, session.begin():
        repository = SqlAlchemyManagementRepository(session)
        response = repository.point(None, command, "local-owner")
        point_id = response.id
    # A new engine/session sees the same receipt after an unobserved response.
    fresh = create_engine(
        database.url, execution_options={"schema_translate_map": {"public": None}}
    )
    with Session(fresh) as session, session.begin():
        repository = SqlAlchemyManagementRepository(session)
        assert repository.point(None, command, "local-owner") == response
        assert session.scalar(select(func.count()).select_from(ManagementPointModel)) == 1
        assert session.scalar(select(func.count()).select_from(ManagementJournalModel)) == 1
        with pytest.raises(ManagementError, match="already used"):
            repository.point(None, command, "other-actor")
        with pytest.raises(ManagementError, match="already used"):
            repository.point(point_id, command, "local-owner")
        with pytest.raises(ManagementError, match="Refresh"):
            repository.point(point_id, point_command(0), "local-owner")
    fresh.dispose()


def test_assignment_eligibility_detach_archive_restore_and_atomic_rollback(database) -> None:
    with Session(database) as session, session.begin():
        repo = SqlAlchemyManagementRepository(session)
        point = repo.point(None, point_command(), "local-owner")
        machine = repo.machine(
            point.id,
            None,
            ManagementMachineCommand(operation_id=uuid4(), expected_revision=0, name="Maszyna"),
            "local-owner",
        )
        game = GameModel(code="active", name="Aktywna", status=GameStatus.ACTIVE)
        draft = GameModel(code="draft", name="Draft", status=GameStatus.DRAFT)
        session.add_all([game, draft])
        session.flush()
        game_id, draft_id = game.id, draft.id
        machine = repo.assignments(
            machine.id,
            ManagementAssignmentCommand(
                operation_id=uuid4(), expected_revision=machine.revision, game_ids=[game_id]
            ),
            "local-owner",
        )
        machine_id, revision = machine.id, machine.revision
        operation_count = session.scalar(select(func.count()).select_from(ManagementOperationModel))
    with Session(database) as session:
        repo = SqlAlchemyManagementRepository(session)
        with pytest.raises(ManagementError, match="active games"):
            repo.assignments(
                machine_id,
                ManagementAssignmentCommand(
                    operation_id=uuid4(), expected_revision=revision, game_ids=[draft_id]
                ),
                "local-owner",
            )
        session.rollback()
        assert (
            session.scalar(select(func.count()).select_from(ManagementOperationModel))
            == operation_count
        )
        assert session.get(ManagementMachineModel, machine_id).revision == revision
        game = session.get(GameModel, game_id)
        game.status = GameStatus.ARCHIVED
        session.commit()
        # An attached game becoming inactive does not silently detach during unrelated edits.
        retained = repo.assignments(
            machine_id,
            ManagementAssignmentCommand(
                operation_id=uuid4(), expected_revision=revision, game_ids=[game_id]
            ),
            "local-owner",
        )
        session.commit()
        assert retained.assignments[0].attached
        detached = repo.assignments(
            machine_id,
            ManagementAssignmentCommand(
                operation_id=uuid4(), expected_revision=retained.revision, game_ids=[]
            ),
            "local-owner",
        )
        session.commit()
        assert not detached.assignments[0].attached
        with pytest.raises(ManagementError, match="active games"):
            repo.assignments(
                machine_id,
                ManagementAssignmentCommand(
                    operation_id=uuid4(), expected_revision=detached.revision, game_ids=[game_id]
                ),
                "local-owner",
            )
        session.rollback()
        game = session.get(GameModel, game_id)
        game.status = GameStatus.ACTIVE
        session.commit()
        attached = repo.assignments(
            machine_id,
            ManagementAssignmentCommand(
                operation_id=uuid4(), expected_revision=detached.revision, game_ids=[game_id]
            ),
            "local-owner",
        )
        session.commit()
        assert attached.assignments[0].attached
        archived = repo.point(point.id, point_command(point.revision, archived=True), "local-owner")
        session.commit()
        assert repo.snapshot().points[0].machines[0].assignments[0].attached
        with pytest.raises(ManagementError, match="Restore"):
            repo.assignments(
                machine_id,
                ManagementAssignmentCommand(
                    operation_id=uuid4(), expected_revision=attached.revision, game_ids=[]
                ),
                "local-owner",
            )
        session.rollback()
        restored = repo.point(point.id, point_command(archived.revision), "local-owner")
        session.commit()
        assert not restored.archived
        assert session.get(ManagementAssignmentModel, (machine_id, game_id)).attached


def test_blank_fields_and_duplicate_games_rejected() -> None:
    with pytest.raises(ValidationError):
        ManagementPointCommand(
            operation_id=uuid4(), expected_revision=0, name=" ", city="X", street="Y"
        )
    game_id = uuid4()
    with pytest.raises(ValidationError):
        ManagementAssignmentCommand(
            operation_id=uuid4(), expected_revision=1, game_ids=[game_id, game_id]
        )


def test_http_contract_and_commit_precedes_response(database) -> None:
    completed: list[str] = []

    def dependency() -> Iterator[ManagementService]:
        with Session(database) as session:
            yield ManagementService(SqlAlchemyManagementRepository(session))
            session.commit()
            completed.append("commit")

    app = FastAPI()
    app.include_router(create_management_router(dependency))
    with TestClient(app) as client:
        payload = point_command().model_dump(mode="json", by_alias=True)
        response = client.post("/api/v1/admin/management/points", json=payload)
        assert response.status_code == 200
        assert response.json()["name"] == "Punkt"
        assert completed == ["commit"]
        assert (
            client.post("/api/v1/admin/management/points", json=payload).json() == response.json()
        )
        assert len(client.get("/api/v1/admin/management").json()["points"]) == 1

    def failing_dependency() -> Iterator[ManagementService]:
        with Session(database) as session:
            yield ManagementService(SqlAlchemyManagementRepository(session))
            session.rollback()
            raise RuntimeError("commit failed")

    failed = FastAPI()
    failed.include_router(create_management_router(failing_dependency))
    with TestClient(failed, raise_server_exceptions=False) as client:
        assert (
            client.post(
                "/api/v1/admin/management/points",
                json=point_command().model_dump(mode="json", by_alias=True),
            ).status_code
            == 500
        )
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(ManagementPointModel)) == 1
