"""A private detector and lattice start from their own seed and supervised pixels."""

import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
import torch
from game_predictor_worker.images import grid_training_child as child
from game_predictor_worker.images.grid_training_data import CohortPhotos, ScreenGridBatches
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.training_core.grid_rescue_training import TrainingExposure
from game_predictor_worker.training_core.grid_training import namespace, screen_grid_losses, train
from game_predictor_worker.training_core.grid_training_admission import (
    SCREEN_GRID_CORRECTIONS_V1,
    digest,
)
from test_durable_v3_grid_training import PRESET, Control, Tiny, batches, evaluate, losses, plan
from test_grid_cohort_dataset import SnapshotFixture
from test_grid_training_handler import BASE, FakeChild, Store, handler, job


@pytest.fixture
def private_snapshot(tmp_path):
    fixture = SnapshotFixture(tmp_path)
    full = fixture.source("TRAIN", full=True)
    partial = fixture.source("TRAIN")
    for _ in range(9):
        fixture.source("TRAIN", full=True)
    for _ in range(5):
        fixture.source("VALIDATION", full=True)
    split = {
        "schemaVersion": "grid-correction-split-v3",
        "sources": [
            {
                "sourceId": source["sourceId"],
                "role": source["role"],
                "representative": True,
                "eligibleBoards": len(source["targets"]),
                "qualifiedLabelsSha256": digest(source["targets"]),
                "sourceSha256": source["sourceIdentity"]["checksum_sha256"],
                "pixelSha256": source["sourceIdentity"]["normalized_pixel_checksum_sha256"],
            }
            for source in fixture.sources
        ],
    }
    split["sha256"] = digest(split)

    def private(root):
        root.update(
            schemaVersion="application-grid-snapshot-v3",
            policyVersion="application-grid-corrections-v3",
            cropPolicyVersion="full-cell-v2",
            photoSplit=split,
            detectorReadiness={"reasonCodes": []},
            weightInitialization="from_scratch",
            privateLearning=dict(
                gameId=fixture.game,
                assignmentRevision=1,
                targetFamilyId=root["familyId"],
                baseVersionId=root["base"]["versionId"],
                baseManifestSha256=root["base"]["manifestSha256"],
            ),
        )

    def without_validation(root):
        private(root)
        root["counts"]["VALIDATION"]["fullPhotos"] = 4

    with pytest.raises(ValueError, match="full VALIDATION"):
        fixture.publish(mode="screen+grid", change=without_validation)
    snapshot = fixture.publish(mode="screen+grid", change=private)
    return fixture, snapshot, full, partial


def test_seeded_private_network_trains_both_stages_without_any_previous_weights(
    tmp_path, monkeypatch, private_snapshot
):
    fixture, snapshot, full, partial = private_snapshot
    photos = CohortPhotos(snapshot, "TRAIN", full_only=False)
    payload = json.loads(child.RECIPE_FILE.read_bytes())
    recipe = namespace(payload)
    recipe.screen.train_canvas = (64, 64)
    recipe.board.canvas = (64, 64)
    recipe.board.boards_per_image = 2
    spec = {
        "seed": 51,
        "weightInitialization": "from_scratch",
        "base": {"presetSha256": child.RECIPE_FINGERPRINT, "managedDirectory": "missing"},
        "preset": {"id": "screen-grid-corrections-v1"},
    }
    monkeypatch.setattr(
        child, "_base", lambda *_: pytest.fail("Cold training opened ancestral weights")
    )
    monkeypatch.setattr(
        torch, "load", lambda *_a, **_k: pytest.fail("Cold training loaded an old network")
    )
    network = child._initial_network(spec, tmp_path, recipe, payload)
    second = child._initial_network(spec, tmp_path, recipe, payload)
    for first, replayed in zip(network.parameters(), second.parameters(), strict=True):
        assert torch.equal(first, replayed)
    del second
    batches = ScreenGridBatches(photos, recipe, 2, 51, 1, partial_training=True)
    try:
        # Hold membership constant to exercise both types of real annotation in one optimizer step.
        batches.sampler = SimpleNamespace(indices=lambda _: [0, 1])
        batch = batches._build(0)
        assert batch["screen_eligible"].tolist() == [True, False]
        assert batch["weights"][1].tolist() == [4, 0]
        exposure = TrainingExposure({"sha256": "a" * 64, "variant": None})
        original_manifest = type(snapshot).manifest
        reads = []

        def tracked_manifest(instance):
            reads.append(instance)
            return original_manifest.__get__(instance, type(instance))

        monkeypatch.setattr(type(snapshot), "manifest", property(tracked_manifest))
        members = batches.private_exposure_members(0)
        assert batches.private_exposure_members(0) == members
        assert reads == [snapshot]
        exposure.confirm(1, members)
        per_stage = exposure.state()["games"][fixture.game]
        for stage, ids in (
            ("screen:baseline", {full["sourceId"]}),
            ("board:baseline", {full["sourceId"], partial["sourceId"]}),
        ):
            assert {m["sourceId"] for m in per_stage[stage]["sources"].values()} == ids
        previous_threads = torch.get_num_threads()
        try:
            torch.set_num_threads(1)
            stage_weights = [network.screen.heat[-1].weight, network.board.nodes[-1].weight]
            before = [weight.detach().clone() for weight in stage_weights]
            optimizer = torch.optim.SGD(network.parameters(), lr=1e-3)
            screen_grid_losses(network, batch, recipe, "cpu")["total"].backward()
            optimizer.step()
            assert all(
                not torch.equal(prior, current)
                for prior, current in zip(before, stage_weights, strict=True)
            )
        finally:
            torch.set_num_threads(previous_threads)
    finally:
        batches.close()


