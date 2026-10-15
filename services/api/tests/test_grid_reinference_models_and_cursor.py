"""Exercise real reinference model selection, start CAS and SQL target pagination."""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
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
from game_predictor_api.domain.jobs import JobConflictError, JobStatus
from game_predictor_api.storage import grid_profile_snapshot_resolver as resolver_module
from game_predictor_api.storage import grid_reinference as storage
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from game_predictor_api.storage.grid_reinference_models import (
    GridReinferenceOperationModel as Operation,
)
from game_predictor_api.storage.grid_reinference_models import GridReinferenceTargetModel as Target
from game_predictor_api.storage.models import GameModel, JobModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class _Session:
    """Only persistence is isolated; model(), prepare() and execute() stay real."""

    def __init__(self, game: Any) -> None:
        self.game = game
        self.operation: Operation | None = None
        self.job: JobModel | None = None

    def get(self, model: Any, key: UUID) -> Any:
        assert model is GameModel and key == self.game.id
        return self.game

    def scalar(self, statement: Any) -> Any:
        entity = statement.column_descriptions[0]["entity"]
        if entity is Operation:
            return self.operation
        assert entity is JobModel
        return self.job

    def add(self, record: Any) -> None:
        if isinstance(record, Operation):
            self.operation = record
        else:
            assert isinstance(record, JobModel)
            self.job = record

    def flush(self) -> None:
        pass


