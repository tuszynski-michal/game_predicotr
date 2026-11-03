"""Parent composition/replay and strict history boundaries; child computation is substituted."""

import copy
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application import grid_correction_learning as learning
from game_predictor_api.application.grid_correction_history import (
    require_historical_cohort,
    verified_history,
)
from game_predictor_api.domain.grid_correction_evaluation import CHECKPOINT_RULE, build_report
from game_predictor_api.domain.grid_model_publication import require_evaluation_evidence
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
)
from game_predictor_api.domain.jobs import JobType, create_job
from test_grid_correction_evaluation import roles, uid


def test_historical_plan_preserves_original_bases_and_alias_protection():
    from game_predictor_api.domain.shared_grid_model_candidate import (
        SharedCandidateError,
        joint_plan,
    )
    from test_shared_grid_model_candidate import cohort, large, small

    current = cohort("a", small(), base_version_id="new-base")
    previous = cohort("b", large(), base_version_id="old-base")
    with pytest.raises(SharedCandidateError, match="one base"):
        joint_plan("a", [current, previous])
    plan = joint_plan("a", [previous, current], historical=True)
    assert plan["baseVersionId"] == "new-base"
    assert plan["sourceBases"] == {"a": "new-base", "b": "old-base"}
    assert plan["weighting"] == {"games": "equal", "samplingUnits": "equal-within-game"}
    assert plan["evidenceLevel"] == "photo-only"
    alias = replace(
        previous,
        members=(
            replace(previous.members[0], pixel_sha256=current.members[1].pixel_sha256),
            *previous.members[1:],
        ),
    )
    with pytest.raises(SharedCandidateError, match="control photo"):
        joint_plan("a", [current, alias], historical=True)


class Session:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def begin(self):
        return self

    def get(self, *args):
        return self.row[0]

    def execute(self, *args):
        return None


def test_metadata_preview_uses_game_cohort_reader_and_changes_pin_with_population(
    monkeypatch, tmp_path
):
    game, base, family, import_id = [uuid4() for _ in range(4)]
    catalogue = SimpleNamespace(
        default=lambda: SimpleNamespace(version_id=base, revision=3), version=lambda value: object()
    )
    manifest = {
        "versionId": str(base),
        "familyId": str(family),
        "trainingArtifacts": [
            {"name": name} for name in ("weights.pt", "checkpoint.pt", "bundle.json", "preset.json")
        ],
    }
    cohort_reader = SimpleNamespace(bind=lambda value: None)
    monkeypatch.setattr(learning, "Session", lambda *args: Session([None]))
    monkeypatch.setattr(
        learning, "SqlAlchemyGridModelRegistryRepository", lambda session: catalogue
    )
    monkeypatch.setattr(
        learning,
        "GridModelRegistryService",
        lambda *args: SimpleNamespace(
            view=lambda *args, **kwargs: {
                "available": True,
                "manifest": manifest,
                "manifestSha256": "a" * 64,
            }
        ),
    )
    monkeypatch.setattr(
        learning,
        "verified_history",
        lambda *args: {"documented": False, "gameIds": [], "cohorts": []},
    )
    monkeypatch.setattr(
        learning, "SqlAlchemyGridTrainingCohortRepository", lambda *args: cohort_reader
    )
    split = {
        "sha256": "b" * 64,
        "sources": [
            {
                "buffer": index == 0,
                "representative": True,
                "eligibleBoards": 3,
                "role": None
                if index == 0
                else "TRAIN"
                if index <= 10
                else "VALIDATION"
                if index <= 15
                else "REGRESSION",
            }
            for index in range(21)
        ]
        + [{"buffer": False, "representative": False, "eligibleBoards": 3}],
        "roleCounts": [
            {"role": role, "photos": photos, "boards": boards}
            for role, photos, boards in (
                ("TRAIN", 10, 30),
                ("VALIDATION", 5, 15),
                ("REGRESSION", 5, 15),
            )
        ],
    }

    def read(reader, target, imports, deadline):
        assert reader is cohort_reader and target == game and imports == [str(import_id)]
        return split

    monkeypatch.setattr(learning, "prepare_split", read)
    service = learning.GridCorrectionLearningService(None, lambda: Session([None]), tmp_path)
    command = {"importJobIds": [str(import_id)], "exclusions": []}
    first = service.preview(game, command)
    assert first["canStart"], first["blockers"]
    assert first["bufferPhotos"] == 1 and first["pendingWorkerChecks"]
    assert first["dataAvailability"] == {
        "photos": 21,
        "boards": 63,
        "minimumPhotos": 20,
        "minimumBoards": 60,
        "photoDeficit": 0,
        "boardDeficit": 0,
        "splitStatus": "ready",
    }
    assert sum(item["photos"] for item in first["roleCounts"]) == 20
    split["sha256"] = "c" * 64
    assert service.preview(game, command)["previewSha256"] != first["previewSha256"]
    from game_predictor_api.domain.grid_correction_split import CorrectionSplitError

    for code, photos, boards, status in (
        ("GRID_CORRECTION_SPLIT_MINIMA", 7, 21, "minima"),
        ("GRID_CORRECTION_SPLIT_INFEASIBLE", 21, 63, "infeasible"),
    ):

        def failed(*args, code=code, photos=photos, boards=boards):
            raise learning.GridCorrectionSplitPreparationError(
                CorrectionSplitError(code, "No split", photos=photos, boards=boards)
            )

        monkeypatch.setattr(learning, "prepare_split", failed)
        blocked = service.preview(game, command)
        assert blocked["roleCounts"] == [] and not blocked["canStart"]
        assert blocked["dataAvailability"]["photos"] == photos
        assert blocked["dataAvailability"]["boards"] == boards
        assert blocked["dataAvailability"]["splitStatus"] == status
    monkeypatch.setattr(catalogue, "default", lambda: None)
    assert service.preview(game, command)["dataAvailability"] is None


