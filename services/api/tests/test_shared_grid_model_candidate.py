"""TASK-1006 joint policy, shared run creation and the evaluation scope of a shared candidate."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.grid_model_evaluation import GridModelEvaluationService
from game_predictor_api.application.grid_training_runs import GridTrainingRunService
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.domain.shared_grid_model_candidate import (
    JOINT_POLICY,
    SharedCandidateError,
    SharedCohort,
    SharedMember,
    joint_plan,
)
from game_predictor_api.schemas.jobs import GridTrainingJobPayload
from game_predictor_worker.training_core.grid_training_admission import (
    GRID_ONLY_V1,
    CohortCounts,
    estimate_cohort_cost,
)
from test_grid_training_runs import BASE, COHORT, GAME, Cohorts, Jobs

FAMILY, OTHER, OTHER_COHORT = str(uuid4()), UUID(int=7), UUID(int=8)


def member(role: str, index: int, *, group: str | None = None, pixels: str | None = None):
    return SharedMember(
        source_id=f"s{index}",
        role=role,
        group_id=group or f"g{index}",
        checksum_sha256=f"c{index}",
        pixel_sha256=pixels or f"p{index}",
    )


def cohort(game: str, members: tuple[SharedMember, ...], **change: str) -> SharedCohort:
    values = {
        "game_id": game,
        "cohort_id": f"cohort-{game}",
        "manifest_sha256": "a" * 64,
        "family_id": FAMILY,
        "base_version_id": BASE,
        "mode": "grid-only",
        "members": members,
    }
    values.update(change)
    return SharedCohort(**values)  # type: ignore[arg-type]


def small() -> tuple[SharedMember, ...]:
    return (member("TRAIN", 1), member("VALIDATION", 2), member("REGRESSION", 3))


def large() -> tuple[SharedMember, ...]:
    return tuple(member("TRAIN", 100 + i, group=f"big-{i % 4}") for i in range(40)) + (
        member("VALIDATION", 200),
        member("REGRESSION", 201),
    )


def test_the_plan_weighs_every_game_equally_whatever_its_size():
    plan = joint_plan("a", [cohort("a", small()), cohort("b", large())])
    assert plan["policy"] == JOINT_POLICY
    assert plan["weighting"] == {"games": "equal", "recordings": "equal-within-game"}
    assert [(c["gameId"], c["trainPhotos"], c["trainRecordings"]) for c in plan["cohorts"]] == [
        ("a", 1, 1),
        ("b", 40, 4),
    ]
    # Deterministic and bound to the primary game.
    assert plan == joint_plan("a", [cohort("b", large()), cohort("a", small())])
    assert plan["sha256"] != joint_plan("b", [cohort("a", small()), cohort("b", large())])["sha256"]


@pytest.mark.parametrize("identity", ["source", "pixels", "recording"])
def test_a_control_alias_of_one_game_never_trains_the_other(identity):
    control = member("VALIDATION", 2)
    train = {
        "source": SharedMember("x", "TRAIN", "gx", control.checksum_sha256, "px"),
        "pixels": SharedMember("x", "TRAIN", "gx", "cx", control.pixel_sha256),
        "recording": SharedMember("x", "TRAIN", control.group_id, "cx", "px"),
    }[identity]
    b = cohort("b", (train, member("VALIDATION", 9), member("REGRESSION", 10)))
    with pytest.raises(SharedCandidateError) as error:
        joint_plan("a", [cohort("a", small()), b])
    expected = (
        "GRID_SHARED_ROLE_CONFLICT" if identity == "recording" else "GRID_SHARED_CONTROL_ALIAS"
    )
    assert error.value.code == expected
    if identity != "recording":
        assert error.value.details == {
            "trainGameId": "b",
            "controlGameId": "a",
            "identity": identity,
        }


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"family_id": str(uuid4())}, "GRID_SHARED_COHORT_MISMATCH"),
        ({"base_version_id": str(uuid4())}, "GRID_SHARED_COHORT_MISMATCH"),
        ({"mode": "screen+grid"}, "GRID_SHARED_COHORT_MISMATCH"),
        ({"members": (member("VALIDATION", 7),)}, "GRID_SHARED_COHORT_EMPTY_ROLE"),
    ],
)
def test_one_family_base_mode_and_both_roles_are_required(change, code):
    with pytest.raises(SharedCandidateError) as error:
        members = change.pop("members", large())
        joint_plan("a", [cohort("a", small()), cohort("b", members, **change)])
    assert error.value.code == code


def test_scope_needs_two_distinct_games_including_the_primary():
    for cohorts, primary in (
        ([cohort("a", small())], "a"),
        ([cohort("a", small()), cohort("a", large())], "a"),
        ([cohort("a", small()), cohort("b", large())], "c"),
    ):
        with pytest.raises(SharedCandidateError) as error:
            joint_plan(primary, cohorts)
        assert error.value.code == "GRID_SHARED_SCOPE_INVALID"


class Planner:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def prepare(self, game: UUID, cohort_id: UUID, others: list[tuple[UUID, UUID]]):
        self.calls.append((game, cohort_id, list(others)))
        return {
            "plan": {"sha256": "d" * 64},
            "pins": [
                {"game_id": str(o), "cohort_id": str(c), "manifest_sha256": "e" * 64}
                for o, c in others
            ],
            "counts": CohortCounts(
                mode="grid-only", train_boards=60, train_photos=20, train_full_photos=0
            ),
        }


def command(**change: Any) -> dict[str, Any]:
    return {
        "idempotencyKey": str(uuid4()),
        "cohortId": str(COHORT),
        "presetId": GRID_ONLY_V1.preset_id,
        "presetFingerprint": GRID_ONLY_V1.fingerprint,
        "sharedCohorts": [{"gameId": str(OTHER), "cohortId": str(OTHER_COHORT)}],
        **change,
    }


def test_shared_run_pins_the_other_cohorts_and_the_plan_sha_and_replays_exactly():
    planner, jobs = Planner(), Jobs()
    service = GridTrainingRunService(Cohorts(), jobs, planner)
    body = command()
    view = service.create(GAME, body)
    (job,) = jobs.rows.values()
    payload = job.input_payload
    assert payload["training_kind"] == "grid-shared-training-run-v1"
    assert payload["shared_cohorts"] == [
        {"game_id": str(OTHER), "cohort_id": str(OTHER_COHORT), "manifest_sha256": "e" * 64}
    ]
    assert payload["joint_sha256"] == "d" * 64
    # The step plan follows the summed counts of all shared cohorts, not the primary alone.
    expected = estimate_cohort_cost(GRID_ONLY_V1, planner.prepare(GAME, COHORT, [])["counts"])
    assert payload["planned_steps"] == expected.planned_steps != 1200
    GridTrainingJobPayload.model_validate(payload)
    assert view["sharedCohorts"] == [{"gameId": str(OTHER), "cohortId": str(OTHER_COHORT)}]
    assert service.create(GAME, body) == view and len(planner.calls) == 2
    with pytest.raises(GridCohortError, match="another run"):
        service.create(GAME, {**body, "sharedCohorts": []})
    assert job.game_id == GAME and job.job_type is JobType.GRID_TRAINING


def test_shared_run_needs_the_planner_and_single_runs_are_unchanged():
    jobs = Jobs()
    with pytest.raises(GridCohortError) as error:
        GridTrainingRunService(Cohorts(), jobs).create(GAME, command())
    assert error.value.code == "GRID_SHARED_UNAVAILABLE"
    view = GridTrainingRunService(Cohorts(), jobs).create(GAME, command(sharedCohorts=None))
    (job,) = jobs.rows.values()
    assert job.input_payload["training_kind"] == "grid-training-run-v1"
    assert "shared_cohorts" not in job.input_payload and view["sharedCohorts"] == []


def test_a_shared_candidate_is_evaluated_on_every_cohort_it_trained_on():
    shared = create_job(
        JobType.GRID_TRAINING,
        game_id=GAME,
        input_payload={
            "schema_version": 1,
            "training_kind": "grid-shared-training-run-v1",
            "cohort_id": str(COHORT),
            "shared_cohorts": [{"game_id": str(OTHER), "cohort_id": str(OTHER_COHORT)}],
        },
    )
    session = SimpleNamespace(get=lambda _model, key: shared if key == shared.id else None)
    manifest = {"provenance": {"runId": str(shared.id)}}
    assert GridModelEvaluationService._trained_cohorts(session, manifest) == {  # type: ignore[arg-type]
        (str(GAME), str(COHORT)),
        (str(OTHER), str(OTHER_COHORT)),
    }
    for run_id in (str(uuid4()), "historical-run"):
        assert (
            GridModelEvaluationService._trained_cohorts(  # type: ignore[arg-type]
                session, {"provenance": {"runId": run_id}}
            )
            == set()
        )


class Reached(Exception):
    pass


def test_evaluation_create_refuses_a_partial_or_swapped_shared_scope(monkeypatch):
    from game_predictor_api.application import grid_model_evaluation as module
    from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
    from sqlalchemy import create_engine

    trained = {(str(GAME), str(COHORT)), (str(OTHER), str(OTHER_COHORT))}
    manifest = {"familyId": FAMILY, "cohortId": str(COHORT), "provenance": {"runId": "x"}}
    monkeypatch.setattr(GridModelEvaluationService, "_by_key", staticmethod(lambda s, k: None))
    monkeypatch.setattr(
        GridModelEvaluationService, "_candidate", lambda self, s, v: (manifest, "b" * 64)
    )
    monkeypatch.setattr(
        GridModelEvaluationService, "_trained_cohorts", staticmethod(lambda s, m: trained)
    )
    monkeypatch.setattr(module.evidence, "family_games", lambda s, family: set())

    def parity(root, value):
        raise Reached

    monkeypatch.setattr(module, "candidate_parity", parity)
    service = GridModelEvaluationService(create_engine("sqlite://"), None, None)  # type: ignore[arg-type]
    swapped = UUID(int=9)
    for cohorts in (
        [(GAME, COHORT)],
        [(GAME, COHORT), (OTHER, swapped)],
    ):
        body = {
            "idempotencyKey": str(uuid4()),
            "versionId": str(uuid4()),
            "cohorts": [{"gameId": str(g), "cohortId": str(c)} for g, c in cohorts],
        }
        with pytest.raises(GridModelRegistryError) as error:
            service.create(body)
        assert error.value.code == "GRID_EVALUATION_GAME_COHORT_REQUIRED"
        assert error.value.details["cohorts"] == [
            {"gameId": str(OTHER), "cohortId": str(OTHER_COHORT)}
        ]
    complete = {
        "idempotencyKey": str(uuid4()),
        "versionId": str(uuid4()),
        "cohorts": [
            {"gameId": str(GAME), "cohortId": str(COHORT)},
            {"gameId": str(OTHER), "cohortId": str(OTHER_COHORT)},
        ],
    }
    with pytest.raises(Reached):  # the full trained scope passes on to the parity check
        service.create(complete)
