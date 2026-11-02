"""Durable apply crash gaps, independent steps, CAS and actual-assigned evidence."""

import json
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest
from game_predictor_api.application import grid_correction_apply as module
from game_predictor_api.application.grid_correction_apply import (
    APPLY_KIND,
    GridCorrectionApplyService,
    apply_key,
)
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.schemas.jobs import GridCorrectionApplyJobPayload, _payload_from_domain
from pydantic import ValidationError

GAME, OTHER, LEARNING, BASE, VERSION, REPORT, EVALUATION, COHORT = (
    UUID(int=x) for x in range(1, 9)
)


def preview_value(additional=False):
    targets = [
        {
            "gameId": str(GAME),
            "gameLabel": "A2",
            "assignmentRevision": 2,
            "assignedVersionId": str(BASE),
            "requiresComparison": False,
        }
    ]
    if additional:
        targets.append(
            {
                "gameId": str(OTHER),
                "gameLabel": "B2",
                "assignmentRevision": 4,
                "assignedVersionId": str(BASE),
                "requiresComparison": False,
            }
        )
    return {
        "gameId": str(GAME),
        "learningId": str(LEARNING),
        "versionId": str(VERSION),
        "versionLabel": "candidate",
        "baseVersionId": str(BASE),
        "defaultVersionId": str(BASE),
        "defaultRevision": 5,
        "additionalGameIds": [str(OTHER)] if additional else [],
        "requiredGameIds": [str(GAME)],
        "targets": targets,
        "excludedGameIds": [],
        "limitations": [],
        "evidenceLevel": "photo-only",
        "blockers": [],
        "canApply": True,
        "previewSha256": "a" * 64,
    }


def pins_value():
    return {
        "versionId": str(VERSION),
        "manifestSha256": "b" * 64,
        "reportId": str(REPORT),
        "reportSha256": "c" * 64,
        "evaluationId": str(EVALUATION),
        "scope": {"currentGameId": str(GAME)},
        "cohorts": [{"gameId": str(GAME), "cohortId": str(COHORT), "manifestSha256": "d" * 64}],
    }


def parent(preview=None):
    return create_job(
        JobType.GRID_CORRECTION_LEARNING,
        game_id=GAME,
        input_payload={
            "schema_version": 1,
            "learning_kind": APPLY_KIND,
            "idempotency_key": str(UUID(int=20)),
            "learning_id": str(LEARNING),
            "actor": "fixture:1122",
            "command": {},
            "preview": preview or preview_value(),
            "pins": pins_value(),
        },
    )


class Catalogue:
    """Independent catalogue state survives replacement of the parent/service objects."""

    def __init__(self):
        self.head = SimpleNamespace(version_id=BASE, revision=5)
        self.assignments = {
            GAME: SimpleNamespace(version_id=BASE, revision=2),
            OTHER: SimpleNamespace(version_id=BASE, revision=4),
        }
        self.receipts = {}
        self.mutations = []
        self.locks = 0
        self.fail_game = None
        self.published = None

    def lock(self):
        self.locks += 1

    def default(self):
        return self.head

    def assignment(self, game):
        return self.assignments.get(game), 0

    def control_receipt(self, key, game):
        receipt = self.receipts.get((key, game))
        return None if receipt is None else SimpleNamespace(receipt_json=json.dumps(receipt))

    def publication(self, version):
        assert version == VERSION
        return self.published

    def execute(self, **command):
        key, game = command["key"], command["game_id"]
        if (key, game) in self.receipts:
            return deepcopy(self.receipts[key, game])
        kind = command["kind"]
        if kind == "publish":
            if self.published is not None:
                raise GridModelRegistryError("GRID_MODEL_REVISION_CONFLICT", "Already published.")
            assert command["expected_revision"] == 0
            publish_matching(self)
        if kind == "activate" and game == self.fail_game:
            raise GridCohortError("FIXTURE_TRANSIENT_FAILURE", "Retry this step.")
        revision = command["expected_revision"] + 1
        if kind == "set_default":
            assert self.head.revision == command["expected_revision"]
            self.head = SimpleNamespace(version_id=command["version_id"], revision=revision)
        if kind == "activate":
            assert self.assignments[game].revision == command["expected_revision"]
            self.assignments[game] = SimpleNamespace(
                version_id=command["version_id"], revision=revision
            )
        receipt = {
            "kind": kind,
            "gameId": None if game is None else str(game),
            "versionId": str(command["version_id"]),
            "revision": revision,
            "idempotencyKey": str(key),
        }
        self.receipts[key, game] = receipt
        self.mutations.append((kind, game))
        return deepcopy(receipt)


