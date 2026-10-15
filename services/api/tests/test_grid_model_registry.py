"""Catalogue commands, artifact guards, durable retries and real HTTP contracts."""

from __future__ import annotations

import copy
import hashlib
import json
import runpy
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import (
    grid_engine_profile_for,
    neural_import_profile,
)
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
    historical_catalogue,
    validate_manifest,
)
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.main import create_app
from game_predictor_api.schemas.grid_model_registry import GridModelManifest
from game_predictor_api.storage.database import assign_session_game
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)
from game_predictor_api.storage.grid_model_registry_models import (
    GameCreateReceiptModel,
    GameGridModelAssignmentEventModel,
    GameGridModelAssignmentModel,
    GridModelControlEventModel,
    GridModelDefaultModel,
    GridModelEvaluationInvalidationModel,
    GridModelEvaluationReportModel,
    GridModelFamilyForkModel,
    GridModelFamilyModel,
    GridModelPublicationModel,
    GridModelRegistrationReceiptModel,
    GridModelVersionEventModel,
    GridModelVersionModel,
)
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

TABLES = (
    GridModelFamilyForkModel,
    GameCreateReceiptModel,
    GridModelFamilyModel,
    GridModelVersionModel,
    GridModelRegistrationReceiptModel,
    GridModelVersionEventModel,
    GameGridModelAssignmentModel,
    GameGridModelAssignmentEventModel,
    GridModelEvaluationReportModel,
    GridModelEvaluationInvalidationModel,
    GridModelPublicationModel,
    GridModelControlEventModel,
    GridModelDefaultModel,
)


