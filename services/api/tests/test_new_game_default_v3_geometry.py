"""Synthetic catalogue transfers: no real games, weights, inference or quality claims."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.new_game_geometry import NewGameGeometryService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration, GameStatus
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    descriptor_sha256,
    validate_manifest,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.game_create_receipts import SqlAlchemyGameCreateReceiptRepository
from game_predictor_api.storage.grid_model_registry_models import (
    GameCreateReceiptModel,
    GameGridModelAssignmentEventModel,
    GameGridModelAssignmentModel,
    GridModelDefaultModel,
    GridModelFamilyForkModel,
    GridModelFamilyModel,
    GridModelVersionModel,
)
from game_predictor_api.storage.models import GameModel, ImageGeometryRolloutStateModel
from sqlalchemy import Column, MetaData, Table, func, select
from sqlalchemy.orm import Session
from test_grid_model_publication_and_activation import execute, registry, seed_report
from test_grid_model_registry import candidate
from test_grid_model_registry import engine as registry_engine  # noqa: F401


@pytest.fixture
def catalog(request, tmp_path):
    engine = request.getfixturevalue("registry_engine").execution_options(
        schema_translate_map={None: "public"}
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE public.games")
        GameModel.__table__.create(connection)
        rollout = ImageGeometryRolloutStateModel.__table__
        Table(
            rollout.name,
            MetaData(),
            *(
                Column(
                    c.name,
                    c.type,
                    nullable=c.nullable,
                    primary_key=c.primary_key,
                    server_default=c.server_default,
                )
                for c in rollout.columns
            ),
            schema="public",
        ).create(connection)

    def service(session):
        repo = SqlAlchemyCatalogRepository(session, artifact_root=tmp_path)
        control = registry(session, tmp_path)
        # Synthetic historical artifact availability; never production weight files.
        creation = NewGameGeometryService(
            repo, SqlAlchemyGameCreateReceiptRepository(session), control
        )
        return repo, control, creation

    return engine, service


def fields(code="new-game", status=GameStatus.DRAFT):
    return dict(
        code=code,
        name="New game",
        status=status,
        expected_layout_count=100,
        shape_geometry_configuration=GameShapeGeometryConfiguration.NEURAL_GRID_V3,
        super_game_kind="none",
    )


def published(session, control, *, default=False):
    version = control.repository.versions()[0]
    execute(control, "publish", str(version.id))
    if default:
        execute(control, "set_default", str(version.id))
    session.commit()
    return version.id


def test_create_default_and_retry_never_reselects_or_rewrites_assignment(catalog):
    engine, service = catalog
    key = uuid4()
    with Session(engine) as session:
        _, control, create = service(session)
        version = published(session, control, default=True)
        game = create.create(
            key=key, fields=fields(status=GameStatus.ACTIVE), selection={"mode": "default"}
        )
        session.commit()
        original = session.scalar(select(GameCreateReceiptModel))
        receipt = json.loads(original.reservation_json)
        assert receipt["assignment"]["transfer"]["qualityScope"] == "source-games-only"
        assert game.status == GameStatus.ACTIVE
        assert session.get(GameGridModelAssignmentModel, game.id).version_id == version
    with Session(engine) as session:
        _, control, create = service(session)
        session.delete(session.get(GridModelDefaultModel, "geometry-v3"))
        session.commit()  # SQLite-only lost-current fixture; PostgreSQL history remains immutable.
        replay = create.create(
            key=key, fields=fields(status=GameStatus.ACTIVE), selection={"mode": "default"}
        )
        assert replay.id == game.id
        assert (
            session.scalar(select(func.count()).select_from(GameGridModelAssignmentEventModel)) == 1
        )
        with pytest.raises(GridModelRegistryError, match="GAME_CREATE_IDEMPOTENCY_CONFLICT"):
            create.create(key=key, fields=fields("changed"), selection={"mode": "default"})


def test_unassigned_status_and_late_transfer_are_explicit_and_once(catalog):
    engine, service = catalog
    with Session(engine) as session:
        _, control, create = service(session)
        game = create.create(
            key=uuid4(), fields=fields(status=GameStatus.ARCHIVED), selection={"mode": "default"}
        )
        session.commit()
        assert game.status == GameStatus.ARCHIVED
        assert control.game_assignment(game.id)["initialTransferAllowed"]
        assert control.game_assignment(game.id)["version"] is None
        from game_predictor_api.domain.jobs import JobConflictError
        from game_predictor_api.storage.grid_profile_snapshot_resolver import (
            SqlAlchemyGridProfileSnapshotResolver,
        )

        with pytest.raises(JobConflictError) as blocked:
            SqlAlchemyGridProfileSnapshotResolver(
                session, artifact_root=Path(".")
            ).resolve_neural_grid_proposal(game_id=game.id)
        assert blocked.value.code == "GRID_MODEL_ASSIGNMENT_REQUIRED"
        version = published(session, control)
        key = uuid4()
        receipt = create.initial_transfer(
            game_id=game.id, key=key, expected_revision=0, version_id=version, actor="local-owner"
        )
        session.commit()
        assert receipt["kind"] == "bootstrap"
        assert (
            create.initial_transfer(
                game_id=game.id,
                key=key,
                expected_revision=0,
                version_id=version,
                actor="local-owner",
            )
            == receipt
        )
        with pytest.raises(GridModelRegistryError, match="INITIAL_TRANSFER_UNAVAILABLE"):
            create.initial_transfer(
                game_id=game.id,
                key=uuid4(),
                expected_revision=0,
                version_id=version,
                actor="local-owner",
            )


def test_fork_is_empty_family_and_pinned_protected_ancestry_without_cloned_version(catalog):
    engine, service = catalog
    with Session(engine) as session:
        _, control, create = service(session)
        version = published(session, control)
        game = create.create(
            key=uuid4(),
            fields=fields(),
            selection={
                "mode": "fork",
                "baseVersionId": str(version),
                "familyCode": "new_family",
                "familyLabel": "New family",
            },
        )
        session.commit()
        assignment = session.get(GameGridModelAssignmentModel, game.id)
        fork = session.get(GridModelFamilyForkModel, assignment.training_family_id)
        assert fork.base_version_id == version and assignment.version_id == version
        assert session.scalar(select(func.count()).select_from(GridModelVersionModel)) == 1
        assert session.scalar(select(func.count()).select_from(GridModelFamilyModel)) == 2
        assert not control.repository.initial_transfer_allowed(game.id)
        lineage = json.loads(fork.lineage_json)
        assert lineage["requiresProtectedSourceResolution"] is True
        assert {"final_test", "unseen_game", "Reels", "Treasure"} <= set(lineage["protectedRoles"])
        assert lineage["ancestors"][0]["snapshotId"]


def test_failure_in_initializer_rolls_back_all_catalogue_writes(catalog):
    engine, service = catalog

    def fail(*_args):
        raise RuntimeError("injected create receipt failure")

    with Session(engine) as session:
        _, control, create = service(session)
        version = published(session, control)
        original_record = create.receipts.record

        def fail_after_record(*args):
            original_record(*args)
            fail()

        create.receipts.record = fail_after_record
        try:
            with pytest.raises(RuntimeError, match="injected"):
                create.create(
                    key=uuid4(),
                    fields=fields(),
                    selection={
                        "mode": "fork",
                        "baseVersionId": str(version),
                        "familyCode": "rollback_family",
                        "familyLabel": "Rollback",
                    },
                )
        finally:
            create.receipts.record = original_record
            session.rollback()
        assert session.scalar(select(func.count()).select_from(GameModel)) == 0
        assert session.scalar(select(func.count()).select_from(GameGridModelAssignmentModel)) == 0
        assert session.scalar(select(func.count()).select_from(GridModelFamilyForkModel)) == 0
        assert session.scalar(select(func.count()).select_from(GridModelFamilyModel)) == 1


@pytest.mark.parametrize(
    "failure,allowed",
    [
        ("GRID_MODEL_EVALUATION_STALE", True),
        ("GRID_MODEL_EVALUATION_REQUIRED", False),
        ("GRID_MODEL_REGISTRY_CORRUPT", False),
        ("GRID_MODEL_PUBLICATION_STALE", False),
    ],
)
def test_default_only_masks_whitelisted_currentness_conditions(
    catalog, monkeypatch, failure, allowed
):
    engine, service = catalog
    with Session(engine) as session:
        _, control, create = service(session)
        published(session, control, default=True)

        def fail(*_args, **_kwargs):
            raise GridModelRegistryError(failure, "Fixture condition")

        monkeypatch.setattr(control.control, "eligible", fail)
        if allowed:
            assert create.create(key=uuid4(), fields=fields(), selection={"mode": "default"})
        else:
            with pytest.raises(GridModelRegistryError, match=failure):
                create.create(key=uuid4(), fields=fields(), selection={"mode": "default"})
        with pytest.raises(GridModelRegistryError, match=failure):
            create.create(
                key=uuid4(),
                fields=fields("explicit"),
                selection={"mode": "published", "versionId": str(uuid4())},
            )


def test_http_requires_key_defaults_to_neutral_and_preserves_historical_patch(catalog):
    engine, _ = catalog

    def dependency():
        with Session(engine) as session:
            try:
                yield CatalogService(SqlAlchemyCatalogRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    with TestClient(
        create_app(ApiSettings.from_environment({}), catalog_service_dependency=dependency)
    ) as client:
        assert (
            client.post("/api/v1/admin/games", json={"code": "x", "name": "X"}).status_code == 422
        )
        payload = {"code": "x", "name": "X", "idempotencyKey": str(uuid4())}
        created = client.post("/api/v1/admin/games", json=payload)
        assert created.status_code == 201, created.text
        assert created.json()["shapeGeometryConfiguration"] == "neural_grid_v3"
        rejected_key = str(uuid4())
        rejected = client.post(
            "/api/v1/admin/games",
            json={
                "code": "bad-published",
                "name": "Bad published",
                "idempotencyKey": rejected_key,
                "gridModel": {"mode": "published", "versionId": str(uuid4())},
            },
        )
        assert rejected.status_code == 404
        assert rejected.json()["details"]["createRecovery"]["idempotencyKey"] == rejected_key
        conflicting = client.post("/api/v1/admin/games", json={**payload, "name": "Changed"})
        assert conflicting.status_code == 409
        assert "createRecovery" not in conflicting.json()["details"]
        assert client.post("/api/v1/admin/games", json=payload).json()["id"] == created.json()["id"]
        reserved = client.post(
            "/api/v1/admin/games", json={**payload, "code": "7", "idempotencyKey": str(uuid4())}
        )
        assert reserved.status_code == 409
        assert reserved.json()["code"] == "GAME_CREATE_HISTORICAL_CODE_RESERVED"
        for configuration in (
            "requires_clarification",
            "framed_full_page_v2",
            "grid_profile_777_v2",
            "grid_profile_mumie_v1",
        ):
            request = copy.deepcopy(payload)
            request.update(
                code=configuration,
                idempotencyKey=str(uuid4()),
                shapeGeometryConfiguration=configuration,
            )
            assert (
                client.post("/api/v1/admin/games", json=request).json()["code"]
                == "GAME_CREATE_V3_REQUIRED"
            )
            response = client.patch(
                f"/api/v1/admin/games/{created.json()['id']}",
                json={"shapeGeometryConfiguration": configuration},
            )
            assert (
                response.status_code == 200
                and response.json()["shapeGeometryConfiguration"] == configuration
            )


def test_transfer_does_not_fabricate_new_game_evaluation_or_bypass_later_gate(catalog, tmp_path):
    engine, service = catalog
    with Session(engine) as session:
        _, control, create = service(session)
        source = create.create(
            key=uuid4(), fields=fields("measured-source"), selection={"mode": "default"}
        )
        session.commit()
        payload = candidate(tmp_path)
        payload["cohortId"] = str(uuid4())
        control.register(uuid4(), payload)
        report = seed_report(session, payload, [source.id])
        execute(control, "publish", payload["versionId"], evaluation=report)
        execute(control, "set_default", payload["versionId"])
        session.commit()
        new_game = create.create(
            key=uuid4(), fields=fields("new-unmeasured"), selection={"mode": "default"}
        )
        session.commit()
        assignment = control.game_assignment(new_game.id)
        assert assignment["version"]["manifest"]["versionId"] == payload["versionId"]
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_REQUIRED"):
            execute(control, "activate", payload["versionId"], game=new_game.id, expected=1)
        receipt = session.scalar(
            select(GameCreateReceiptModel).where(GameCreateReceiptModel.game_id == new_game.id)
        )
        assert (
            json.loads(receipt.reservation_json)["assignment"]["transfer"]["qualityScope"]
            == "source-games-only"
        )


def test_fork_registration_rejects_a_branch_which_skips_its_frozen_base(catalog, tmp_path):
    engine, service = catalog
    with Session(engine) as session:
        _, control, create = service(session)
        source = create.create(key=uuid4(), fields=fields("source"), selection={"mode": "default"})
        session.commit()
        payload = candidate(tmp_path)
        payload["cohortId"] = str(uuid4())
        control.register(uuid4(), payload)
        report = seed_report(session, payload, [source.id])
        execute(control, "publish", payload["versionId"], evaluation=report)
        session.commit()
        new_game = create.create(
            key=uuid4(),
            fields=fields("fork"),
            selection={
                "mode": "fork",
                "baseVersionId": payload["versionId"],
                "familyCode": "fork_family",
                "familyLabel": "Fork family",
            },
        )
        session.commit()
        assignment = session.get(GameGridModelAssignmentModel, new_game.id)
        detached = copy.deepcopy(payload)
        detached.update(
            familyId=str(assignment.training_family_id),
            familyCode="fork_family",
            familyLabel="Fork family",
            versionId=str(uuid4()),
            version="v3",
        )
        detached["inferenceManifest"]["version"] = "v3"
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_FORK_BASE_CONFLICT"):
            control.repository.register(
                detached, validate_manifest(detached), descriptor_sha256(detached), uuid4()
            )


def test_known_v3_without_symbol_resolver_fails_closed():
    from types import SimpleNamespace

    from game_predictor_api.application.jobs import JobService
    from game_predictor_api.domain.jobs import JobConflictError

    service = JobService(SimpleNamespace(game_uses_neural_grid=lambda _: True))
    with pytest.raises(JobConflictError) as error:
        service._resolve_import_symbol_snapshot(game_id=uuid4(), allow_unclassified_cold_start=True)
    assert error.value.code == "SYMBOL_MODEL_RESOLVER_REQUIRED"


def test_different_create_key_cannot_adopt_by_code_and_removed_result_is_not_recreated(catalog):
    engine, service = catalog
    key = uuid4()
    with Session(engine) as session:
        _, _, create = service(session)
        game = create.create(key=key, fields=fields(), selection={"mode": "default"})
        session.commit()
        from game_predictor_api.domain.catalog import CatalogConflictError

        with pytest.raises(CatalogConflictError) as conflict:
            create.create(key=uuid4(), fields=fields(), selection={"mode": "default"})
        assert conflict.value.code == "GAME_CODE_ALREADY_EXISTS"
        session.rollback()
        session.delete(session.get(GameModel, game.id))
        # SQLite models physical removal; the ledger intentionally has no game FK.
        session.commit()
        with pytest.raises(CatalogConflictError) as removed:
            create.create(key=key, fields=fields(), selection={"mode": "default"})
        assert removed.value.code == "GAME_CREATE_RESULT_REMOVED"
        assert session.scalar(select(func.count()).select_from(GameModel)) == 0
        assert session.scalar(select(func.count()).select_from(GameCreateReceiptModel)) == 1


def test_http_initial_transfer_retry_gate_and_invalid_modes(catalog):
    engine, service = catalog
    with Session(engine) as session:
        _, control, create = service(session)
        game = create.create(
            key=uuid4(), fields=fields("http-transfer"), selection={"mode": "default"}
        )
        version = published(session, control)
        session.commit()

    def registry_dependency():
        with Session(engine) as session:
            try:
                yield service(session)[1]
                session.commit()
            except BaseException:
                session.rollback()
                raise

    app = create_app(
        ApiSettings.from_environment({}), grid_model_registry_service_dependency=registry_dependency
    )
    with TestClient(app) as client:
        body = {
            "idempotencyKey": str(uuid4()),
            "versionId": str(version),
            "expectedRevision": 0,
            "mode": "initial_transfer",
        }
        path = f"/api/v1/admin/games/{game.id}/grid-model-assignment/activate"
        first = client.post(path, json=body)
        assert first.status_code == 200, first.text
        assert client.post(path, json=body).json() == first.json()
        denied = client.post(path, json={**body, "idempotencyKey": str(uuid4())})
        assert denied.status_code == 409
        assert denied.json()["code"] == "GRID_MODEL_INITIAL_TRANSFER_UNAVAILABLE"
        for path in [
            "/api/v1/admin/grid-model-default",
            f"/api/v1/admin/games/{game.id}/grid-model-assignment/rollback",
        ]:
            result = client.post(path, json=body)
            assert result.status_code == 409, result.text
            assert result.json()["code"] == "GRID_MODEL_COMMAND_INVALID"


def test_recovery_proof_only_after_rollback_with_no_durable_receipt(catalog, monkeypatch):
    engine, service = catalog
    with Session(engine) as session:
        repo, control, _ = service(session)
        key = uuid4()

        def fail(*args, **kwargs):
            raise GridModelRegistryError("GRID_MODEL_NOT_PUBLISHED", "Fixture rejection")

        monkeypatch.setattr(
            "game_predictor_api.application.new_game_geometry.NewGameGeometryService._selection",
            fail,
        )
        with pytest.raises(GridModelRegistryError) as rejected:
            repo.add_game(**fields(), idempotency_key=key)
        assert rejected.value.details["createRecovery"] == {
            "schemaVersion": "game-create-recovery-v1",
            "idempotencyKey": str(key),
            "reservation": "not_created",
        }
        reads = 0
        original = SqlAlchemyGameCreateReceiptRepository.receipt

        def qualification_fails(self, candidate_key):
            nonlocal reads
            reads += 1
            if reads > 1:
                raise RuntimeError("read failed")
            return original(self, candidate_key)

        monkeypatch.setattr(SqlAlchemyGameCreateReceiptRepository, "receipt", qualification_fails)
        with pytest.raises(GridModelRegistryError) as unqualified:
            repo.add_game(**fields(), idempotency_key=uuid4())
        assert unqualified.value.code == "GRID_MODEL_NOT_PUBLISHED"
        assert "createRecovery" not in unqualified.value.details
        monkeypatch.setattr(SqlAlchemyGameCreateReceiptRepository, "receipt", original)

        def unavailable(*args, **kwargs):
            raise GridModelRegistryError("GRID_MODEL_INFRA_FAILED", "Unavailable", 503)

        monkeypatch.setattr(
            "game_predictor_api.application.new_game_geometry.NewGameGeometryService._selection",
            unavailable,
        )
        with pytest.raises(GridModelRegistryError) as infrastructure:
            repo.add_game(**fields(), idempotency_key=uuid4())
        assert "createRecovery" not in infrastructure.value.details


def test_initial_transfer_missing_game_is_typed_and_receipt_read_once(catalog, monkeypatch):
    engine, service = catalog
    with Session(engine) as session:
        _, control, create = service(session)
        game = create.create(key=uuid4(), fields=fields(), selection={"mode": "default"})
        session.commit()
        count = 0
        original = control.repository.game_receipt

        def receipt(game_id):
            nonlocal count
            count += 1
            return original(game_id)

        monkeypatch.setattr(control.repository, "game_receipt", receipt)
        assert control.repository.initial_transfer_allowed(game.id)
        assert count == 1
        game_record = session.get(GameModel, game.id)
        game_record.code = "7"
        session.commit()
        assert not control.repository.initial_transfer_allowed(game.id)
        session.delete(game_record)
        session.commit()
        with pytest.raises(GridModelRegistryError) as missing:
            control.repository.initial_transfer_allowed(game.id)
        assert missing.value.code == "GRID_MODEL_GAME_NOT_FOUND"