class ReadSession:
    def __init__(self, *args):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def begin(self):
        return nullcontext()

    def execute(self, query, *args):
        assert not getattr(query, "_for_update_arg", None)
        return SimpleNamespace(
            one=lambda: SimpleNamespace(code="A2", shape_geometry_configuration="neural_grid_v3")
        )

    def scalar(self, query):
        return None


def publish_matching(catalogue):
    pins = pins_value()
    evidence = {
        "kind": "evaluated_candidate",
        "evaluationId": pins["reportId"],
        "evaluationSha256": pins["reportSha256"],
        "manifestSha256": pins["manifestSha256"],
    }
    catalogue.published = SimpleNamespace(
        evaluation_id=REPORT,
        evidence_json=canonical_json(evidence),
        evidence_sha256=descriptor_sha256(evidence),
    )


def service_for(monkeypatch, tmp_path, catalogue):
    service = GridCorrectionApplyService(None, None, tmp_path)
    registry = SimpleNamespace(
        repository=catalogue, control=SimpleNamespace(execute=catalogue.execute)
    )
    monkeypatch.setattr(module, "Session", ReadSession)
    monkeypatch.setattr(service, "_registry", lambda session: registry)
    pins = pins_value()
    monkeypatch.setattr(
        service,
        "_evidence",
        lambda *args: (
            None,
            {
                "manifestSha256": pins["manifestSha256"],
                "manifest": {"versionId": str(VERSION), "version": "candidate"},
            },
            {"scope": pins["scope"], "cohorts": pins["cohorts"], "requiredGameIds": [str(GAME)]},
            SimpleNamespace(id=REPORT, report_sha256=pins["reportSha256"]),
        ),
    )
    return service, registry


def test_lost_responses_at_every_control_step_recover_original_receipts(monkeypatch, tmp_path):
    catalogue, job = Catalogue(), parent()
    for expected_kind in ("publish", "set_default", "activate"):
        service, _ = service_for(monkeypatch, tmp_path, catalogue)
        state, _ = service.advance(job)
        assert catalogue.mutations[-1][0] == expected_kind
        # Drop the new checkpoint: catalogue committed, then response/process was lost.
        fresh_service, _ = service_for(monkeypatch, tmp_path, catalogue)
        recovered, finished = fresh_service.advance(replace(job))
        assert recovered == state
        assert (
            len(catalogue.mutations)
            == ("publish", "set_default", "activate").index(expected_kind) + 1
        )
        job = replace(job, checkpoint_payload=recovered)
    assert finished
    assert [step["status"] for step in state["steps"]] == ["completed"] * 3
    assert catalogue.head.version_id == VERSION
    assert catalogue.assignments[GAME].version_id == VERSION
    assert catalogue.mutations == [("publish", None), ("set_default", None), ("activate", GAME)]


def test_get_reconciles_receipt_checkpoint_gap_when_foreign_default_prevents_resume(
    monkeypatch, tmp_path
):
    catalogue, job = Catalogue(), parent()
    service, _ = service_for(monkeypatch, tmp_path, catalogue)
    service.advance(job)  # Discard checkpoint after publication commits.
    catalogue.head = SimpleNamespace(version_id=OTHER, revision=8)
    view = service._view(None, job)
    assert view["steps"][0]["status"] == "completed"
    assert view["steps"][0]["receipt"]["kind"] == "publish"
    assert view["steps"][1]["status"] == "pending"
    assert job.checkpoint_payload is None  # Read never writes or advances the parent.
    assert catalogue.mutations == [("publish", None)]
    with pytest.raises(GridCohortError, match="global default changed"):
        service.advance(job)