class _Registry:
    def __init__(self, baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
        self.assignment_row = SimpleNamespace(version_id=UUID(baseline["versionId"]), revision=7)
        self.records = {
            UUID(payload["versionId"]): SimpleNamespace(
                id=UUID(payload["versionId"]),
                family_id=UUID(payload["familyId"]),
                version=payload["version"],
                manifest_json=canonical_json(payload),
                manifest_sha256=descriptor_sha256(payload),
            )
            for payload in (baseline, candidate)
        }
        self.publications: dict[UUID, Any] = {}
        self.reports: dict[UUID, Any] = {}
        self.calls: list[tuple[str, UUID | None]] = []

    def lock(self) -> None:
        self.calls.append(("lock", None))

    def assignment(self, game_id: UUID) -> tuple[Any, int]:
        self.calls.append(("assignment", game_id))
        return self.assignment_row, 1

    def version(self, version_id: UUID) -> Any:
        self.calls.append(("version", version_id))
        return self.records.get(version_id)

    def publication(self, version_id: UUID) -> Any:
        self.calls.append(("publication", version_id))
        return self.publications.get(version_id)

    def evaluation(self, report_id: UUID) -> tuple[Any, bool]:
        self.calls.append(("evaluation", report_id))
        return self.reports.get(report_id), False


class _AvailableInspector:
    """Synthetic artifact availability only; publication/eligibility code is real."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def inspect(self, payload: dict[str, Any]) -> tuple[bool, str]:
        return True, "GRID_MODEL_ARTIFACT_AVAILABLE"


@pytest.fixture
def context(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    baseline = copy.deepcopy(historical_catalogue()[0])
    candidate = copy.deepcopy(baseline)
    candidate.update(
        versionId=str(uuid4()),
        version="test-v2",
        admission="not_evaluated",
        baseVersionId=baseline["versionId"],
        cohortId=str(uuid4()),
        managedDirectory="models/grid-engine/reinference-test/v2",
    )
    candidate["inferenceManifest"]["version"] = candidate["version"]
    game = SimpleNamespace(
        id=uuid4(),
        code="test-v3",
        shape_geometry_configuration="neural_grid_v3",
        expected_layout_count=1000,
    )
    session = _Session(game)
    registry = _Registry(baseline, candidate)
    repository = storage.SqlAlchemyGridReinferenceRepository(cast(Session, session), Path.cwd())
    monkeypatch.setattr(storage, "SqlAlchemyGridModelRegistryRepository", lambda _session: registry)
    monkeypatch.setattr(
        resolver_module, "SqlAlchemyGridModelRegistryRepository", lambda _session: registry
    )
    monkeypatch.setattr(storage, "GridModelArtifactInspector", _AvailableInspector)
    required_versions: list[str] = []
    monkeypatch.setattr(
        ManagedGridEngineModelStore,
        "require",
        lambda self, version: required_versions.append(version.version),
    )
    monkeypatch.setattr(repository, "bind", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(repository, "key_lock", lambda *_args: None)
    monkeypatch.setattr(storage, "acquire_job_admission", lambda *_args, **_kwargs: None)
    return SimpleNamespace(
        repository=repository,
        session=session,
        registry=registry,
        game=game,
        baseline=baseline,
        candidate=candidate,
        required=required_versions,
    )


def _publish_candidate(context: SimpleNamespace, evaluated_game: UUID) -> None:
    candidate, baseline = context.candidate, context.baseline
    report_id = uuid4()
    payload = {
        "schemaVersion": EVALUATION_SCHEMA,
        "producer": EVALUATION_PRODUCER,
        "policyVersion": EVALUATION_POLICY,
        "versionId": candidate["versionId"],
        "manifestSha256": descriptor_sha256(candidate),
        "baseVersionId": baseline["versionId"],
        "baseManifestSha256": descriptor_sha256(baseline),
        "cohortId": candidate["cohortId"],
        "cohortSha256": "a" * 64,
        "requiredGameIds": [str(evaluated_game)],
        "games": [
            {
                "gameId": str(evaluated_game),
                "validation": "pass",
                "regression": "pass",
                "coverage": "complete",
            }
        ],
    }
    context.registry.reports[report_id] = SimpleNamespace(
        version_id=UUID(candidate["versionId"]),
        report_json=canonical_json(payload),
        report_sha256=descriptor_sha256(payload),
        producer=EVALUATION_PRODUCER,
    )
    evidence = {
        "kind": "evaluated_candidate",
        "evaluationId": str(report_id),
        "evaluationSha256": descriptor_sha256(payload),
        "manifestSha256": descriptor_sha256(candidate),
    }
    context.registry.publications[UUID(candidate["versionId"])] = SimpleNamespace(
        evaluation_id=report_id,
        evidence_json=canonical_json(evidence),
        evidence_sha256=descriptor_sha256(evidence),
    )


def test_historical_code_seven_is_rejected_before_configuration(context: SimpleNamespace) -> None:
    class HistoricalGame:
        id = context.game.id
        code = "7"

        @property
        def shape_geometry_configuration(self) -> str:
            raise AssertionError("Historical code must be rejected before reading configuration")

    context.session.game = HistoricalGame()
    with pytest.raises(JobConflictError) as caught:
        context.repository.model(context.game.id, None)
    assert caught.value.code == "GRID_REINFERENCE_GAME_PROTECTED"
    assert context.registry.calls == []
    assert context.required == []


def test_non_v3_game_is_rejected_by_real_model_resolution(context: SimpleNamespace) -> None:
    context.game.shape_geometry_configuration = "classic"
    with pytest.raises(JobConflictError) as caught:
        context.repository.model(context.game.id, None)
    assert caught.value.code == "GRID_REINFERENCE_FORMAT_UNSUPPORTED"
    assert context.required == []


@pytest.mark.parametrize("explicit_current", [False, True])
def test_current_unpublished_historical_assignment_works_without_training(
    context: SimpleNamespace, explicit_current: bool
) -> None:
    version = context.baseline["versionId"] if explicit_current else None
    snapshot, revision = context.repository.model(context.game.id, version)
    assert snapshot["catalogueManifest"] == context.baseline
    assert snapshot["catalogueManifestSha256"] == descriptor_sha256(context.baseline)
    assert snapshot["gameId"] == str(context.game.id)
    assert revision == 7
    assert context.registry.publications == {}
    assert not any(name == "publication" for name, _ in context.registry.calls)
    assert context.required == [context.baseline["version"]]


def test_explicit_different_unpublished_version_is_rejected(context: SimpleNamespace) -> None:
    with pytest.raises(GridModelRegistryError) as caught:
        context.repository.model(context.game.id, context.candidate["versionId"])
    assert caught.value.code == "GRID_MODEL_NOT_PUBLISHED"
    assert ("publication", UUID(context.candidate["versionId"])) in context.registry.calls
    assert context.required == []


@pytest.mark.parametrize("game_is_eligible", [False, True])
def test_explicit_different_published_version_checks_actual_per_game_evidence(
    context: SimpleNamespace, game_is_eligible: bool
) -> None:
    _publish_candidate(context, context.game.id if game_is_eligible else uuid4())
    if game_is_eligible:
        snapshot, revision = context.repository.model(
            context.game.id, context.candidate["versionId"]
        )
        assert snapshot["catalogueManifest"] == context.candidate
        assert revision == 7
    else:
        with pytest.raises(GridModelRegistryError) as caught:
            context.repository.model(context.game.id, context.candidate["versionId"])
        assert caught.value.code == "GRID_MODEL_EVALUATION_REQUIRED"
    assert any(name == "evaluation" for name, _ in context.registry.calls)


def _prepared(context: SimpleNamespace) -> Operation:
    context.repository.prepare(
        context.game.id,
        {
            "idempotencyKey": str(uuid4()),
            "selector": {"categories": ["grid_issue", "deferred"]},
            "executionScope": "pilot",
        },
        "operator",
    )
    record = context.session.operation
    record.document = {**record.document, "state": "prepared", "manifestSha256": "b" * 64}
    context.session.job.status = JobStatus.WAITING_FOR_REVIEW
    context.repository.execute(
        context.game.id,
        record.id,
        "freeze",
        {
            "idempotencyKey": str(uuid4()),
            "expectedRevision": record.document["revision"],
            "manifestSha256": record.document["manifestSha256"],
        },
        "operator",
    )
    return cast(Operation, record)


@pytest.mark.parametrize("drift", ["revision", "version"])
def test_assignment_drift_after_real_prepare_conflicts_at_start(
    context: SimpleNamespace, drift: str
) -> None:
    record = _prepared(context)
    document, payload = (
        copy.deepcopy(record.document),
        copy.deepcopy(context.session.job.input_payload),
    )
    if drift == "revision":
        context.registry.assignment_row.revision += 1
    else:
        context.registry.assignment_row.version_id = UUID(context.candidate["versionId"])
    with pytest.raises(JobConflictError) as caught:
        context.repository.execute(
            context.game.id,
            record.id,
            "start",
            {
                "idempotencyKey": str(uuid4()),
                "expectedRevision": record.document["revision"],
                "manifestSha256": record.document["manifestSha256"],
            },
            "operator",
        )
    assert caught.value.code == "GRID_REINFERENCE_MODEL_CONFLICT"
    assert record.document == document
    assert context.session.job.input_payload == payload
    assert context.session.job.status is JobStatus.WAITING_FOR_REVIEW


def test_real_start_replay_and_resume_keep_pins_after_later_assignment_change(
    context: SimpleNamespace,
) -> None:
    record = _prepared(context)
    model = copy.deepcopy(record.document["modelSnapshot"])
    payload = copy.deepcopy(context.session.job.input_payload)
    command = {
        "idempotencyKey": str(uuid4()),
        "expectedRevision": record.document["revision"],
        "manifestSha256": record.document["manifestSha256"],
    }
    started = context.repository.execute(context.game.id, record.id, "start", command, "operator")
    context.registry.assignment_row.version_id = UUID(context.candidate["versionId"])
    context.registry.assignment_row.revision += 1
    calls = list(context.registry.calls)
    assert (
        context.repository.execute(context.game.id, record.id, "start", command, "operator")
        == started
    )
    record.document = {**record.document, "state": "failed", "processedSources": 1}
    context.session.job.status = JobStatus.FAILED
    resumed = context.repository.execute(
        context.game.id,
        record.id,
        "resume",
        {
            "idempotencyKey": str(uuid4()),
            "expectedRevision": record.document["revision"],
            "expectedPhase": "infer",
        },
        "operator",
    )
    assert resumed["state"] == "queued"
    assert record.document["processedSources"] == 1
    assert record.document["modelSnapshot"] == model
    assert record.document["startSha256"] == record.document["freezeSha256"] == "b" * 64
    assert context.session.job.input_payload == payload
    assert context.registry.calls == calls


def test_legacy_prepare_replay_and_resume_never_add_stats_pin(context: SimpleNamespace) -> None:
    record = _prepared(context)
    record.document = {
        key: value
        for key, value in record.document.items()
        if key not in {"statsPolicy", "scopeStats", "effectStats"}
    }
    context.session.job.input_payload = {
        key: value
        for key, value in context.session.job.input_payload.items()
        if key != "stats_policy"
    }
    original = copy.deepcopy(record.document)
    replay = context.repository.prepare(context.game.id, record.document["command"], "operator")
    assert replay["scopeStats"] is None and replay["statsPolicy"] is None
    assert record.document == original
    started = context.repository.execute(
        context.game.id,
        record.id,
        "start",
        {
            "idempotencyKey": str(uuid4()),
            "expectedRevision": record.document["revision"],
            "manifestSha256": record.document["manifestSha256"],
        },
        "operator",
    )
    record.document = {**record.document, "state": "failed"}
    context.session.job.status = JobStatus.FAILED
    context.repository.execute(
        context.game.id,
        record.id,
        "resume",
        {
            "idempotencyKey": str(uuid4()),
            "expectedRevision": record.document["revision"],
            "expectedPhase": "infer",
        },
        "operator",
    )
    assert started["manifestSha256"] == original["manifestSha256"]
    assert "statsPolicy" not in record.document
    assert "stats_policy" not in context.session.job.input_payload


@pytest.mark.parametrize("side", ["operation", "job", "both_unknown"])
def test_real_resume_fails_closed_on_mixed_or_unknown_stats_pins(
    context: SimpleNamespace, side: str
) -> None:
    record = _prepared(context)
    if side == "operation":
        record.document = {
            key: value for key, value in record.document.items() if key != "statsPolicy"
        }
    elif side == "job":
        context.session.job.input_payload = {
            key: value
            for key, value in context.session.job.input_payload.items()
            if key != "stats_policy"
        }
    else:
        record.document = {**record.document, "statsPolicy": "future"}
        context.session.job.input_payload = {
            **context.session.job.input_payload,
            "stats_policy": "future",
        }
    record.document = {**record.document, "state": "failed"}
    context.session.job.status = JobStatus.FAILED
    before = copy.deepcopy(record.document)
    with pytest.raises(JobConflictError) as error:
        context.repository.execute(
            context.game.id,
            record.id,
            "resume",
            {
                "idempotencyKey": str(uuid4()),
                "expectedRevision": record.document["revision"],
                "expectedPhase": "prepare",
            },
            "operator",
        )
    assert error.value.code == "GRID_REINFERENCE_PAYLOAD_INVALID"
    assert record.document == before


@pytest.fixture
def target_pages(monkeypatch: pytest.MonkeyPatch) -> Any:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE grid_reinference_operations (
            game_id CHAR(32),id CHAR(32),idempotency_key CHAR(32),command_sha256 VARCHAR(64),
            job_id CHAR(32),document JSON,PRIMARY KEY(game_id,id))""")
        connection.exec_driver_sql("""CREATE TABLE grid_reinference_targets (
            game_id CHAR(32),operation_id CHAR(32),ordinal BIGINT,source_ordinal BIGINT,
            source_image_id CHAR(32),position_index INTEGER,target_result_id CHAR(32),snapshot JSON,
            fingerprint_sha256 VARCHAR(64),outcome VARCHAR(32),result JSON,
            PRIMARY KEY(game_id,operation_id,ordinal))""")
    with Session(engine) as session:
        game, operation, other_operation, other_game = uuid4(), uuid4(), uuid4(), uuid4()
        session.add(
            Operation(
                game_id=game,
                id=operation,
                idempotency_key=uuid4(),
                command_sha256="a" * 64,
                job_id=uuid4(),
                document={"manifestSha256": "c" * 64},
            )
        )
        expected = [11, 13, 19, 21, 25]
        for owner, op, ordinal in [(game, operation, item) for item in expected] + [
            (game, other_operation, 12),
            (other_game, operation, 14),
        ]:
            session.add(
                Target(
                    game_id=owner,
                    operation_id=op,
                    ordinal=ordinal,
                    source_ordinal=ordinal // 10,
                    source_image_id=uuid4(),
                    position_index=ordinal % 10 - 1,
                    target_result_id=uuid4(),
                    snapshot={"frozenOrdinal": ordinal},
                    fingerprint_sha256="a" * 64,
                )
            )
        session.commit()
        repository = storage.SqlAlchemyGridReinferenceRepository(session, Path.cwd())
        monkeypatch.setattr(repository, "bind", lambda *_args, **_kwargs: None)
        yield SimpleNamespace(
            repository=repository,
            game=game,
            operation=operation,
            expected=expected,
            other_game=other_game,
        )
    engine.dispose()