def test_cold_child_trains_selects_exports_and_reopens_both_graphs(
    tmp_path, monkeypatch, private_snapshot
):
    from game_predictor_api.domain.grid_rescue_policy import require_rescue_evidence

    fixture, snapshot, _, _ = private_snapshot
    # Keep the real training path, two ONNX graphs, selection and parity, on tiny CPU rasters.
    payload = json.loads(child.RECIPE_FILE.read_bytes())
    payload["screen"]["train_canvas"] = [64, 64]
    payload["board"]["boards_per_image"] = 2
    recipe_file = tmp_path / "cpu-recipe.json"
    recipe_file.write_bytes(child.canonical(payload))
    monkeypatch.setattr(child, "RECIPE_FILE", recipe_file)
    monkeypatch.setattr(child, "RECIPE_FINGERPRINT", digest(payload))
    preset = replace(SCREEN_GRID_CORRECTIONS_V1, batch_items=2, data_workers=1)
    monkeypatch.setitem(child.PRESETS, preset.preset_id, preset)
    monkeypatch.setattr(child, "ChildControl", lambda *a, **k: Control())
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    import onnxruntime as ort

    create_session = ort.InferenceSession
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1

    def cpu_session(path, sess_options=None, **kwargs):
        return create_session(path, sess_options=sess_options or options, **kwargs)

    monkeypatch.setattr(ort, "InferenceSession", cpu_session)
    monkeypatch.setattr(
        child, "_base", lambda *_: pytest.fail("Loaded the comparator's training files")
    )
    base = snapshot.manifest["base"]
    spec = {
        "jobId": str(uuid4()),
        "attempt": 1,
        "artifactRoot": str(tmp_path),
        "cohort": {
            "gameId": fixture.game,
            "cohortId": fixture.cohort,
            "manifestPath": fixture.manifest_pin["path"],
            "manifestSha256": fixture.manifest_pin["sha256"],
        },
        "base": {
            "versionId": base["versionId"],
            "comparisonManifestSha256": base["manifestSha256"],
            "managedDirectory": base["manifest"]["managedDirectory"],
            "presetSha256": digest(payload),
        },
        "weightInitialization": "from_scratch",
        "independentGameId": fixture.game,
        "seed": 51,
        "plannedSteps": 1,
        "requireCuda": False,
        "device": "cpu",
        "dataWorkers": 1,
        "preset": {"id": preset.preset_id, "fingerprint": preset.fingerprint},
    }
    result = child._train(spec, tmp_path, tmp_path, None, None, {"step": 0})
    assert result["status"] == "exported"
    exported = tmp_path / result["export"]["directory"]
    bundle = json.loads((exported / "bundle.json").read_bytes())
    assert bundle["parity"]["passed"]
    assert bundle["provenance"]["independentGameId"] == fixture.game
    assert bundle["provenance"]["weightInitialization"] == "from_scratch"
    assert all((exported / graph).is_file() for graph in ("screen.onnx", "board.onnx"))
    assert require_rescue_evidence(bundle)["trainingExposure"]["confirmedSteps"] == 1