def test_parent_composes_all_steps_and_adopts_children_after_lost_response(monkeypatch, tmp_path):
    game, parent, cohort, run_id, evaluation_id = [uuid4() for _ in range(5)]
    row = [None]
    calls, runs, evaluations = [], {}, {}
    header = {
        "status": "preparing",
        "revision": 1,
        "nextCaptureCursor": 0,
        "nextMaterializationCursor": None,
        "previewSha256": "p" * 64,
        "manifestSha256": "m" * 64,
    }
    preview = {
        "baseVersionId": str(uuid4()),
        "presetId": "grid-corrections-v1",
        "presetFingerprint": "a" * 64,
        "exclusions": [],
        "importJobIds": [str(uuid4())],
    }
    payload = {
        "schema_version": 1,
        "learning_kind": learning.LEARNING_KIND,
        "actor": "fixture",
        "preview": preview,
        "pins": {
            "base": {"familyId": str(uuid4())},
            "splitSha256": "s" * 64,
            "historicalCohorts": [],
        },
    }
    job = replace(
        create_job(JobType.GRID_CORRECTION_LEARNING, game_id=game, input_payload=payload), id=parent
    )
    repository = SimpleNamespace(bind=lambda *args: None, cohort=lambda *args: row[0])

    def prepare(*args):
        calls.append("prepare")
        row[0] = SimpleNamespace(document={"photoSplit": {"sha256": "s" * 64}})

    def command(_game, _cohort, kind, body, _actor):
        calls.append(kind)
        assert body["expectedRevision"] == header["revision"]
        header["revision"] += 1
        if kind == "prepare-page":
            header.update(
                status="preview_ready", nextCaptureCursor=None, nextMaterializationCursor=0
            )
        elif kind == "materialize-page":
            header.update(status="ready_to_freeze", nextMaterializationCursor=None)
        else:
            assert kind == "freeze"
            header["status"] = "frozen"

    cohort_service = SimpleNamespace(
        repository=repository, prepare=prepare, command=command, get=lambda *args: dict(header)
    )

    def training_create(_self, _game, command):
        return runs.setdefault(
            command["idempotencyKey"],
            {"runId": str(run_id), "status": "created", "candidateVersionId": None},
        )

    def evaluation_create(command):
        return evaluations.setdefault(
            command["idempotencyKey"],
            {
                "evaluationId": str(evaluation_id),
                "reportId": str(uuid4()),
                "status": "created",
                "verdict": None,
            },
        )

    monkeypatch.setattr(learning, "Session", lambda *args: Session(row))
    monkeypatch.setattr(learning.GridTrainingRunService, "create", training_create)

    def service():
        value = learning.GridCorrectionLearningService(None, lambda: Session(row), tmp_path)
        value._cohorts = lambda *args: cohort_service
        value._job = lambda *args, **kwargs: job
        value.evaluations = SimpleNamespace(create=evaluation_create)
        return value

    state = {"schema_version": 1}
    for _ in range(4):
        state, finished = service().advance(replace(job, checkpoint_payload=state))
        assert not finished
    assert calls == ["prepare", "prepare-page", "materialize-page", "freeze"]
    before = copy.deepcopy(state)
    state, finished = service().advance(replace(job, checkpoint_payload=state))
    assert state["waitingForJobId"] == str(run_id)
    # Lost response: repeat the same pre-child checkpoint in a fresh service.
    replay, _ = service().advance(replace(job, checkpoint_payload=before))
    assert replay == state and len(runs) == 1
    next(iter(runs.values())).update(status="completed", candidateVersionId=str(uuid4()))
    state, finished = service().advance(replace(job, checkpoint_payload=state))
    assert state["waitingForJobId"] == str(evaluation_id) and not finished
    next(iter(evaluations.values())).update(status="completed", verdict="REVISE")
    state, finished = service().advance(replace(job, checkpoint_payload=state))
    assert finished and state["verdict"] == "REVISE" and "waitingForJobId" not in state
    assert len(runs) == len(evaluations) == 1