def test_start_replay_after_response_loss_and_resume_retain_same_parent(monkeypatch, tmp_path):
    catalogue, jobs = Catalogue(), {}

    class Repository:
        def __init__(self, session):
            pass

        def add_job(self, job):
            jobs[job.id] = job
            return job

        def get_job_for_update(self, identifier):
            return jobs.get(identifier)

        def save_job(self, job):
            jobs[job.id] = job
            return job

    monkeypatch.setattr(module, "SqlAlchemyJobRepository", Repository)
    monkeypatch.setattr(module.GridCorrectionLearningService, "_lock_step", lambda *args: None)

    def configure():
        service, _ = service_for(monkeypatch, tmp_path, catalogue)
        monkeypatch.setattr(service, "_preview", lambda *args: (preview_value(), pins_value()))
        monkeypatch.setattr(
            service,
            "_active",
            lambda session, game, learning: next(
                (
                    job.id
                    for job in jobs.values()
                    if job.status in {JobStatus.CREATED, JobStatus.PROCESSING}
                ),
                None,
            ),
        )
        monkeypatch.setattr(
            service,
            "_by_key",
            lambda session, game, key: next(
                (job for job in jobs.values() if job.input_payload["idempotency_key"] == str(key)),
                None,
            ),
        )
        return service

    command = {
        "idempotencyKey": str(UUID(int=20)),
        "previewSha256": "a" * 64,
        "additionalGameIds": [],
        "confirmLimitedEvidence": True,
    }
    service = configure()
    started = service.start(GAME, LEARNING, command, "fixture")
    restarted = configure()
    assert restarted.start(GAME, LEARNING, command, "fixture") == started
    assert len(jobs) == 1
    with pytest.raises(GridCohortError, match="another apply command"):
        restarted.start(GAME, LEARNING, {**command, "previewSha256": "f" * 64}, "fixture")
    with pytest.raises(GridCohortError, match="already active apply"):
        restarted.start(
            GAME,
            LEARNING,
            {**command, "idempotencyKey": str(UUID(int=21)), "previewSha256": "f" * 64},
            "fixture",
        )
    identifier = UUID(started["applyId"])
    jobs[identifier] = replace(
        jobs[identifier],
        status=JobStatus.FAILED,
        checkpoint_payload={"steps": restarted._steps(preview_value()), "original": True},
    )
    # A failed workflow cannot block a fresh preview/start after an unrecoverable CAS.
    with pytest.raises(GridCohortError, match="fresh apply preview"):
        restarted.start(
            GAME,
            LEARNING,
            {**command, "idempotencyKey": str(UUID(int=21)), "previewSha256": "f" * 64},
            "fixture",
        )
    resumed = restarted.resume(GAME, LEARNING, identifier, "fixture")
    assert resumed["applyId"] == started["applyId"] and resumed["status"] == "created"
    assert jobs[identifier].checkpoint_payload["original"]
    assert len(jobs) == 1
    for status in (JobStatus.CREATED, JobStatus.PROCESSING, JobStatus.COMPLETED):
        jobs[identifier] = replace(jobs[identifier], status=status)
        response = restarted.resume(GAME, LEARNING, identifier, "fixture")
        assert response["status"] == status.value
        assert jobs[identifier].checkpoint_payload["original"]


def install_learning(monkeypatch):
    learning = SimpleNamespace(
        input_payload={"preview": {"baseVersionId": str(BASE), "exclusions": []}},
        checkpoint_payload={"candidateVersionId": str(VERSION), "evaluationId": str(EVALUATION)},
    )
    monkeypatch.setattr(module.GridCorrectionLearningService, "_job", lambda *args: learning)
    monkeypatch.setattr(module, "uses_neural_grid", lambda config: True)


