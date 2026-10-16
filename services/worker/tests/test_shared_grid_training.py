"""TASK-1006 shared candidate: balanced sampling, pinned joint plan and the supervisor.

Generated CPU-only snapshots and the fake trainer of the TASK-0996 supervisor tests; no
GPU, no operator data and no real training.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import numpy as np
import pytest
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.domain.shared_grid_model_candidate import SharedCandidateError
from game_predictor_worker.images.grid_shared_candidate import plan_for
from game_predictor_worker.images.grid_training_data import GridOnlyBatches, JointPhotos
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.training_core.grid_training import BalancedSampler
from game_predictor_worker.training_core.grid_training_admission import GRID_ONLY_V1
from PIL import Image
from test_durable_v3_grid_training import FakePhotos, grid, recipe
from test_grid_cohort_dataset import SnapshotFixture
from test_grid_training_handler import BASE, Context, FakeChild, Store, handler

WORKER = Path(__file__).resolve().parents[1] / "src" / "game_predictor_worker"
API = Path(__file__).resolve().parents[2] / "api" / "src" / "game_predictor_api"


def test_a_large_game_never_dominates_and_recordings_weigh_the_same():
    small = ((0, 1, 2, 3, 4),)
    large = tuple(tuple(range(5 + 25 * r, 30 + 25 * r)) for r in range(4))
    sampler = BalancedSampler((small, large), batch=4, seed=11)
    drawn = [index for step in range(200) for index in sampler.indices(step)]
    games = Counter("small" if index < 5 else "large" for index in drawn)
    assert games == {"small": 400, "large": 400}
    recordings = Counter((index - 5) // 25 for index in drawn if index >= 5)
    assert set(recordings.values()) == {100}
    # A pure function of (seed, step): a resumed sampler continues identically.
    again = BalancedSampler((small, large), batch=4, seed=11)
    assert [again.indices(step) for step in (7, 3)] == [sampler.indices(step) for step in (7, 3)]
    assert sampler.size == 105
    with pytest.raises(ValueError, match="GRID_TRAINING_EMPTY_DATASET"):
        BalancedSampler((small, ()), batch=1, seed=1)


class Part(FakePhotos):
    def __init__(self, count: int, prefix: str) -> None:
        super().__init__([[(grid(30), 4)] for _ in range(count)])
        self.rows = [({"sourceId": f"{prefix}{i}"}, None) for i in range(count)]


def test_joint_photos_feed_balanced_batches_from_every_game():
    small, large = Part(2, "a"), Part(30, "b")
    groups = [{"a0": "ga", "a1": "ga"}, {f"b{i}": f"gb{i % 3}" for i in range(30)}]
    joint = JointPhotos([small, large], groups)
    assert len(joint) == 32 and joint.strata[0] == ((0, 1),)
    assert [len(recording) for recording in joint.strata[1]] == [10, 10, 10]
    assert joint.targets(31) == large.targets(29)
    batches = GridOnlyBatches(
        joint, recipe(), batch_boards=8, seed=3, workers=1, strata=joint.strata
    )
    try:
        assert isinstance(batches.sampler, BalancedSampler)
        picks = [index for step in range(40) for index in batches.sampler.indices(step)]
        assert Counter(index < 2 for index in picks) == {
            True: len(picks) // 2,
            False: len(picks) // 2,
        }
        assert batches(0)["crops"].shape[0] == 8
    finally:
        batches.close()
    with pytest.raises(ValueError, match="GRID_TRAINING_RECORDING_UNRESOLVED"):
        JointPhotos([small, large], [{"a0": "ga"}, groups[1]])


def _source(fixture: SnapshotFixture, role: str, key: int) -> dict[str, Any]:
    real = Image.new
    with patch.object(Image, "new", lambda mode, size, _c: real(mode, size, (key * 7, 60, 90))):
        return fixture.source(role, full=role != "TRAIN")


class Game:
    def __init__(self, root: Path, keys: dict[str, list[int]]) -> None:
        self.fixture = SnapshotFixture(root)
        for role, values in keys.items():
            for key in values:
                _source(self.fixture, role, key)
        self.fixture.publish()
        self.groups = {
            source["sourceId"]: f"{self.fixture.game}:{source['role']}:{index % 2}"
            for index, source in enumerate(self.fixture.sources)
        }

    def header(self) -> dict[str, Any]:
        return {
            "gameId": self.fixture.game,
            "id": self.fixture.cohort,
            "status": "frozen",
            "manifestSha256": self.fixture.manifest_pin["sha256"],
            "manifestPath": self.fixture.manifest_pin["path"],
            "mode": "grid-only",
            "familyId": BASE["familyId"],
            "baseVersionId": BASE["versionId"],
            "summary": {
                "roles": [
                    {
                        "role": "TRAIN",
                        "eligibleBoards": 30,
                        "eligiblePhotos": 10,
                        "eligibleFullPhotos": 0,
                    },
                    {
                        "role": "VALIDATION",
                        "eligibleBoards": 45,
                        "eligiblePhotos": 5,
                        "eligibleFullPhotos": 5,
                    },
                ]
            },
        }


class SharedStore(Store):
    def __init__(self, root: Path, games: list[Game]) -> None:
        super().__init__(root)
        self.games = {game.fixture.game: game for game in games}

    def cohort(self, game_id: UUID, cohort_id: UUID) -> dict[str, Any]:
        game = self.games[str(game_id)]
        assert str(cohort_id) == game.fixture.cohort
        return game.header()

    def recordings(self, game_id: UUID, cohort_id: UUID) -> dict[str, str]:
        return dict(self.games[str(game_id)].groups)


def shared_job(root: Path, primary: Game, other: Game) -> Any:
    plan = plan_for(
        root,
        primary.fixture.game,
        [(primary.header(), primary.groups), (other.header(), other.groups)],
    )
    from dataclasses import replace

    from game_predictor_api.domain.jobs import JobStatus

    value = create_job(
        JobType.GRID_TRAINING,
        game_id=UUID(primary.fixture.game),
        input_payload={
            "schema_version": 1,
            "training_kind": "grid-shared-training-run-v1",
            "idempotency_key": str(uuid4()),
            "cohort_id": primary.fixture.cohort,
            "cohort_manifest_sha256": primary.fixture.manifest_pin["sha256"],
            "mode": "grid-only",
            "family_id": BASE["familyId"],
            "base_version_id": BASE["versionId"],
            "preset_id": GRID_ONLY_V1.preset_id,
            "preset_fingerprint": GRID_ONLY_V1.fingerprint,
            "seed": 7,
            "planned_steps": 30,
            "shared_cohorts": [
                {
                    "game_id": other.fixture.game,
                    "cohort_id": other.fixture.cohort,
                    "manifest_sha256": other.fixture.manifest_pin["sha256"],
                }
            ],
            "joint_sha256": plan["sha256"],
        },
    )
    return replace(value, status=JobStatus.PROCESSING), plan


@pytest.fixture
def games(tmp_path: Path) -> tuple[Game, Game]:
    small = Game(tmp_path, {"TRAIN": [1, 2], "VALIDATION": [3, 4, 5, 6, 7], "REGRESSION": [8]})
    large = Game(
        tmp_path,
        {"TRAIN": list(range(10, 22)), "VALIDATION": list(range(22, 27)), "REGRESSION": [27]},
    )
    return small, large


def test_shared_run_trains_on_all_pinned_cohorts_and_registers_one_candidate(tmp_path, games):
    small, large = games
    store, child = SharedStore(tmp_path, [small, large]), FakeChild()
    current, plan = shared_job(tmp_path, small, large)
    handler(tmp_path, store, child)(Context(current), current)  # type: ignore[arg-type]
    (spec,) = child.launches
    joint = spec["joint"]
    assert joint["sha256"] == plan["sha256"] == current.input_payload["joint_sha256"]
    assert [pin["cohortId"] for pin in joint["cohorts"]] == [
        small.fixture.cohort,
        large.fixture.cohort,
    ]
    assert joint["cohorts"][1]["recordings"] == large.groups
    ((_key, payload),) = store.registered
    # The candidate is only registered: no publication, activation or game switch.
    assert payload["admission"] == "not_evaluated"
    assert payload["cohortId"] == small.fixture.cohort
    assert large.fixture.game in payload["inferenceManifest"]["selectionReason"]


def test_a_changed_shared_cohort_or_recording_never_trains(tmp_path, games):
    small, large = games
    current, _plan = shared_job(tmp_path, small, large)
    first = next(iter(large.groups))
    large.groups[first] = "moved-to-another-recording"
    store, child = SharedStore(tmp_path, [small, large]), FakeChild()
    with pytest.raises(JobHandlerError) as error:
        handler(tmp_path, store, child)(Context(current), current)  # type: ignore[arg-type]
    assert error.value.code == "GRID_SHARED_PLAN_DRIFT" and child.launches == []
    store.qualification = "blocked"
    with pytest.raises(JobHandlerError) as error:
        handler(tmp_path, store, child)(Context(current), current)  # type: ignore[arg-type]
    assert error.value.code == "SOURCE_REMOVED_NEW_USE_BLOCKED"


def test_a_swapped_recording_assignment_with_equal_counts_is_a_drift(tmp_path, games):
    small, large = games
    current, _plan = shared_job(tmp_path, small, large)
    train = [s["sourceId"] for s in large.fixture.sources if s["role"] == "TRAIN"]
    first, second = train[0], train[1]
    assert large.groups[first] != large.groups[second]
    large.groups[first], large.groups[second] = large.groups[second], large.groups[first]
    store, child = SharedStore(tmp_path, [small, large]), FakeChild()
    with pytest.raises(JobHandlerError) as error:
        handler(tmp_path, store, child)(Context(current), current)  # type: ignore[arg-type]
    assert error.value.code == "GRID_SHARED_PLAN_DRIFT" and child.launches == []


def test_a_control_photo_of_one_game_never_trains_the_shared_game(tmp_path, games):
    small, _large = games
    # Key 3 is a VALIDATION photo of the small game: the same bytes become TRAIN here.
    alias = Game(
        tmp_path, {"TRAIN": [3, 40], "VALIDATION": list(range(41, 46)), "REGRESSION": [46]}
    )
    with pytest.raises(SharedCandidateError) as error:
        plan_for(
            tmp_path,
            small.fixture.game,
            [(small.header(), small.groups), (alias.header(), alias.groups)],
        )
    assert error.value.code == "GRID_SHARED_CONTROL_ALIAS"
    assert error.value.details["controlGameId"] == small.fixture.game


def test_no_shared_path_publishes_activates_or_switches_a_game():
    for path in (
        WORKER / "images/grid_training_handler.py",
        WORKER / "images/grid_shared_candidate.py",
        API / "application/shared_grid_model_candidate.py",
        API / "domain/shared_grid_model_candidate.py",
    ):
        names = {
            node.attr if isinstance(node, ast.Attribute) else node.id
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Attribute | ast.Name)
        }
        assert not names & {"execute", "activate", "publish", "set_default", "apply_control"}, path
    assert np.isfinite(grid(30)).all()
