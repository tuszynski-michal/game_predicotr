"""Synthetic contract/evidence cases; these tests do not qualify a real model."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.grid_model_registry import canonical_json, descriptor_sha256
from game_predictor_api.domain.neural_grid_operation_pin import (
    CAPABILITY_PREFLIGHT_POLICY,
    GAME_EVALUATION_REQUIRED,
    OPERATION_PIN_KEY,
    NeuralOperationPinError,
    make_operation_pin,
    model_capabilities,
    require_operation_pin,
)
from game_predictor_api.domain.neural_grid_proposal import NeuralGridSnapshot
from game_predictor_api.domain.v3_engine_acceptance import (
    GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
    V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY,
    pin_v3_engine_acceptance_policy,
    qualify_v3_engine_acceptance,
)
from game_predictor_worker.images.neural_pending_geometry import neural_pending_payload
from test_v3_engine_acceptance import facts


def unqualified_pin(snapshot, game_id):
    return make_operation_pin(
        snapshot=snapshot,
        game_id=game_id,
        rules_version_id=str(uuid4()),
        rows=3,
        columns=5,
        qualification={"state": "unqualified", "reasonCodes": [GAME_EVALUATION_REQUIRED]},
    )


def resolve_unqualified_operation_pin(*, game_id, model_snapshot, rules_version_id, rows, columns):
    return make_operation_pin(
        snapshot=NeuralGridSnapshot.from_payload(model_snapshot),
        game_id=str(game_id),
        rules_version_id=str(rules_version_id),
        rows=rows,
        columns=columns,
        qualification={"state": "unqualified", "reasonCodes": [GAME_EVALUATION_REQUIRED]},
    )


def test_capability_adapter_keeps_snapshot_bytes_and_sequence_limit_separate():
    snapshot = NeuralGridSnapshot.from_payload(facts()["model_snapshot"])
    before = canonical_json(snapshot.to_payload())
    capabilities = model_capabilities(snapshot)
    assert (capabilities["boardRows"], capabilities["boardColumns"]) == (3, 5)
    assert (capabilities["pageRows"], capabilities["pageColumns"]) == (3, 3)
    assert model_capabilities(replace(snapshot, expected_layout_count=20)) == capabilities
    assert canonical_json(snapshot.to_payload()) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("boardRows", 5),
        ("boardColumns", 3),
        ("boardRows", 3.0),
        ("gameId", str(uuid4())),
        ("modelVersionId", str(uuid4())),
        ("contractVersion", "unknown"),
        ("pinSha256", "0" * 64),
    ],
)
def test_forged_pin_rejected_even_when_rehashed(field, value):
    data = facts()
    snapshot = NeuralGridSnapshot.from_payload(data["model_snapshot"])
    pin = unqualified_pin(snapshot, data["game_id"])
    pin[field] = value
    if field != "pinSha256":
        pin["pinSha256"] = descriptor_sha256({k: v for k, v in pin.items() if k != "pinSha256"})
    with pytest.raises(NeuralOperationPinError):
        require_operation_pin(pin, snapshot=snapshot, game_id=data["game_id"])


def test_new_policy_requires_pin_and_binds_its_fingerprint():
    data = facts()
    snapshot = NeuralGridSnapshot.from_payload(data["model_snapshot"])
    payload = {"neural_grid_proposal": data["model_snapshot"]}
    with pytest.raises(NeuralOperationPinError):
        pin_v3_engine_acceptance_policy(payload, "a" * 64)
    payload[OPERATION_PIN_KEY] = unqualified_pin(snapshot, data["game_id"])
    digest = pin_v3_engine_acceptance_policy(payload, "a" * 64)
    assert payload[V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY] == GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY
    assert pin_v3_engine_acceptance_policy(deepcopy(payload), "a" * 64) == digest


def test_actual_job_response_preserves_v3_without_serializing_internal_pin():
    from game_predictor_api.domain.jobs import JobType, create_job
    from game_predictor_api.schemas.jobs import JobResponse

    data = facts()
    pin = unqualified_pin(NeuralGridSnapshot.from_payload(data["model_snapshot"]), data["game_id"])
    job = create_job(
        JobType.IMAGE_GRID_REINFERENCE,
        game_id=UUID(data["game_id"]),
        input_payload={
            "schema_version": 3,
            "inference_kind": "grid-reinference-v1",
            "operation_id": str(uuid4()),
            "model_snapshot": data["model_snapshot"],
            "runtime_policy": "grid-reinference-runtime-v1",
            "acceptance_policy": GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
            "stats_policy": "grid-reinference-stats-v1",
            OPERATION_PIN_KEY: pin,
        },
    )
    response = JobResponse.from_domain(job).model_dump(mode="json", by_alias=True)
    assert response["inputPayload"]["acceptancePolicy"] == GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY
    assert "neuralGridOperationPin" not in response["inputPayload"]
    assert "statsPolicy" not in response["inputPayload"]
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        JobResponse.from_domain(replace(job, input_payload={**job.input_payload, "unknown": True}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_manifest_sha256", "c" * 64),
        ("source_selection_id", str(uuid4())),
        ("previous_job_id", str(uuid4())),
        ("canonical_sequence_numbers", [106]),
        ("source_display_name", "changed user label"),
        ("managed_source_job_id", str(uuid4())),
    ],
)
def test_changed_stable_input_cannot_reuse_frozen_pin(field, value):
    from game_predictor_api.application.jobs import JobService
    from game_predictor_api.domain.jobs import JobError, JobType, create_job
    from test_jobs_domain import MemoryJobRepository

    data = facts()
    game = UUID(data["game_id"])
    pin = unqualified_pin(NeuralGridSnapshot.from_payload(data["model_snapshot"]), str(game))
    stable = {
        "schema_version": 7,
        "import_kind": "image_directory",
        "neural_grid_proposal": data["model_snapshot"],
        "source_manifest_sha256": "b" * 64,
        "source_selection_id": str(uuid4()),
        "previous_job_id": None,
        "canonical_sequence_numbers": [],
        "source_display_name": "user label",
        "managed_source_job_id": None,
    }
    repository = MemoryJobRepository(game)
    repository.list_jobs = Mock(side_effect=AssertionError("No bounded history scan is allowed."))
    repository.add_job(
        create_job(
            JobType.IMPORT,
            game_id=game,
            input_payload={
                **stable,
                OPERATION_PIN_KEY: pin,
                V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY: GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
                "pipeline_fingerprint": "a" * 64,
            },
        )
    )
    service = JobService(repository)
    replay = deepcopy(stable)
    service._pin_neural_operation(game, replay)
    assert replay[OPERATION_PIN_KEY] == pin
    with pytest.raises(JobError, match="operation pin resolver is unavailable"):
        service._pin_neural_operation(game, {**stable, field: value})


@pytest.mark.parametrize("ambiguous", [False, True])
def test_exact_repository_lookup_has_no_ten_thousand_history_window(ambiguous):
    """A targeted query returns the old exact match regardless of unrelated history size."""
    from game_predictor_api.application.jobs import JobService
    from game_predictor_api.domain.jobs import JobConflictError
    from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository

    data = facts()
    pin = unqualified_pin(NeuralGridSnapshot.from_payload(data["model_snapshot"]), data["game_id"])
    session = Mock()
    session.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    session.execute.return_value.scalars.return_value.all.return_value = (
        [pin, pin] if ambiguous else [pin]
    )
    repository = SqlAlchemyJobRepository(session)
    repository.list_jobs = Mock(
        side_effect=AssertionError("An exact old match must not depend on a 10000-job window.")
    )
    resolver = SimpleNamespace(
        resolve_neural_operation_pin=Mock(
            side_effect=AssertionError("Frozen lookup precedes any new report.")
        )
    )
    service = JobService(repository, grid_profile_snapshot_resolver=resolver)
    payload = {
        "schema_version": 7,
        "neural_grid_proposal": data["model_snapshot"],
        "source_display_name": "stable",
    }
    if ambiguous:
        with pytest.raises(JobConflictError) as error:
            service._pin_neural_operation(UUID(data["game_id"]), payload)
        assert error.value.code == "NEURAL_GRID_OPERATION_IDENTITY_AMBIGUOUS"
    else:
        service._pin_neural_operation(UUID(data["game_id"]), payload)
        assert payload[OPERATION_PIN_KEY] == pin
    assert "pg_advisory_xact_lock" in str(session.execute.call_args_list[1].args[0])
    statement, parameters = session.execute.call_args.args
    assert "CAST(:identity AS jsonb)" in str(statement)
    assert parameters["identity"] == canonical_json(
        {
            "schema_version": 7,
            "neural_grid_proposal": data["model_snapshot"],
            "source_display_name": "stable",
        }
    )
    repository.list_jobs.assert_not_called()
    resolver.resolve_neural_operation_pin.assert_not_called()


def test_unqualified_new_game_keeps_proposals_but_worker_and_api_block_automatic():
    data = facts()
    pin = unqualified_pin(NeuralGridSnapshot.from_payload(data["model_snapshot"]), data["game_id"])
    data.update(
        policy=GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY, operation_pin=pin, qualification_blockers=()
    )
    assert GAME_EVALUATION_REQUIRED in qualify_v3_engine_acceptance(**data)
    manual = {
        "sourceChecksumSha256": data["source_checksum_sha256"],
        "canonicalWidth": 500,
        "canonicalHeight": 300,
        "boards": [{}, {}, {}, {}, {}],
        "engineId": "manual",
        "globalInitialization": {},
    }
    entry = {"neuralProposal": data["proposal"], "neuralProposalBinding": data["binding"]}
    result = neural_pending_payload(
        manual,
        entry,
        automatic_crops=True,
        execution_policy="neural-auto-crop-v2",
        engine_acceptance_policy=GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
        operation_pin=pin,
        qualification_blockers=(GAME_EVALUATION_REQUIRED,),
    )
    for board in result["structuredGeometry"]["boards"]:
        assert board["disposition"] == "needs_manual_review"
        assert board["reviewDraftQuad"] is not None
        assert board["finalQuad"] is None
        assert GAME_EVALUATION_REQUIRED in board["reasonCodes"]


def test_v14_rejects_missing_or_unsupported_pin_before_runner(tmp_path):
    from game_predictor_worker.images.neural_page_geometry_preflight import (
        NeuralPageGeometryPreflightHandler,
    )
    from game_predictor_worker.jobs.runtime import JobHandlerError

    from services.worker.tests.test_neural_page_geometry_preflight import (
        Context,
        Models,
        Runner,
        job_fixture,
    )

    job, _ = job_fixture(tmp_path, files=1)
    payload = {**job.input_payload, "preflight_policy_version": CAPABILITY_PREFLIGHT_POLICY}
    runner = Runner([1])
    handler = NeuralPageGeometryPreflightHandler(
        artifact_root=tmp_path, runner=runner, model_store=Models(tmp_path)
    )
    with pytest.raises(JobHandlerError):
        handler(Context(), replace(job, input_payload=payload))
    assert runner.calls == 0
    pin = unqualified_pin(
        NeuralGridSnapshot.from_payload(payload["neural_grid_proposal"]), str(job.game_id)
    )
    pin["boardRows"] = 4
    pin["pinSha256"] = descriptor_sha256({k: v for k, v in pin.items() if k != "pinSha256"})
    payload[OPERATION_PIN_KEY] = pin
    with pytest.raises(JobHandlerError):
        handler(Context(), replace(job, input_payload=payload))
    assert runner.calls == 0


def test_v14_compatible_unqualified_game_produces_only_proposals(tmp_path):
    from game_predictor_worker.images.neural_page_geometry_preflight import (
        NeuralPageGeometryPreflightHandler,
    )

    from services.worker.tests.test_neural_page_geometry_preflight import (
        Context,
        Models,
        Runner,
        job_fixture,
        result,
    )

    job, _ = job_fixture(tmp_path, files=1)
    snapshot = NeuralGridSnapshot.from_payload(job.input_payload["neural_grid_proposal"])
    pin = unqualified_pin(snapshot, str(job.game_id))
    payload = {
        **job.input_payload,
        "preflight_policy_version": CAPABILITY_PREFLIGHT_POLICY,
        OPERATION_PIN_KEY: pin,
    }
    runner, context = Runner([1]), Context()
    handler = NeuralPageGeometryPreflightHandler(
        artifact_root=tmp_path, runner=runner, model_store=Models(tmp_path)
    )
    handler(context, replace(job, input_payload=payload))
    manifest = result(tmp_path, context)
    assert runner.calls == 1
    assert manifest[OPERATION_PIN_KEY] == pin
    assert manifest["version"] == CAPABILITY_PREFLIGHT_POLICY