def test_manually_published_candidate_is_adopted_with_a_durable_receipt(monkeypatch, tmp_path):
    catalogue = Catalogue()
    publish_matching(catalogue)
    service, _ = service_for(monkeypatch, tmp_path, catalogue)
    install_learning(monkeypatch)
    preview = service.preview(GAME, LEARNING, [])
    assert preview["canApply"]
    job = parent(preview)
    state, _ = service.advance(job)
    receipt = state["steps"][0]["receipt"]
    assert receipt["kind"] == "already-published"
    assert receipt["evaluationId"] == str(REPORT)
    assert receipt["evaluationSha256"] == pins_value()["reportSha256"]
    assert receipt["manifestSha256"] == pins_value()["manifestSha256"]
    assert receipt["idempotencyKey"] == str(apply_key(job.id, "publish"))
    assert not catalogue.mutations
    # Lost checkpoint/response reconstructs the exact receipt without a second publish.
    assert service.advance(replace(job))[0] == state
    assert service._view(None, job)["steps"][0]["receipt"] == receipt
    job = replace(job, checkpoint_payload=state)
    for _ in range(2):
        state, finished = service.advance(job)
        job = replace(job, checkpoint_payload=state)
    assert finished
    assert catalogue.mutations == [("set_default", None), ("activate", GAME)]


def test_published_partial_apply_allows_fresh_preview_after_same_base_revision(
    monkeypatch, tmp_path
):
    catalogue, old = Catalogue(), parent()
    service, _ = service_for(monkeypatch, tmp_path, catalogue)
    state, _ = service.advance(old)
    old = replace(old, status=JobStatus.FAILED, checkpoint_payload=state)
    catalogue.head.revision += 1
    with pytest.raises(GridCohortError, match="global default changed"):
        service.advance(old)
    install_learning(monkeypatch)
    preview = service.preview(GAME, LEARNING, [])
    assert preview["canApply"] and preview["defaultRevision"] == 6
    fresh = parent(preview)
    for _ in range(3):
        state, finished = service.advance(fresh)
        fresh = replace(fresh, checkpoint_payload=state)
    assert finished and state["steps"][0]["receipt"]["kind"] == "already-published"
    assert catalogue.mutations == [("publish", None), ("set_default", None), ("activate", GAME)]


@pytest.mark.parametrize(
    "field",
    ["evaluationId", "evaluationSha256", "manifestSha256", "storedChecksum", "storedEvaluation"],
)
def test_published_with_other_evidence_blocks_preview_and_advance(monkeypatch, tmp_path, field):
    catalogue = Catalogue()
    publish_matching(catalogue)
    if field == "storedChecksum":
        catalogue.published.evidence_sha256 = "f" * 64
    elif field == "storedEvaluation":
        catalogue.published.evaluation_id = OTHER
    else:
        evidence = json.loads(catalogue.published.evidence_json)
        evidence[field] = str(OTHER) if field == "evaluationId" else "f" * 64
        catalogue.published.evidence_json = canonical_json(evidence)
        catalogue.published.evidence_sha256 = descriptor_sha256(evidence)
    service, _ = service_for(monkeypatch, tmp_path, catalogue)
    install_learning(monkeypatch)
    assert service.preview(GAME, LEARNING, [])["blockers"] == [
        "GRID_APPLY_PUBLICATION_EVIDENCE_CONFLICT"
    ]
    with pytest.raises(GridCohortError) as failure:
        service.advance(parent())
    assert failure.value.code == "GRID_APPLY_PUBLICATION_EVIDENCE_CONFLICT"
    assert not catalogue.mutations


def test_already_default_has_its_own_reason_and_active_apply_blocks_preview(monkeypatch, tmp_path):
    catalogue = Catalogue()
    service, _ = service_for(monkeypatch, tmp_path, catalogue)
    install_learning(monkeypatch)
    monkeypatch.setattr(service, "_active", lambda *args: UUID(int=99))
    assert service.preview(GAME, LEARNING, [])["blockers"] == ["GRID_APPLY_BUSY"]
    catalogue.head.version_id = VERSION
    assert service.preview(GAME, LEARNING, [])["blockers"] == ["GRID_APPLY_ALREADY_DEFAULT"]


def test_existing_publication_never_bypasses_main_report_currentness(monkeypatch, tmp_path):
    catalogue = Catalogue()
    publish_matching(catalogue)
    service, _ = service_for(monkeypatch, tmp_path, catalogue)
    install_learning(monkeypatch)

    def stale(*args):
        raise GridModelRegistryError("GRID_MODEL_EVALUATION_STALE", "The main proof is stale.")

    monkeypatch.setattr(service, "_evidence", stale)
    assert service.preview(GAME, LEARNING, [])["blockers"] == ["GRID_MODEL_EVALUATION_STALE"]
    with pytest.raises(GridModelRegistryError, match="main proof is stale"):
        service.advance(parent())
    assert not catalogue.mutations