def history_fixture():
    manifest = {
        "versionId": uid(1),
        "baseVersionId": uid(2),
        "familyId": uid(3),
        "cohortId": uid(4),
    }
    pin = {"gameId": uid(5), "cohortId": uid(4), "manifestSha256": "c" * 64}
    report = build_report(
        manifest=manifest,
        base_manifest_sha256="b" * 64,
        training_game_id=uid(5),
        parity={"passed": True, "bundleSha256": "a" * 64},
        cohorts=[pin],
        measured={uid(5): {"mode": "grid-only", "roles": roles()}},
        scope={
            "currentGameId": uid(5),
            "trainingGameIds": [uid(5)],
            "priorVerifiedGameIds": [],
            "priorScopeDocumented": False,
            "exclusions": [],
        },
        checkpoint_selection={
            "rule": CHECKPOINT_RULE,
            "role": "VALIDATION",
            "step": 1,
            "metrics": {"boardCorrectRate": 0.8, "normalizedError": 0.02},
            "earlyStopping": {"patience": 4, "evaluationsWithoutImprovement": 0, "stopped": False},
        },
    )
    version = SimpleNamespace(
        manifest_json=canonical_json(manifest), manifest_sha256=descriptor_sha256(manifest)
    )
    row = SimpleNamespace(
        id=UUID(int=7),
        report_json=canonical_json(report),
        report_sha256=descriptor_sha256(report),
        producer=report["producer"],
    )
    repo = SimpleNamespace(
        version=lambda key: version
        if key == UUID(int=1)
        else SimpleNamespace(manifest_sha256="b" * 64),
        publication=lambda key: SimpleNamespace(evaluation_id=row.id),
        evaluation=lambda key: (row, False),
        cohort_currentness=lambda *args: [{"state": "current"}],
        lineage=lambda key: {"ancestors": [{"versionId": uid(2)}]},
    )
    return repo, row, manifest, pin


def test_history_uses_verified_explicit_ids_and_preserves_original_base():
    repo, row, manifest, pin = history_fixture()
    history = verified_history(repo, UUID(int=1))
    assert history["gameIds"] == [uid(5)] and history["cohorts"] == [pin]
    require_historical_cohort(
        repo,
        UUID(int=1),
        {"gameId": uid(5), "id": uid(4), "manifestSha256": "c" * 64, "baseVersionId": uid(2)},
    )
    evidence = require_evaluation_evidence(
        report_id=row.id,
        report_json=row.report_json,
        report_sha256=row.report_sha256,
        producer=row.producer,
        invalidated=False,
        manifest=manifest,
        base_sha256="b" * 64,
        game_id=None,
    )
    assert evidence.scoped and evidence.games == frozenset({UUID(int=5)})
    repo.cohort_currentness = lambda *args: [{"state": "stale"}]
    with pytest.raises(GridModelRegistryError, match="current proof"):
        verified_history(repo, UUID(int=1))


def test_legacy_dataset_labels_are_not_a_game_scope():
    repo, _, _, _ = history_fixture()
    repo.publication = lambda key: SimpleNamespace(evaluation_id=None)
    assert verified_history(repo, UUID(int=1)) == {
        "documented": False,
        "gameIds": [],
        "cohorts": [],
        "reportId": None,
    }