def candidate(root: Path) -> dict:
    payload = copy.deepcopy(historical_catalogue()[0])
    payload.update(
        familyId=str(uuid4()),
        familyCode="third_geometry",
        familyLabel="Third geometry",
        versionId=str(uuid4()),
        version="v2",
        baseVersionId=historical_catalogue()[0]["versionId"],
        admission="not_evaluated",
        managedDirectory="models/grid-engine/third_geometry/v2",
    )
    files = []
    directory = root / payload["managedDirectory"]
    directory.mkdir(parents=True)
    for name in ("screen.onnx", "board.onnx", "bundle.json", "preset.json"):
        content = ("test-" + name).encode()
        (directory / name).write_bytes(content)
        files.append(
            {"name": name, "sizeBytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        )
    training_directory = directory / "training-base"
    training_directory.mkdir()
    training_files = []
    for name in ("checkpoint.pt", "weights.pt", "bundle.json", "preset.json"):
        content = (
            (directory / name).read_bytes()
            if name in {"bundle.json", "preset.json"}
            else ("training-" + name).encode()
        )
        (training_directory / name).write_bytes(content)
        training_files.append(
            {"name": name, "sizeBytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        )
    payload["trainingArtifacts"] = training_files
    payload["provenance"]["checkpointSha256"] = training_files[0]["sha256"]
    payload["provenance"]["weightsSha256"] = training_files[1]["sha256"]
    payload["inferenceManifest"]["checkpointSha256"] = training_files[0]["sha256"]
    payload["inferenceManifest"]["weightsSha256"] = training_files[1]["sha256"]
    payload["files"] = files
    payload["inferenceManifest"].update(version="v2", files=files)
    (directory / "manifest.json").write_text(
        json.dumps(payload["inferenceManifest"]), encoding="utf-8"
    )
    from game_predictor_api.storage.grid_engine_model_store import receipt_bytes

    identity = {
        "schemaVersion": "grid-engine-training-base-v1",
        "model": payload["inferenceManifest"],
        "files": training_files,
        "sources": {
            file["name"]: str((training_directory / file["name"]).resolve())
            for file in training_files
        },
    }
    (training_directory / "receipt.json").write_bytes(receipt_bytes(identity))
    return payload


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS public")
        connection.exec_driver_sql("CREATE TABLE public.games (id CHAR(32) PRIMARY KEY)")
        for model in TABLES:
            model.__table__.create(connection)
    baseline = historical_catalogue()[0]
    with Session(engine) as session:
        session.add(
            GridModelFamilyModel(
                id=UUID(baseline["familyId"]),
                code=baseline["familyCode"],
                descriptor_json=canonical_json(
                    {
                        key: baseline[key]
                        for key in ("familyCode", "familyLabel", "topology", "capabilities")
                    }
                ),
            )
        )
        session.flush()
        session.add(
            GridModelVersionModel(
                id=UUID(baseline["versionId"]),
                family_id=UUID(baseline["familyId"]),
                version="v1",
                manifest_json=validate_manifest(baseline),
                manifest_sha256=descriptor_sha256(baseline),
            )
        )
        session.commit()
    yield engine
    engine.dispose()


def service(session, root):
    return GridModelRegistryService(
        SqlAlchemyGridModelRegistryRepository(session), GridModelArtifactInspector(root)
    )


def test_historical_descriptors_are_closed_immutable_and_never_new_pass():
    for payload in historical_catalogue():
        assert (
            GridModelManifest.model_validate(payload).model_dump(mode="json", by_alias=True)
            == payload
        )
        assert validate_manifest(payload) == canonical_json(payload)
        assert payload["admission"] == "historical_baseline"
        assert payload["cohortId"] is None and payload["baseVersionId"] is None


def test_historical_descriptors_match_frozen_migration_seed_and_pinned_sha() -> None:
    migration_root = Path(__file__).resolve().parents[1] / "alembic"
    frozen = json.loads(
        (migration_root / "data/grid_model_baselines_v1.json").read_text(encoding="utf-8")
    )
    assert frozen == list(historical_catalogue())
    # Loading the revision also exercises its own pinned integrity guard without DDL.
    migration = runpy.run_path(str(migration_root / "versions/0156_grid_model_registry.py"))
    assert migration["BASELINES"] == frozen
    canonical = canonical_json(frozen)
    assert migration["BASELINES_CANONICAL"] == canonical
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == (
        "e0816dfc9aff709eb1529306da45443393df5e62fa6ed7618076a49ee6aad76d"
    )


def test_registration_retry_new_session_conflicts_and_third_family(engine, tmp_path):
    payload = candidate(tmp_path)
    key = uuid4()
    with Session(engine) as session:
        first = service(session, tmp_path).register(key, payload)
        session.commit()
    with Session(engine) as session:
        assert service(session, tmp_path).register(key, payload) == first
        assert service(session, tmp_path).register(uuid4(), payload) == first
        session.commit()
    with Session(engine) as session:
        assert len(list(session.scalars(select(GridModelVersionEventModel)))) == 1
        changed = copy.deepcopy(payload)
        changed["familyLabel"] = "Changed"
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_IDEMPOTENCY_CONFLICT"):
            service(session, tmp_path).register(key, changed)
        wrong_family = copy.deepcopy(payload)
        wrong_family["familyId"] = str(uuid4())
        wrong_family["versionId"] = str(uuid4())
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_FAMILY_CONFLICT"):
            service(session, tmp_path).register(uuid4(), wrong_family)
        changed = copy.deepcopy(payload)
        changed["versionId"] = str(uuid4())
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_VERSION_CONFLICT"):
            service(session, tmp_path).register(uuid4(), changed)


def test_artifact_loss_and_changed_manifest_fail_closed_without_receipt(engine, tmp_path):
    payload = candidate(tmp_path)
    file = tmp_path / payload["managedDirectory"] / "board.onnx"
    file.unlink()
    with Session(engine) as session:
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_ARTIFACT_UNAVAILABLE"):
            service(session, tmp_path).register(uuid4(), payload)
        assert session.scalar(select(GridModelRegistrationReceiptModel)) is None
        assert len(list(session.scalars(select(GridModelFamilyModel)))) == 1
    bad = copy.deepcopy(payload)
    bad["inferenceManifest"]["version"] = "v3"
    with pytest.raises(GridModelRegistryError, match="GRID_MODEL_MANIFEST_INVALID"):
        validate_manifest(bad)


def test_atomic_failure_rolls_back_family_version_and_event(engine, tmp_path):
    payload = candidate(tmp_path)

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO public.grid_model_registration_receipts"):
            raise RuntimeError("injected receipt failure")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with Session(engine) as session:
            with pytest.raises(RuntimeError, match="injected receipt failure"):
                service(session, tmp_path).register(uuid4(), payload)
            session.rollback()
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    with Session(engine) as session:
        assert len(list(session.scalars(select(GridModelFamilyModel)))) == 1
        assert len(list(session.scalars(select(GridModelVersionModel)))) == 1
        assert list(session.scalars(select(GridModelVersionEventModel))) == []


def test_unsafe_paths_and_hash_mismatch(engine, tmp_path):
    payload = candidate(tmp_path)
    bad = copy.deepcopy(payload)
    bad["managedDirectory"] = "models/grid-engine/../../outside"
    with pytest.raises(GridModelRegistryError, match="GRID_MODEL_PATH_INVALID"):
        validate_manifest(bad)
    (tmp_path / payload["managedDirectory"] / "screen.onnx").write_bytes(b"corrupt")
    assert GridModelArtifactInspector(tmp_path).inspect(payload) == (
        False,
        "GRID_MODEL_ARTIFACT_MISMATCH",
    )
    bad = copy.deepcopy(payload)
    bad["topology"]["boardColumns"] = 5
    with pytest.raises(GridModelRegistryError, match="GRID_MODEL_TOPOLOGY_UNSUPPORTED"):
        validate_manifest(bad)


def test_explicit_cross_game_session_scope_refuses_before_read(engine, tmp_path):
    with Session(engine) as session:
        assign_session_game(session, uuid4())
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_GAME_SCOPE_CONFLICT"):
            service(session, tmp_path).game_assignment(uuid4())


def test_http_register_get_and_replayed_command_after_artifact_loss(engine, tmp_path):
    payload = candidate(tmp_path)
    key = str(uuid4())

    def dependency():
        with Session(engine) as session:
            try:
                yield service(session, tmp_path)
                session.commit()
            except BaseException:
                session.rollback()
                raise

    app = create_app(
        ApiSettings.from_environment({}), grid_model_registry_service_dependency=dependency
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/grid-model-versions", json={"idempotencyKey": key, "manifest": payload}
        )
        assert response.status_code == 200, response.text
        assert response.json()["manifest"]["familyCode"] == "third_geometry"
        assert response.json()["published"] is False
        assigned, unassigned = uuid4(), uuid4()
        with Session(engine) as session:
            session.execute(text("INSERT INTO public.games(id) VALUES(:id)"), {"id": assigned.hex})
            session.execute(
                text("INSERT INTO public.games(id) VALUES(:id)"), {"id": unassigned.hex}
            )
            session.add(
                GameGridModelAssignmentModel(
                    game_id=assigned, version_id=UUID(payload["versionId"]), revision=1
                )
            )
            session.commit()
        bound = client.get(f"/api/v1/admin/games/{assigned}/grid-model-assignment")
        assert (
            bound.status_code == 200
            and bound.json()["version"]["manifest"]["versionId"] == payload["versionId"]
        )
        assert (
            client.get(f"/api/v1/admin/games/{unassigned}/grid-model-assignment").json()["version"]
            is None
        )
        extra = copy.deepcopy(payload)
        extra["inferenceManifest"]["gameId"] = str(assigned)
        assert (
            client.post(
                "/api/v1/admin/grid-model-versions",
                json={"idempotencyKey": str(uuid4()), "manifest": extra},
            ).status_code
            == 422
        )

        assert client.get("/api/v1/admin/grid-model-versions").status_code == 200
        missing_game = client.get(f"/api/v1/admin/games/{uuid4()}/grid-model-assignment")
        assert missing_game.status_code == 404
        (tmp_path / payload["managedDirectory"] / "board.onnx").unlink()
        retry = client.post(
            "/api/v1/admin/grid-model-versions", json={"idempotencyKey": key, "manifest": payload}
        )
        assert retry.status_code == 409
        assert retry.json()["code"] == "GRID_MODEL_ARTIFACT_UNAVAILABLE"


def test_neutral_enum_never_falls_back_to_classical_before_dynamic_resolver():
    for resolver in (grid_engine_profile_for, neural_import_profile):
        with pytest.raises(JobConflictError) as error:
            resolver(GameShapeGeometryConfiguration.NEURAL_GRID_V3)
        assert error.value.code == "GRID_MODEL_DYNAMIC_ROUTING_REQUIRED"
    assert neural_import_profile("framed_full_page_v2") is None
    assert neural_import_profile("grid_profile_777_v2").configuration.value == "grid_profile_777_v2"


def test_missing_checkpoint_or_receipt_blocks_registration(engine, tmp_path):
    payload = candidate(tmp_path)
    receipt = tmp_path / payload["managedDirectory"] / "training-base" / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    assert GridModelArtifactInspector(tmp_path).inspect(payload) == (
        False,
        "GRID_MODEL_ARTIFACT_UNREADABLE",
    )
    receipt.write_text(json.dumps({"payload": 42}), encoding="utf-8")
    assert GridModelArtifactInspector(tmp_path).inspect(payload) == (
        False,
        "GRID_MODEL_TRAINING_RECEIPT_INVALID",
    )
    receipt.unlink()
    with Session(engine) as session:
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_ARTIFACT_UNAVAILABLE"):
            service(session, tmp_path).register(uuid4(), payload)
        assert session.scalar(select(GridModelRegistrationReceiptModel)) is None


def test_domain_rejects_game_data_hidden_in_shared_descriptor(tmp_path):
    payload = candidate(tmp_path)
    payload["symbolLabels"] = {"gameId": str(uuid4())}
    with pytest.raises(GridModelRegistryError, match="GRID_MODEL_MANIFEST_INVALID"):
        validate_manifest(payload)
