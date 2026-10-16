"""TASK-0997 evaluation job: identical inputs, per-game report, restart, cancel, guards.

Generated CPU-only snapshots and deterministic fake engines; no operator data, no ONNX.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import numpy as np
import pytest
from game_predictor_api.domain.grid_model_evaluation import require_report
from game_predictor_api.domain.grid_model_registry import (
    canonical_json,
    descriptor_sha256,
    historical_catalogue,
)
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_worker.images.grid_model_evaluation_handler import (
    GridModelEvaluationJobHandler,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from PIL import Image
from test_grid_cohort_dataset import SnapshotFixture

GROUP_A = "a1111111-1111-4111-8111-111111111111"
GROUP_B = "b2222222-2222-4222-8222-222222222222"
WORKER = Path(__file__).resolve().parents[1] / "src" / "game_predictor_worker"


class Stop(Exception):
    pass


class Context:
    def __init__(self, job: Any) -> None:
        self._job, self.states, self.progress = job, [], []

    @property
    def job(self) -> Any:
        return self._job

    def heartbeat(self) -> None:
        pass

    def checkpoint(self, *, checkpoint_payload, stage, current, total, **_counts) -> None:
        assert stage == "grid_model_evaluation"
        assert not self.progress or current >= self.progress[-1], "progress never decreases"
        assert checkpoint_payload["schema_version"] == 1
        json.dumps(checkpoint_payload)  # the durable state is plain JSON
        self.progress.append(current)
        self.states.append(copy.deepcopy(checkpoint_payload))
        if self._job.cancel_requested_at is not None:
            raise Stop


class FakeEngine:
    """Every label board, except on photos whose colour key is in ``missing``."""

    def __init__(self, labels: np.ndarray, missing: set[int], extra: set[int]) -> None:
        self.labels, self.missing, self.extra, self.calls = labels, missing, extra, 0

    def analyse(self, rgb: np.ndarray) -> list[Any]:
        self.calls += 1
        key = colour(rgb)
        count = 8 if key in self.missing else 10 if key in self.extra else 9
        return [SimpleNamespace(nodes=self.labels.copy()) for _ in range(count)]


def colour(rgb: np.ndarray) -> int:
    return int(round(float(rgb[..., 0].mean()) / 10.0))


def add_source(fixture: SnapshotFixture, role: str, key: int) -> dict[str, Any]:
    real = Image.new
    with patch.object(
        Image, "new", lambda mode, size, _colour: real(mode, size, (key * 10, 70, 90))
    ):
        return fixture.source(role, full=True)


class Store:
    def __init__(self, root: Path, games: dict[str, SnapshotFixture], candidate, base) -> None:
        self.root, self.games, self.candidate, self.base = root, games, candidate, base
        self.reports: dict[UUID, tuple[str, str]] = {}
        self.proofs: list[str] = []
        self.eligible = True
        self.groups = {
            str(game): {
                source["sourceId"]: (GROUP_A if index % 2 == 0 else GROUP_B)
                for index, source in enumerate(fixture.sources)
            }
            for game, fixture in games.items()
        }

    def catalogue(self, version_id, base_version_id):
        assert str(version_id) == self.candidate["versionId"]
        assert str(base_version_id) == self.candidate["baseVersionId"]
        return copy.deepcopy(self.candidate), copy.deepcopy(self.base), descriptor_sha256(self.base)

    def cohort(self, game_id, cohort_id):
        fixture = self.games[str(game_id)]
        assert str(cohort_id) == fixture.cohort
        return {
            "status": "frozen",
            "manifestSha256": fixture.manifest_pin["sha256"],
            "manifestPath": fixture.manifest_pin["path"],
            "familyId": self.candidate["familyId"],
            "baseVersionId": self.candidate["baseVersionId"],
        }

    def eligibility(self, game_id, cohort_id):
        return (
            {"qualification": "eligible", "reasons": []}
            if self.eligible
            else {"qualification": "blocked", "reasons": ["GRID_COHORT_LABEL_STALE"]}
        )

    def recordings(self, game_id, cohort_id):
        return self.groups[str(game_id)]

    def store_report(self, report_id, version_id, report_json, report_sha256):
        previous = self.reports.setdefault(report_id, (report_json, report_sha256))
        assert previous == (report_json, report_sha256), "same identity, same bytes"

    def prove(self, report_id, game_id, cohort_id, manifest_sha256):
        assert report_id in self.reports
        self.proofs.append(str(game_id))


@pytest.fixture
def scenario(tmp_path):
    games: dict[str, SnapshotFixture] = {}
    key = 0
    keys: dict[str, dict[str, list[int]]] = {}
    for _ in range(2):
        fixture = SnapshotFixture(tmp_path)
        keys[fixture.game] = {"VALIDATION": [], "REGRESSION": []}
        for role in ("VALIDATION", "REGRESSION"):
            for _photo in range(5):
                key += 1
                add_source(fixture, role, key)
                keys[fixture.game][role].append(key)
        fixture.publish()
        games[fixture.game] = fixture
    ordered = sorted(games)
    training, other = ordered[0], ordered[1]
    base = copy.deepcopy(historical_catalogue()[0])
    base["managedDirectory"] = "models/grid-engine/fixture/base"
    candidate = copy.deepcopy(base)
    bundle = json.dumps({"parity": {"passed": True}}).encode()
    directory = tmp_path / "models/grid-engine/fixture/candidate"
    directory.mkdir(parents=True)
    (directory / "bundle.json").write_bytes(bundle)
    files = [
        {**file, "sha256": hashlib.sha256(bundle).hexdigest(), "sizeBytes": len(bundle)}
        if file["name"] == "bundle.json"
        else file
        for file in base["files"]
    ]
    candidate.update(
        versionId=str(uuid4()),
        familyId=str(uuid4()),
        baseVersionId=base["versionId"],
        cohortId=games[training].cohort,
        admission="not_evaluated",
        managedDirectory="models/grid-engine/fixture/candidate",
        files=files,
    )
    store = Store(tmp_path, games, candidate, base)
    payload = {
        "schema_version": 1,
        "evaluation_kind": "grid-model-evaluation-v1",
        "idempotency_key": str(uuid4()),
        "version_id": candidate["versionId"],
        "manifest_sha256": descriptor_sha256(candidate),
        "base_version_id": base["versionId"],
        "base_manifest_sha256": descriptor_sha256(base),
        "family_id": candidate["familyId"],
        "training_game_id": training,
        "cohorts": [
            {
                "game_id": game,
                "cohort_id": games[game].cohort,
                "manifest_sha256": games[game].manifest_pin["sha256"],
            }
            for game in ordered
        ],
    }
    job = create_job(JobType.GRID_MODEL_EVALUATION, game_id=UUID(training), input_payload=payload)
    labels = np.array(
        [[node["x"], node["y"]] for node in games[training].sources[0]["targets"][0]["nodes"]],
        dtype=np.float32,
    )
    return SimpleNamespace(
        root=tmp_path,
        store=store,
        job=job,
        training=training,
        other=other,
        keys=keys,
        labels=labels,
        candidate=candidate,
        base=base,
    )


def handler(s, base_missing=(), candidate_missing=(), candidate_extra=(), engines=None):
    engines = engines if engines is not None else {}

    def factory(directory: Path, sha: str):
        name = directory.name
        assert name in {"base", "candidate"}
        missing = set(base_missing if name == "base" else candidate_missing)
        extra = set() if name == "base" else set(candidate_extra)
        engines[name] = FakeEngine(s.labels, missing, extra)
        return engines[name]

    return GridModelEvaluationJobHandler(s.store, s.root, engine_factory=factory), engines


def run(s, job=None, **options):
    evaluation, engines = handler(s, **options)
    context = Context(job or s.job)
    evaluation(context, job or s.job)
    return context, engines


def only_report(s):
    ((report_json, sha),) = s.store.reports.values()
    report = require_report(
        report_json, manifest=s.candidate, base_sha256=descriptor_sha256(s.base)
    )
    assert descriptor_sha256(report) == sha
    return report


def test_candidate_improving_the_training_game_without_regression_passes(scenario):
    s = scenario
    context, engines = run(s, base_missing=s.keys[s.training]["VALIDATION"][:2])
    report = only_report(s)
    assert report["verdict"] == "PASS"
    training = next(game for game in report["games"] if game["gameId"] == s.training)
    validation = training["roles"]["VALIDATION"]
    assert (validation["base"]["boards_matched"], validation["candidate"]["boards_matched"]) == (
        43,
        45,
    )
    # A missing board costs 1 per missing label in image-macro, never zero error.
    assert validation["base"]["image_macro"] > validation["candidate"]["image_macro"]
    assert validation["base"]["photo_complete_correct"] == 3
    assert [item["groupId"] for item in validation["recordings"]] == sorted([GROUP_A, GROUP_B])
    for game in report["games"]:
        for role in ("VALIDATION", "REGRESSION"):
            entry = game["roles"][role]
            detail = s.root / entry["detail"]["path"]
            content = detail.read_bytes()
            assert hashlib.sha256(content).hexdigest() == entry["detail"]["sha256"]
            rows = json.loads(content)["photos"]
            assert len(rows) == entry["photos"] == 5
            assert all(set(row) == {"sourceId", "groupId", "base", "candidate"} for row in rows)
    # Both engines saw each of the twenty control photos exactly once.
    assert engines["base"].calls == engines["candidate"].calls == 20
    assert s.store.proofs == sorted([s.training, s.other])
    assert context.states[-1]["proven"] == s.store.proofs


def test_regression_in_another_game_blocks_the_shared_pass(scenario):
    s = scenario
    run(
        s,
        base_missing=s.keys[s.training]["VALIDATION"][:1],
        candidate_missing=s.keys[s.other]["REGRESSION"][:1],
    )
    report = only_report(s)
    assert report["verdict"] == "REVISE"
    other = next(game for game in report["games"] if game["gameId"] == s.other)
    assert other["regression"] == "fail"
    assert "REGRESSION_REGRESSED:boards_matched" in other["reasons"]
    # A negative report is still bound and proven per game; it never publishes.
    assert s.store.proofs == sorted([s.training, s.other])


def test_an_extra_duplicate_detection_in_another_game_blocks_the_pass(scenario):
    s = scenario
    run(
        s,
        base_missing=s.keys[s.training]["VALIDATION"][:1],
        candidate_extra=s.keys[s.other]["REGRESSION"][:1],
    )
    report = only_report(s)
    assert report["verdict"] == "REVISE"
    other = next(game for game in report["games"] if game["gameId"] == s.other)
    regression = other["roles"]["REGRESSION"]["candidate"]
    assert regression["duplicate_predictions"] == 1 and regression["false_boards"] == 0
    assert other["reasons"] == ["REGRESSION_REGRESSED:duplicate_predictions"]


def test_a_missing_or_changed_detail_file_fails_closed_on_restart(scenario):
    s = scenario
    context, _ = run(s, base_missing=s.keys[s.training]["VALIDATION"][:1])
    state = copy.deepcopy(context.states[-1])
    state["proven"], state["reportSha256"], state["verdict"] = [], None, None
    unit = state["units"][f"{s.training}:VALIDATION"]
    (s.root / unit["detail"]["path"]).write_bytes(b"{}")
    s.store.reports.clear()
    resumed = dataclasses.replace(s.job, checkpoint_payload=state)
    with pytest.raises(JobHandlerError) as error:
        run(s, job=resumed)
    assert error.value.code == "GRID_EVALUATION_DETAIL_CHANGED"
    (s.root / unit["detail"]["path"]).unlink()
    with pytest.raises(JobHandlerError) as error:
        run(s, job=resumed)
    assert error.value.code == "GRID_EVALUATION_DETAIL_CHANGED"
    assert s.store.reports == {}


def test_restart_skips_finished_units_and_rebuilds_the_identical_report(scenario):
    s = scenario
    options = {"base_missing": s.keys[s.training]["VALIDATION"][:1]}
    context, _ = run(s, **options)
    (expected,) = s.store.reports.values()
    after_one_unit = context.states[0]
    assert len(after_one_unit["units"]) == 1
    s.store.reports.clear()
    s.store.proofs.clear()
    restarted = dataclasses.replace(s.job, checkpoint_payload=after_one_unit)
    _, engines = run(s, job=restarted, **options)
    assert engines["base"].calls == engines["candidate"].calls == 15
    assert list(s.store.reports.values()) == [expected]
    # A crash after the report and the first proof only proves the remaining game.
    s.store.proofs.clear()
    state = copy.deepcopy(context.states[-1])
    state["proven"] = state["proven"][:1]
    resumed = dataclasses.replace(s.job, checkpoint_payload=state)
    _, engines = run(s, job=resumed, **options)
    assert engines == {}, "no model is loaded when every unit is measured"
    assert s.store.proofs == context.states[-1]["proven"][1:]
    assert list(s.store.reports.values()) == [expected]


def test_cancel_is_honoured_between_photos_without_a_report(scenario):
    s = scenario
    job = dataclasses.replace(s.job, cancel_requested_at=datetime.now(UTC))
    evaluation, engines = handler(s)
    with pytest.raises(Stop):
        evaluation(Context(job), job)
    assert engines["base"].calls == 0
    assert s.store.reports == {} and s.store.proofs == []


def test_changed_pins_or_withdrawn_labels_fail_closed(scenario):
    s = scenario
    s.store.eligible = False
    with pytest.raises(JobHandlerError) as error:
        run(s)
    assert error.value.code == "GRID_COHORT_LABEL_STALE"
    s.store.eligible = True
    changed = copy.deepcopy(s.job.input_payload)
    changed["manifest_sha256"] = "0" * 64
    job = create_job(JobType.GRID_MODEL_EVALUATION, game_id=s.job.game_id, input_payload=changed)
    with pytest.raises(JobHandlerError) as error:
        run(s, job=job)
    assert error.value.code == "GRID_EVALUATION_MODEL_CHANGED"
    foreign = copy.deepcopy(s.job.input_payload)
    foreign["training_game_id"] = s.other
    job = create_job(JobType.GRID_MODEL_EVALUATION, game_id=s.job.game_id, input_payload=foreign)
    with pytest.raises(JobHandlerError) as error:
        run(s, job=job)
    assert error.value.code == "GRID_EVALUATION_INPUT_INVALID"
    assert s.store.reports == {}


def test_checkpoint_selection_never_reads_regression():
    """The trainer, its data and the neutral core select checkpoints on VALIDATION only.

    The supervisor reads REGRESSION photo counts for the cost estimate only; it never
    decodes a pixel or evaluates a checkpoint.
    """
    for relative in (
        "images/grid_training_child.py",
        "images/grid_training_data.py",
        "training_core/grid_training.py",
    ):
        tree = ast.parse((WORKER / relative).read_text(encoding="utf-8"))
        roles = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and node.value in {"TRAIN", "VALIDATION", "REGRESSION"}
        }
        assert "REGRESSION" not in roles, relative
    child = ast.parse((WORKER / "images/grid_training_child.py").read_text(encoding="utf-8"))
    photo_roles = [
        call.args[1].value
        for call in ast.walk(child)
        if isinstance(call, ast.Call)
        and getattr(call.func, "id", None) == "CohortPhotos"
        and isinstance(call.args[1], ast.Constant)
    ]
    assert photo_roles == ["TRAIN", "VALIDATION"]


def test_the_report_is_canonical_and_free_of_timestamps(scenario):
    s = scenario
    run(s, base_missing=s.keys[s.training]["VALIDATION"][:1])
    ((report_json, _),) = s.store.reports.values()
    assert canonical_json(json.loads(report_json)) == report_json
    assert "At" not in "".join(json.loads(report_json).keys())
