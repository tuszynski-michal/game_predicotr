"""Control commands use synthetic server records; no real model PASS is asserted."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.grid_model_publication import (
    EVALUATION_POLICY,
    EVALUATION_PRODUCER,
    EVALUATION_SCHEMA,
)
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
    historical_catalogue,
)
from game_predictor_api.domain.neural_grid_proposal import NeuralGridSnapshot
from game_predictor_api.main import create_app
from game_predictor_api.security.local_admin import ADMIN_ACTOR
from game_predictor_api.storage.database import assign_session_game
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)
from game_predictor_api.storage.grid_model_registry_models import (
    GameGridModelAssignmentEventModel,
    GameGridModelAssignmentModel,
    GridModelControlEventModel,
    GridModelEvaluationInvalidationModel,
    GridModelEvaluationReportModel,
    GridModelPublicationModel,
    GridModelVersionModel,
)
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session
from test_grid_model_registry import candidate
from test_grid_model_registry import engine as registry_engine  # noqa: F401


class FixtureInspector(GridModelArtifactInspector):
    """Avoid fabricating frozen production weight bytes. Historical report is real."""

    def inspect(self, payload):
        if payload in historical_catalogue():
            return True, "GRID_MODEL_ARTIFACT_AVAILABLE"
        return super().inspect(payload)


def registry(session, root):
    return GridModelRegistryService(
        SqlAlchemyGridModelRegistryRepository(session), FixtureInspector(root)
    )


def execute(service, kind, version, *, game=None, expected=0, key=None, evaluation=None):
    return service.control.execute(
        kind=kind,
        key=key or uuid4(),
        expected_revision=expected,
        version_id=UUID(version),
        game_id=game,
        evaluation_id=evaluation,
        actor=ADMIN_ACTOR,
    )


def report_payload(payload, games):
    """Internal test fixture only. TASK-0997 will compute real per-game outcomes."""
    baseline = historical_catalogue()[0]
    return {
        "schemaVersion": EVALUATION_SCHEMA,
        "producer": EVALUATION_PRODUCER,
        "policyVersion": EVALUATION_POLICY,
        "versionId": payload["versionId"],
        "manifestSha256": descriptor_sha256(payload),
        "baseVersionId": payload["baseVersionId"],
        "baseManifestSha256": descriptor_sha256(baseline),
        "cohortId": payload["cohortId"],
        "cohortSha256": "a" * 64,
        "requiredGameIds": [str(game) for game in games],
        "games": [
            {
                "gameId": str(game),
                "validation": "pass",
                "regression": "pass",
                "coverage": "complete",
            }
            for game in games
        ],
    }


def seed_report(session, payload, games, change=None, producer=EVALUATION_PRODUCER):
    report = report_payload(payload, games)
    if change:
        change(report)
    key = uuid4()
    session.add(
        GridModelEvaluationReportModel(
            id=key,
            version_id=UUID(payload["versionId"]),
            producer=producer,
            report_json=canonical_json(report),
            report_sha256=descriptor_sha256(report),
        )
    )
    session.flush()
    return key


@pytest.fixture
def controls(request, tmp_path):
    engine = request.getfixturevalue("registry_engine")
    game, other = uuid4(), uuid4()
    baseline = historical_catalogue()[0]
    payload = candidate(tmp_path)
    payload["cohortId"] = str(uuid4())
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE public.games ADD COLUMN code TEXT")
        connection.exec_driver_sql(
            "ALTER TABLE public.games ADD COLUMN shape_geometry_configuration TEXT"
        )
        for game_id, code in ((game, "test"), (other, "other")):
            connection.execute(
                text("""INSERT INTO public.games(id,code,shape_geometry_configuration)
