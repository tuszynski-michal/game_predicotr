"""Control-plane retention, conflict, response-loss and fresh-engine regressions."""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.management import create_management_router
from game_predictor_api.api.management_public import require_management_proxy
from game_predictor_api.application.management import ManagementError, ManagementService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.management import (
    ManagementAssignmentCommand,
    ManagementMachineCommand,
    ManagementPointCommand,
)
from game_predictor_api.domain.management_sessions import (
    MANAGEMENT_PROXY_HEADER,
    MANAGEMENT_PROXY_INTENT,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.management_models import (
    ManagementAssignmentModel,
    ManagementJournalModel,
    ManagementMachineModel,
    ManagementMutationPreviewModel,
    ManagementOperationModel,
    ManagementPointModel,
)
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
from game_predictor_api.storage.management_stake_models import (
    ManagementResultVersionModel,
    ManagementSearchContextModel,
    ManagementStakeSlotModel,
)
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
    ManagementMutationPreviewModel.__table__,
    ManagementResultVersionModel.__table__,
    ManagementSearchContextModel.__table__,
    ManagementStakeSlotModel.__table__,
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
        with pytest.raises(ManagementError) as denied:
            repo.assignments(
                machine_id,
                ManagementAssignmentCommand(
                    operation_id=uuid4(), expected_revision=retained.revision, game_ids=[]
                ),
                "local-owner",
            )
        assert denied.value.code == "MANAGEMENT_PREVIEW_REQUIRED"
        session.rollback()
        # Compatibility with previously detached data remains; structural
        # hard-delete is tested with real PostgreSQL immutable triggers.
        session.get(ManagementAssignmentModel, (machine_id, game_id)).attached = False
        session.commit()
        detached = repo.snapshot().points[0].machines[0]
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


@pytest.fixture(params=["admin", "public"])
def mutation_http(database, tmp_path, request):
    """Production routers, error mapping and middleware; isolated metadata only."""
    with Session(database) as session, session.begin():
        repo = SqlAlchemyManagementRepository(session)
        point = repo.point(None, point_command(), "local-owner")
        other = repo.point(None, point_command(), "local-owner")
        game = GameModel(code="http-active", name="Active", status=GameStatus.ACTIVE)
        session.add(game)
        session.flush()
        game_id = game.id
        machine = repo.machine(
            point.id,
            None,
            ManagementMachineCommand(
                operation_id=uuid4(), expected_revision=0, name="Machine", game_ids=[game_id]
            ),
            "local-owner",
        )
    completed = []

    def local_dependency():
        with Session(database) as session, session.begin():
            yield ManagementService(SqlAlchemyManagementRepository(session))
        completed.append("commit")

    app = create_app(
        ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://127.0.0.1:3000",
            artifact_root=tmp_path,
            import_root=tmp_path,
        ),
        management_service_dependency=local_dependency,
    )
    routes = [
        child
        for route in app.routes
        for child in getattr(getattr(route, "original_router", None), "routes", [route])
    ]
    public_route = next(
        route
        for route in routes
        if getattr(route, "path", "")
        == "/api/v1/management-public/points/{point_id}/delete-preview"
    )
    guard_dependency = public_route.dependant.dependencies[0].dependencies[0].call
    actor = f"management-share:{uuid4()}:Recipient"

    def public_guard(_proxy: Annotated[None, Depends(require_management_proxy)]):
        # Replace capability authentication, preserving the real proxy gate and
        # production structure dependency's actor/session wiring.
        with Session(database) as session, session.begin():
            yield SimpleNamespace(session=session, context=SimpleNamespace(actor=actor))
        completed.append("commit")

    app.dependency_overrides[guard_dependency] = public_guard
    public = request.param == "public"
    prefix = "/api/v1/management-public" if public else "/api/v1/admin/management"
    headers = (
        {MANAGEMENT_PROXY_HEADER: MANAGEMENT_PROXY_INTENT}
        if public
        else {"X-Admin-Intent": "local-owner"}
    )
    try:
        with TestClient(app, client=("127.0.0.1", 43210), headers=headers) as client:
            yield client, prefix, point, machine, other, game_id, completed
    finally:
        app.state.database_engine.dispose()