@pytest.mark.parametrize("invalid", ["operation", "sha", "negative", "malformed"])
def test_real_targets_rejects_wrong_cursor_scope(target_pages: Any, invalid: str) -> None:
    op = uuid4() if invalid == "operation" else target_pages.operation
    sha = "d" * 64 if invalid == "sha" else "c" * 64
    cursor = f"{op}:{sha}:{-1 if invalid == 'negative' else 0}"
    if invalid == "malformed":
        cursor = "broken:cursor"
    with pytest.raises(JobConflictError) as caught:
        target_pages.repository.targets(target_pages.game, target_pages.operation, cursor, 2)
    assert caught.value.code == "GRID_REINFERENCE_CURSOR_INVALID"


def test_real_targets_pages_are_ordered_scoped_and_have_no_duplicates(target_pages: Any) -> None:
    cursor = None
    ordinals: list[int] = []
    identifiers: list[str] = []
    for _ in range(5):
        page = target_pages.repository.targets(target_pages.game, target_pages.operation, cursor, 2)
        assert len(page["items"]) <= 2
        ordinals.extend(item["ordinal"] for item in page["items"])
        identifiers.extend(item["targetResultId"] for item in page["items"])
        cursor = page["nextCursor"]
        if cursor is None:
            break
        assert cursor.startswith(f"{target_pages.operation}:{'c' * 64}:")
    assert cursor is None
    assert ordinals == target_pages.expected
    assert len(identifiers) == len(set(identifiers)) == len(target_pages.expected)
    with pytest.raises(JobConflictError) as caught:
        target_pages.repository.targets(target_pages.other_game, target_pages.operation, None, 2)
    assert caught.value.code == "GRID_REINFERENCE_NOT_FOUND"