VALUES(:id,:code,'neural_grid_v3')"""),
                {"id": game_id.hex, "code": code},
            )
    with Session(engine) as session:
        registry(session, tmp_path).register(uuid4(), payload)
        session.add(
            GameGridModelAssignmentModel(
                game_id=game, version_id=UUID(baseline["versionId"]), revision=1
            )
        )
        session.flush()
        session.add(
            GameGridModelAssignmentEventModel(
                game_id=game,
                id=uuid4(),
                idempotency_key=uuid4(),
                version_id=UUID(baseline["versionId"]),
                revision=1,
                kind="historical_assignment",
            )
        )
        session.commit()
    return SimpleNamespace(
        engine=engine, root=tmp_path, game=game, other=other, baseline=baseline, candidate=payload
    )


def publish_fixture(c, session):
    service = registry(session, c.root)
    report = seed_report(session, c.candidate, [c.game])
    execute(service, "publish", c.baseline["versionId"])
    execute(service, "publish", c.candidate["versionId"], evaluation=report)
    return service, report


def control_http_client(c):
    def dependency():
        with Session(c.engine) as session:
            try:
                yield registry(session, c.root)
                session.commit()
            except BaseException:
                session.rollback()
                raise

    return TestClient(
        create_app(
            ApiSettings.from_environment({}), grid_model_registry_service_dependency=dependency
        )
    )


def test_missing_evaluation_blocks_candidate_and_historical_admission_uses_real_report(controls):
    c = controls
    with Session(c.engine) as session:
        service = registry(session, c.root)
        assert service.game_assignment(c.game)["version"]["published"] is False
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_REQUIRED"):
            execute(service, "publish", c.candidate["versionId"])
        assert session.scalar(select(GridModelPublicationModel)) is None
        result = execute(service, "publish", c.baseline["versionId"])
        assert result["evidenceKind"] == "historical_admission"
        publication = session.get(GridModelPublicationModel, UUID(c.baseline["versionId"]))
        proof = json.loads(publication.evidence_json)
        assert proof["report"].endswith("GRID_V3_COMPARISON_REPORT_20261004.md")
        assert proof["historicalResults"] == c.baseline["historicalReports"]
        assert "cohortId" not in proof and "pass" not in proof
        assert service.game_assignment(c.game)["revision"] == 1
        assert service.control.default_view()["version"] is None


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(producer="client:untrusted"),
        lambda r: r.update(policyVersion="unknown"),
        lambda r: r.update(manifestSha256="0" * 64),
        lambda r: r.update(baseManifestSha256="0" * 64),
        lambda r: r.update(cohortId=str(uuid4())),
        lambda r: r.update(cohortSha256="invalid"),
        lambda r: r.update(games=[]),
        lambda r: r["games"][0].update(validation="fail"),
        lambda r: r["games"][0].update(regression="fail"),
        lambda r: r["games"][0].update(coverage="partial"),
        lambda r: r["requiredGameIds"].append(str(uuid4())),
        lambda r: r.update(games=r["games"] * 2, requiredGameIds=r["requiredGameIds"] * 2),
    ],
)
def test_untrusted_incomplete_failed_or_mismatched_evidence_fails_closed(controls, mutation):
    c = controls
    with Session(c.engine) as session:
        report = seed_report(session, c.candidate, [c.game], change=mutation)
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_REQUIRED"):
            execute(
                registry(session, c.root), "publish", c.candidate["versionId"], evaluation=report
            )
        assert session.scalar(select(GridModelPublicationModel)) is None
        assert session.scalar(select(GridModelControlEventModel)) is None


def test_exact_receipt_replays_after_new_session_even_when_artifact_or_proof_lost(controls):
    c = controls
    with Session(c.engine) as session:
        service, report = publish_fixture(c, session)
        key = uuid4()
        result = execute(
            service, "activate", c.candidate["versionId"], game=c.game, expected=1, key=key
        )
        session.commit()
    with Session(c.engine) as session:
        session.add(
            GridModelEvaluationInvalidationModel(
                id=uuid4(), report_id=report, reason="approval revoked", actor="server:test-fixture"
            )
        )
        session.commit()
    (c.root / c.candidate["managedDirectory"] / "board.onnx").unlink()
    with Session(c.engine) as session:
        service = registry(session, c.root)
        assert (
            execute(service, "activate", c.candidate["versionId"], game=c.game, expected=1, key=key)
            == result
        )
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_IDEMPOTENCY_CONFLICT"):
            execute(service, "activate", c.baseline["versionId"], game=c.game, expected=1, key=key)
        assert service.game_assignment(c.game)["revision"] == 2


def test_invalidated_published_proof_blocks_new_activation_and_default(controls):
    c = controls
    with Session(c.engine) as session:
        service, report = publish_fixture(c, session)
        execute(service, "set_default", c.candidate["versionId"])
        session.add(
            GridModelEvaluationInvalidationModel(
                id=uuid4(), report_id=report, reason="truth changed", actor="server:test-fixture"
            )
        )
        session.commit()
    with Session(c.engine) as session:
        service = registry(session, c.root)
        for kind, game, expected in (("activate", c.game, 1), ("set_default", None, 1)):
            with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_STALE"):
                execute(service, kind, c.candidate["versionId"], game=game, expected=expected)
        assert service.control.default_view()["eligible"] is False
        assert service.control.default_view()["revision"] == 1
        view = service.list_versions()
        candidate_view = next(
            v for v in view if v["manifest"]["versionId"] == c.candidate["versionId"]
        )
        assert candidate_view["published"] is True and candidate_view["eligible"] is False
        assert candidate_view["eligibilityReasonCode"] == "GRID_MODEL_EVALUATION_STALE"


def test_default_cas_rollback_history_and_old_job_pin_leave_artifacts_unchanged(controls):
    c = controls
    original = copy.deepcopy(c.candidate)
    files_before = {
        path.relative_to(c.root).as_posix(): path.read_bytes()
        for path in c.root.rglob("*")
        if path.is_file()
    }
    old_job = NeuralGridSnapshot.from_catalogue(
        game_id=str(c.game),
        game_configuration="neural_grid_v3",
        expected_layout_count=100,
        descriptor=c.baseline,
    ).to_payload()
    with Session(c.engine) as session:
        service, _ = publish_fixture(c, session)
        first = execute(service, "activate", c.candidate["versionId"], game=c.game, expected=1)
        assert first["revision"] == 2
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_REVISION_CONFLICT"):
            execute(service, "activate", c.baseline["versionId"], game=c.game, expected=1)
        default_key = uuid4()
        default = execute(service, "set_default", c.candidate["versionId"], key=default_key)
        execute(service, "set_default", c.baseline["versionId"], expected=1)
        assert execute(service, "set_default", c.candidate["versionId"], key=default_key) == default
        assert service.control.default_view()["version"]["manifest"] == c.baseline
        assert service.game_assignment(c.game)["version"]["manifest"] == c.candidate
        assert service.game_assignment(c.other)["version"] is None
        rolled = execute(service, "rollback", c.baseline["versionId"], game=c.game, expected=2)
        assert rolled["revision"] == 3
        assert [row["kind"] for row in service.repository.history(c.game)] == [
            "rollback",
            "activate",
            "historical_assignment",
        ]
        assert service.game_assignment(c.game)["version"]["manifest"] == c.baseline
        session.commit()
    assert NeuralGridSnapshot.from_payload(old_job).to_payload() == old_job
    assert c.candidate == original and original["admission"] == "not_evaluated"
    assert files_before == {
        path.relative_to(c.root).as_posix(): path.read_bytes()
        for path in c.root.rglob("*")
        if path.is_file()
    }


def test_evaluated_game_scope_historical_game_and_rollback_target_are_guarded(controls):
    c = controls
    with Session(c.engine) as session:
        service, _ = publish_fixture(c, session)
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_REQUIRED"):
            execute(service, "activate", c.candidate["versionId"], game=c.other)
        # Global eligible read permits a future compatible game bootstrap in TASK-1004.
        assert service.control.eligible(UUID(c.candidate["versionId"]))[0]["published"]
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_ROLLBACK_TARGET_INVALID"):
            execute(service, "rollback", c.baseline["versionId"], game=c.other)
        session.execute(text("UPDATE public.games SET code='7' WHERE id=:id"), {"id": c.other.hex})
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_GAME_INCOMPATIBLE"):
            execute(service, "activate", c.baseline["versionId"], game=c.other)
        assign_session_game(session, c.game)
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_GAME_SCOPE_CONFLICT"):
            execute(service, "activate", c.baseline["versionId"], game=c.other)


def test_injected_event_failure_rolls_back_assignment_and_publication(controls):
    c = controls
    with Session(c.engine) as session:
        publish_fixture(c, session)
        session.commit()

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO public.game_grid_model_assignment_events"):
            raise RuntimeError("injected control event failure")

    event.listen(c.engine, "before_cursor_execute", fail)
    try:
        with Session(c.engine) as session:
            with pytest.raises(RuntimeError, match="injected control event failure"):
                execute(
                    registry(session, c.root),
                    "activate",
                    c.candidate["versionId"],
                    game=c.game,
                    expected=1,
                )
            session.rollback()
    finally:
        event.remove(c.engine, "before_cursor_execute", fail)
    with Session(c.engine) as session:
        assert registry(session, c.root).game_assignment(c.game)["revision"] == 1
        assert len(registry(session, c.root).repository.history(c.game)) == 1


def test_publication_event_failure_is_atomic_and_repeat_publication_is_controlled(controls):
    c = controls

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO public.grid_model_control_events"):
            raise RuntimeError("injected publication event failure")

    event.listen(c.engine, "before_cursor_execute", fail)
    try:
        with Session(c.engine) as session:
            with pytest.raises(RuntimeError, match="injected publication event failure"):
                execute(registry(session, c.root), "publish", c.baseline["versionId"])
            session.rollback()
    finally:
        event.remove(c.engine, "before_cursor_execute", fail)
    with Session(c.engine) as session:
        assert session.scalar(select(GridModelPublicationModel)) is None
        execute(registry(session, c.root), "publish", c.baseline["versionId"])
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_REVISION_CONFLICT"):
            execute(registry(session, c.root), "publish", c.baseline["versionId"], expected=1)


def test_report_storage_producer_hash_and_reference_cannot_substitute_for_evaluator(controls):
    c = controls
    with Session(c.engine) as session:
        service = registry(session, c.root)
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_NOT_PUBLISHED"):
            execute(service, "activate", c.candidate["versionId"], game=c.game, expected=1)
        for producer in ("client:untrusted", EVALUATION_PRODUCER):
            report_id = seed_report(session, c.candidate, [c.game], producer=producer)
            if producer == EVALUATION_PRODUCER:
                session.get(GridModelEvaluationReportModel, report_id).report_sha256 = "0" * 64
                session.flush()
            with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_REQUIRED"):
                execute(service, "publish", c.candidate["versionId"], evaluation=report_id)
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_REQUIRED"):
            execute(service, "publish", c.candidate["versionId"], evaluation=uuid4())


def test_http_commands_reject_client_pass_actor_and_replay_original_receipt(controls):
    c = controls
    publish_url = f"/api/v1/admin/grid-model-versions/{c.candidate['versionId']}/publish"
    base_url = f"/api/v1/admin/grid-model-versions/{c.baseline['versionId']}/publish"
    command = {"idempotencyKey": str(uuid4()), "expectedRevision": 0}
    with control_http_client(c) as client:
        for extra in ({"passed": True}, {"report": {"verdict": "PASS"}}, {"actor": "human"}):
            assert client.post(publish_url, json={**command, **extra}).status_code == 422
        missing = client.post(publish_url, json=command)
        assert missing.status_code == 409
        assert missing.json()["code"] == "GRID_MODEL_EVALUATION_REQUIRED"
        assert client.post(base_url, json=command).status_code == 200
        assert client.post(base_url, json=command).json()["actor"] == ADMIN_ACTOR
        default_command = {
            **command,
            "idempotencyKey": str(uuid4()),
            "versionId": c.baseline["versionId"],
        }
        assert (
            client.post("/api/v1/admin/grid-model-default", json=default_command).status_code == 200
        )
        assert client.get("/api/v1/admin/grid-model-default").json()["eligible"] is True
        url = f"/api/v1/admin/games/{c.other}/grid-model-assignment"
        activated = client.post(url + "/activate", json=default_command)
        assert activated.status_code == 200, activated.text
        assert client.post(url + "/activate", json=default_command).json() == activated.json()
        rollback = client.post(url + "/rollback", json={**default_command, "expectedRevision": 1})
        assert rollback.status_code == 409
        assert len(client.get(url + "/history").json()) == 1
        assert len(client.get("/api/v1/admin/grid-model-history").json()) == 2


@pytest.mark.parametrize(
    "problem,code",
    [
        ("base_missing", "GRID_MODEL_EVALUATION_REQUIRED"),
        ("unsupported_contract", "GRID_MODEL_CONTRACT_UNSUPPORTED"),
    ],
)
def test_http_publish_stored_base_missing_and_unsupported_contract_return_controlled_errors(
    controls, problem, code
):
    c = controls
    # Bypass normal registration only to model an incompatible persisted record.
    # This is a synthetic adversarial SQLite fixture, not a public report writer.
    malformed = copy.deepcopy(c.candidate)
    if problem == "base_missing":
        malformed["baseVersionId"] = None
    else:
        malformed["familyId"] = "ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDEF"
    with Session(c.engine) as session:
        stored = session.get(GridModelVersionModel, UUID(c.candidate["versionId"]))
        stored.manifest_json = canonical_json(malformed)
        stored.manifest_sha256 = descriptor_sha256(malformed)
        if problem == "base_missing":
            stored.base_version_id = None
        evaluation = seed_report(session, malformed, [c.game])
        session.commit()
    with control_http_client(c) as client:
        response = client.post(
            f"/api/v1/admin/grid-model-versions/{c.candidate['versionId']}/publish",
            json={
                "idempotencyKey": str(uuid4()),
                "expectedRevision": 0,
                "evaluationId": str(evaluation),
            },
        )
        assert response.status_code == 409, response.text
        assert response.json()["code"] == code
    with Session(c.engine) as session:
        assert session.scalar(select(GridModelPublicationModel)) is None
        assert session.scalar(select(GridModelControlEventModel)) is None


def test_idempotency_namespaces_are_global_and_separate_for_each_game(controls):
    c = controls
    key = uuid4()
    publication = {"idempotencyKey": str(key), "expectedRevision": 0}
    with control_http_client(c) as client:
        url = f"/api/v1/admin/grid-model-versions/{c.baseline['versionId']}/publish"
        published = client.post(url, json=publication)
        assert published.status_code == 200
        assert client.post(url, json=publication).json() == published.json()
        # publish/default share a global namespace, so changing operation conflicts.
        command = {**publication, "versionId": c.baseline["versionId"]}
        conflict = client.post("/api/v1/admin/grid-model-default", json=command)
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "GRID_MODEL_IDEMPOTENCY_CONFLICT"
        for game, revision in ((c.game, 1), (c.other, 0)):
            # The same UUID is independent in each game's namespace.
            assignment = {**command, "expectedRevision": revision}
            target = f"/api/v1/admin/games/{game}/grid-model-assignment/activate"
            activated = client.post(target, json=assignment)
            assert activated.status_code == 200, activated.text
            assert activated.json()["gameId"] == str(game)
            assert client.post(target, json=assignment).json() == activated.json()
            conflict = client.post(
                target, json={**assignment, "versionId": c.candidate["versionId"]}
            )
            assert conflict.status_code == 409
            assert conflict.json()["code"] == "GRID_MODEL_IDEMPOTENCY_CONFLICT"
        assert len(client.get("/api/v1/admin/grid-model-history").json()) == 1