@pytest.mark.parametrize("after_default", [False, True])
def test_foreign_default_blocks_all_later_mutations_even_after_own_default(
    monkeypatch, tmp_path, after_default
):
    catalogue, job = Catalogue(), parent()
    service, _ = service_for(monkeypatch, tmp_path, catalogue)
    if after_default:
        for _ in range(2):
            state, _ = service.advance(job)
            job = replace(job, checkpoint_payload=state)
    before = list(catalogue.mutations)
    catalogue.head = SimpleNamespace(version_id=UUID(int=99), revision=8)
    with pytest.raises(GridCohortError, match="global default changed"):
        service.advance(job)
    assert catalogue.mutations == before


def test_assignment_conflict_leaves_publication_default_and_other_successful_game(
    monkeypatch, tmp_path
):
    catalogue, job = Catalogue(), parent(preview_value(additional=True))
    service, _ = service_for(monkeypatch, tmp_path, catalogue)
    for _ in range(3):
        state, _ = service.advance(job)
        job = replace(job, checkpoint_payload=state)
    catalogue.assignments[OTHER] = SimpleNamespace(version_id=BASE, revision=9)
    with pytest.raises(GridCohortError, match="assignment changed"):
        service.advance(job)
    assert catalogue.head.version_id == VERSION
    assert catalogue.assignments[GAME].version_id == VERSION
    assert catalogue.assignments[OTHER].version_id == BASE
    assert [step["status"] for step in job.checkpoint_payload["steps"]] == ["completed"] * 3 + [
        "pending"
    ]


def test_partial_failure_and_retry_performs_only_the_remaining_game(monkeypatch, tmp_path):
    catalogue, job = Catalogue(), parent(preview_value(additional=True))
    service, _ = service_for(monkeypatch, tmp_path, catalogue)
    for _ in range(3):
        state, _ = service.advance(job)
        job = replace(job, checkpoint_payload=state)
    catalogue.fail_game = OTHER
    with pytest.raises(GridCohortError, match="Retry this step"):
        service.advance(job)
    catalogue.fail_game = None
    restarted, _ = service_for(monkeypatch, tmp_path, catalogue)
    state, finished = restarted.advance(replace(job))
    assert finished
    assert catalogue.mutations == [
        ("publish", None),
        ("set_default", None),
        ("activate", GAME),
        ("activate", OTHER),
    ]
    assert all(step["status"] == "completed" for step in state["steps"])


def test_actual_assignment_comparison_waits_before_any_mutation(monkeypatch, tmp_path):
    preview = preview_value()
    preview["targets"][0].update(requiresComparison=True, assignedVersionId=str(OTHER))
    catalogue, job = Catalogue(), parent(preview)
    catalogue.assignments[GAME].version_id = OTHER
    service, _ = service_for(monkeypatch, tmp_path, catalogue)
    calls = []
    monkeypatch.setattr(
        service.evaluations,
        "create_assigned_comparison",
        lambda command: (
            calls.append(command) or {"evaluationId": str(EVALUATION), "status": "processing"}
        ),
    )
    state, finished = service.advance(job)
    assert not finished and not catalogue.mutations
    assert state["waitingForJobId"] == str(EVALUATION)
    assert state["steps"][0]["kind"] == "comparison"
    assert state["steps"][0]["status"] == "waiting"
    assert calls == [
        {
            "idempotencyKey": str(apply_key(job.id, "comparison", str(GAME))),
            "versionId": str(VERSION),
            "gameId": str(GAME),
            "cohortId": str(COHORT),
        }
    ]
    # Changed assignment is rejected before creating/reusing any comparison.
    catalogue.assignments[GAME].revision += 1
    with pytest.raises(GridCohortError, match="assignment changed"):
        service.advance(replace(job, checkpoint_payload=state))
    assert len(calls) == 1 and not catalogue.mutations