def test_mutation_http_previews_commit_and_preserve_secret_boundary(
    mutation_http, database, tmp_path
):
    client, base, point, machine, _, _, completed = mutation_http
    tokens = []
    for path, revision in (
        (f"/points/{point.id}", point.revision),
        (f"/points/{point.id}/machines/{machine.id}", machine.revision),
    ):
        response = client.post(f"{base}{path}/delete-preview", json={"expectedRevision": revision})
        assert response.status_code == 200, response.text
        preview = response.json()
        assert len(preview["previewToken"]) == 43
        assert preview["expiresAt"]
        assert preview["counts"]["machines"] == 1
        assert preview["counts"]["assignments"] == 1
        tokens.append(preview["previewToken"])
    for command in (
        {"operationId": str(uuid4()), "expectedRevision": machine.revision, "gameIds": []},
        {
            "operationId": str(uuid4()),
            "expectedRevision": machine.revision,
            "name": "New name",
            "gameIds": [],
        },
    ):
        response = client.post(
            f"{base}/machines/{machine.id}/update-preview", json={"command": command}
        )
        assert response.status_code == 200, response.text
        assert response.json()["counts"]["assignments"] == 1
        tokens.append(response.json()["previewToken"])
    assert completed == ["commit"] * 4
    with Session(database) as session:
        previews = session.scalars(select(ManagementMutationPreviewModel)).all()
        assert len(previews) == 4
        if "management-public" in base:
            assert all(item.actor.startswith("management-share:") for item in previews)
        else:
            assert all(item.actor == "local-owner" for item in previews)
        stored = repr([item.response for item in session.scalars(select(ManagementOperationModel))])
        stored += repr([item.after for item in session.scalars(select(ManagementJournalModel))])
        stored += repr([item.token_sha256 for item in previews])
        assert all(token not in stored for token in tokens)
    log = tmp_path / "admin-audit" / "local-admin-events.jsonl"
    if log.exists():
        assert all(token not in log.read_text(encoding="utf-8") for token in tokens)


def test_mutation_http_validation_and_scope_errors_leave_data_intact(mutation_http, database):
    client, base, point, machine, other, game_id, _ = mutation_http
    update_path = f"{base}/machines/{machine.id}/update-preview"
    missing_games = client.post(
        update_path,
        json={
            "command": {
                "operationId": str(uuid4()),
                "expectedRevision": machine.revision,
                "name": "Name",
            }
        },
    )
    assert missing_games.status_code == 422
    assert missing_games.json()["code"] == "MANAGEMENT_PREVIEW_INVALID"
    malformed = client.post(update_path, json={"command": {"expectedRevision": machine.revision}})
    assert malformed.status_code == 422
    missing = client.post(
        f"{base}/machines/{uuid4()}/update-preview",
        json={"command": {"operationId": str(uuid4()), "expectedRevision": 1, "gameIds": []}},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "MANAGEMENT_MACHINE_NOT_FOUND"
    wrong_point = client.post(
        f"{base}/points/{other.id}/machines/{machine.id}/delete-preview",
        json={"expectedRevision": machine.revision},
    )
    assert wrong_point.status_code == 404
    assert wrong_point.json()["code"] == "MANAGEMENT_MACHINE_NOT_FOUND"
    detach = client.put(
        f"{base}/machines/{machine.id}/assignments",
        json={"operationId": str(uuid4()), "expectedRevision": machine.revision, "gameIds": []},
    )
    assert detach.status_code == 409
    assert detach.json()["code"] == "MANAGEMENT_PREVIEW_REQUIRED"
    for scope, revision in (
        (f"/points/{point.id}", point.revision),
        (f"/points/{point.id}/machines/{machine.id}", machine.revision),
    ):
        command = {
            "operationId": str(uuid4()),
            "expectedRevision": revision,
            "previewToken": "x" * 43,
            "confirmed": False,
        }
        unconfirmed = client.post(f"{base}{scope}/delete", json=command)
        assert unconfirmed.status_code == 422
        required = client.post(f"{base}{scope}/delete", json={**command, "confirmed": True})
        assert required.status_code == 409
        assert required.json()["code"] == "MANAGEMENT_PREVIEW_INVALID"
        preview = client.post(
            f"{base}{scope}/delete-preview", json={"expectedRevision": revision}
        ).json()
        refused = client.post(
            f"{base}{scope}/delete",
            json={**command, "confirmed": True, "previewToken": preview["previewToken"]},
        )
        assert refused.status_code == 503
        assert refused.json()["code"] == "MANAGEMENT_PURGE_REQUIRES_POSTGRESQL"
    with Session(database) as session:
        assert session.get(ManagementMachineModel, machine.id).revision == machine.revision
        assert session.get(ManagementAssignmentModel, (machine.id, game_id)).attached
        assert session.scalar(select(func.count()).select_from(ManagementPointModel)) == 2
        assert session.scalar(select(func.count()).select_from(ManagementOperationModel)) == 3


def test_mutation_http_security_guard_refuses_every_new_route(mutation_http, database):
    client, base, point, machine, _, _, completed = mutation_http
    client.headers.clear()
    for path in (
        f"/points/{point.id}/delete-preview",
        f"/points/{point.id}/delete",
        f"/points/{point.id}/machines/{machine.id}/delete-preview",
        f"/points/{point.id}/machines/{machine.id}/delete",
        f"/machines/{machine.id}/update-preview",
    ):
        denied = client.post(f"{base}{path}", json={})
        assert denied.status_code == 403, denied.text
        assert denied.json()["code"] == (
            "MANAGEMENT_PROXY_REQUIRED" if "management-public" in base else "ADMIN_INTENT_REQUIRED"
        )
    assert completed == []
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(ManagementMutationPreviewModel)) == 0