def test_private_spec_pins_comparison_without_training_artifacts_and_refuses_foreign_continuation(
    tmp_path, monkeypatch
):
    store = Store(tmp_path)
    current = job()
    family = str(uuid4())
    current = replace(
        current,
        input_payload={
            **current.input_payload,
            "private_learning": {"targetFamilyId": family, "baseManifestSha256": "f" * 64},
            "weight_initialization": "from_scratch",
        },
    )
    previous = {**BASE, "trainingArtifacts": []}
    reads = []

    def read(_version, *, inference_only=False):
        reads.append(inference_only)
        return previous

    monkeypatch.setattr(store, "base_version", read)
    runner = handler(tmp_path, store, FakeChild())
    assert runner._base_for_job(current) is previous
    header = store.cohort(current.game_id, current.input_payload["cohort_id"])
    state = SimpleNamespace(
        attempt=1,
        checkpoint=None,
        budget=SimpleNamespace(
            max_seconds=None, remaining_steps=5, used_seconds=0, limit_policy=None
        ),
    )
    spec = runner._spec(current, state, header, previous)
    assert spec["weightInitialization"] == "from_scratch"
    assert spec["independentGameId"] == str(current.game_id)
    assert spec["base"] == {
        "versionId": BASE["versionId"],
        "managedDirectory": BASE["managedDirectory"],
        "comparisonManifestSha256": "f" * 64,
        "presetSha256": child.RECIPE_FINGERPRINT,
    }
    manifest = {
        "gameId": str(current.game_id),
        "cohortId": spec["cohort"]["cohortId"],
        "familyId": family,
        "weightInitialization": "from_scratch",
        "privateLearning": {"gameId": str(current.game_id)},
        "base": {"versionId": BASE["versionId"], "manifestSha256": "f" * 64, "manifest": previous},
    }
    child._check_private_snapshot(spec, manifest)
    for changed in (
        {"weightInitialization": "assigned_weights"},
        {"independentGameId": str(uuid4())},
        {"base": {**spec["base"], "comparisonManifestSha256": "0" * 64}},
        {"cohort": {**spec["cohort"], "cohortId": str(uuid4())}},
    ):
        with pytest.raises(child.ChildError, match="GRID_PRIVATE_INITIALIZATION_INVALID"):
            child._check_private_snapshot({**spec, **changed}, manifest)
    with pytest.raises(child.ChildError):
        child._check_private_snapshot({**spec, "weightInitialization": None}, manifest)
    warm = replace(
        current,
        input_payload={**current.input_payload, "weight_initialization": "assigned_weights"},
    )
    with pytest.raises(JobHandlerError, match="lineage"):
        runner._base_for_job(warm)
    previous.update(
        familyId=family,
        provenance={
            "independentGameId": str(current.game_id),
            "weightInitialization": "from_scratch",
        },
    )
    assert runner._base_for_job(warm) is previous
    assert reads == [True, False, False]
    with pytest.raises(JobHandlerError):
        runner._private_provenance(
            warm,
            {"weightInitialization": "from_scratch", "independentGameId": str(current.game_id)},
        )
    with pytest.raises(JobHandlerError):
        runner._private_provenance(
            job(),
            {"weightInitialization": "assigned_weights", "independentGameId": str(current.game_id)},
        )


def test_private_checkpoint_resumes_only_its_original_weight_lineage(tmp_path):
    spec = {
        "weightInitialization": "from_scratch",
        "independentGameId": str(uuid4()),
        "base": {
            "presetSha256": child.RECIPE_FINGERPRINT,
            "versionId": str(uuid4()),
            "comparisonManifestSha256": "1" * 64,
        },
    }
    initial = child._weight_binding(spec)
    assert "baseWeightsSha256" not in initial
    arguments = dict(
        preset=PRESET,
        batches=batches,
        losses=losses,
        evaluate=evaluate,
        checkpoint_directory=tmp_path,
    )
    capture = Control()
    reference = train(
        network=Tiny(), control=capture, plan=replace(plan(), binding=initial), **arguments
    )
    path, checksum, _ = capture.published[0]
    restart = dict(resume=(path, checksum), **arguments)
    result = train(
        network=Tiny(),
        control=Control(),
        plan=replace(plan(), binding=child._weight_binding(spec)),
        **restart,
    )
    assert result.best_metric == reference.best_metric
    for foreign in (
        {**spec, "independentGameId": str(uuid4())},
        {
            **spec,
            "weightInitialization": "assigned_weights",
            "base": {**spec["base"], "weightsSha256": "a" * 64},
        },
        {**spec, "base": {**spec["base"], "comparisonManifestSha256": "f" * 64}},
    ):
        with pytest.raises(ValueError, match="CHECKPOINT_BINDING_MISMATCH"):
            train(
                network=Tiny(),
                control=Control(),
                plan=replace(plan(), binding=child._weight_binding(foreign)),
                **restart,
            )