def test_preview_is_read_only_and_digest_binds_assignment_default_report_and_full_scope(
    monkeypatch, tmp_path
):
    catalogue = Catalogue()
    service, _ = service_for(monkeypatch, tmp_path, catalogue)
    learning = SimpleNamespace(
        input_payload={
            "preview": {"baseVersionId": str(BASE), "defaultRevision": 5, "exclusions": []}
        },
        checkpoint_payload={"candidateVersionId": str(VERSION), "evaluationId": str(EVALUATION)},
    )
    monkeypatch.setattr(module.GridCorrectionLearningService, "_job", lambda *args: learning)
    monkeypatch.setattr(module, "uses_neural_grid", lambda config: True)
    initial = service.preview(GAME, LEARNING, [])
    assert initial["canApply"] and catalogue.locks == 0 and not catalogue.mutations
    catalogue.assignments[GAME].revision += 1
    changed_assignment = service.preview(GAME, LEARNING, [])
    assert changed_assignment["previewSha256"] != initial["previewSha256"]
    catalogue.head.revision += 1
    changed_revision = service.preview(GAME, LEARNING, [])
    assert (
        changed_revision["canApply"]
        and changed_revision["previewSha256"] != changed_assignment["previewSha256"]
    )
    catalogue.head.version_id = OTHER
    assert service.preview(GAME, LEARNING, [])["blockers"] == ["GRID_APPLY_DEFAULT_CHANGED"]
    catalogue.head.version_id = BASE
    assert service.preview(GAME, LEARNING, [OTHER])["blockers"] == [
        "GRID_APPLY_SCOPE_NOT_EVALUATED"
    ]


def test_apply_payload_is_closed_and_job_response_uses_its_own_discriminator():
    job = parent()
    payload = _payload_from_domain(job)
    assert isinstance(payload, GridCorrectionApplyJobPayload)
    assert payload.learning_kind == APPLY_KIND
    with pytest.raises(ValidationError):
        GridCorrectionApplyJobPayload.model_validate({**job.input_payload, "clientEvidence": {}})


def test_false_photo_only_confirmation_rejected_before_opening_any_session(monkeypatch, tmp_path):
    service = GridCorrectionApplyService(None, None, tmp_path)
    with pytest.raises(GridCohortError, match="Confirm the photo-only"):
        service.start(GAME, LEARNING, {"confirmLimitedEvidence": False}, "fixture")


@pytest.mark.parametrize("problem", ["revision", "checksum", "verdict", "invalidated", "stale"])
def test_assigned_report_requires_pinned_revision_checksum_pass_and_currentness(
    monkeypatch, tmp_path, problem
):
    catalogue = Catalogue()
    service, registry = service_for(monkeypatch, tmp_path, catalogue)
    target = preview_value()["targets"][0]
    target.update(assignedVersionId=str(OTHER), requiresComparison=True)
    pins = pins_value()
    report = {"versionId": str(VERSION), "verdict": "PASS", "cohort": pins["cohorts"][0]}
    row = SimpleNamespace(id=REPORT, version_id=VERSION, report_sha256=descriptor_sha256(report))
    payload = {
        "evaluation_kind": "grid-assigned-comparison-v1",
        "baseline_version_id": str(OTHER),
        "assignment_revision": 2,
        "manifest_sha256": pins["manifestSha256"],
        "version_id": str(VERSION),
    }
    if problem == "revision":
        payload["assignment_revision"] = 3
    if problem == "checksum":
        row.report_sha256 = "f" * 64
    if problem == "verdict":
        report["verdict"] = "REVISE"
        row.report_sha256 = descriptor_sha256(report)
    monkeypatch.setattr(
        service.evaluations,
        "_job",
        lambda *args: SimpleNamespace(status=JobStatus.COMPLETED, input_payload=payload),
    )
    monkeypatch.setattr(service.evaluations, "_report", lambda *args, **kwargs: report)
    catalogue.evaluation = lambda identifier: (row, problem == "invalidated")

    def current(*args):
        if problem == "stale":
            raise GridCohortError("GRID_MODEL_EVALUATION_STALE", "Stale proof.")

    registry.control._require_current = current
    with pytest.raises(GridCohortError):
        service._require_comparison(None, registry, EVALUATION, target, pins)
