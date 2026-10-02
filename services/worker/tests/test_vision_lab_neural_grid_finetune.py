"""TASK-0825: iterative Mumie fine-tune of neural_grid (preset D, run 3 of D-481)."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from game_predictor_worker.training_core.runtime import TrainingInterrupted
from game_predictor_worker.vision_lab import assisted_annotation as assisted
from game_predictor_worker.vision_lab import neural_grid_finetune as finetune
from game_predictor_worker.vision_lab import neural_grid_protocol as protocol
from game_predictor_worker.vision_lab.annotations import read_checked
from game_predictor_worker.vision_lab.neural_grid_data import load_samples
from game_predictor_worker.vision_lab.run_contracts import RunMutation
from game_predictor_worker.vision_lab.runs import RunManager, token
from test_vision_lab_assisted_annotation import (
    FakeEngine,
    accept_all,
    first_photo,
    lab,
    publish,
)


def _settings():
    return protocol.load_preset("D")[0].finetune


# --- preset D ---------------------------------------------------------------------------------


def test_preset_d_frozen_bound_to_run1_and_drift_refused(tmp_path, monkeypatch):
    preset, fingerprint = protocol.load_preset("D")
    assert fingerprint == protocol.FROZEN_PRESET_FINGERPRINTS["D"]
    assert preset.pretrained == protocol.PRETRAINED_RUN1 and preset.metrics == (
        protocol.METRIC_DEFINITION
    )
    init = preset.finetune.init
    assert init.run_id == "43933ac8d7d443c8b9079630a83de2e6" and init.best_round == 3
    assert init.weights_sha256.startswith("19b8d138")
    assert preset.optimization.learning_rate == 1e-4
    assert (
        preset.optimization.batch_images == protocol.load_preset("B")[0].optimization.batch_images
    )
    assert preset.augmentation == protocol.load_preset("B")[0].augmentation  # full B
    assert preset.schedule.max_run_seconds == protocol.MAX_RUN_SECONDS
    # A/B/C stay as they were and never carry a fine-tune section.
    for name in protocol.PRESET_NAMES:
        assert protocol.load_preset(name)[0].finetune is None
    payload = json.loads(protocol.preset_path("D").read_text(encoding="utf-8"))
    payload["finetune"]["mumie_images_per_batch"] = 6
    (tmp_path / "D.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(protocol, "PRESET_DIRECTORY", tmp_path)
    with pytest.raises(ValueError, match="FINGERPRINT_MISMATCH"):
        protocol.load_preset("D")
    payload = json.loads((tmp_path / "D.json").read_text(encoding="utf-8"))
    payload.pop("finetune")
    with pytest.raises(ValueError, match="FINETUNE_PRESET_INVALID"):
        protocol.Preset.model_validate(payload)


# --- one run, durable budget --------------------------------------------------------------------


def _manager(tmp_path, clock):
    return RunManager(
        tmp_path,
        validate=protocol.validate_request,
        models=(protocol.MODEL_VERSION,),
        launcher=lambda run: None,
        state_type=protocol.NeuralGridRunState,
        admit=protocol.admit_run,
        identity=lambda pid: None,
        clock=lambda: clock[0],
    )


def _request(name, purpose="train", request_id=None):
    return protocol.build_request(
        request_id=request_id or f"neural-{name}-{purpose}",
        preset_name=name,
        purpose=purpose,
        snapshot_id="b" * 64,
    )


def _checkpoint(request, epoch):
    torch = pytest.importorskip("torch")
    from game_predictor_worker.training_core.checkpoint import checkpoint_bytes, make_checkpoint
    from game_predictor_worker.vision_lab.runs import checkpoint_binding

    model = torch.nn.Linear(1, 1)
    return checkpoint_bytes(
        make_checkpoint(
            model,
            torch.optim.AdamW(model.parameters()),
            None,
            torch.Generator(),
            binding=checkpoint_binding(request),
            epoch=epoch,
            global_step=1,
            history=[],
            best_state={"round": epoch},
        )
    )


def test_finetune_is_one_run_whose_iterations_share_the_durable_budget(tmp_path):
    clock = [1000.0]
    manager = _manager(tmp_path, clock)
    for name in ("A", "B"):
        run = manager.create_or_get_run(_request(name))
        manager.cancel_run(run.id, RunMutation(request_id=f"cancel-{name}", expected_attempt=1))
    smoke = manager.create_or_get_run(_request("D", "smoke"))
    assert smoke.request.configuration.max_steps <= 50
    manager.cancel_run(smoke.id, RunMutation(request_id="cancel-smoke", expected_attempt=1))
    run = manager.create_or_get_run(_request("D"))  # smoke did not count: D is run 3
    assert run.request.configuration.max_seconds == 14400
    assert run.request.configuration.epochs == 16
    # Iteration 1: an attempt that charges wall time and ends with its own checkpoint.
    lease = token(run)
    manager.claim(run.id, lease)
    clock[0] += 5000
    manager.heartbeat(run.id, lease)
    manager.checkpoint(run.id, lease, _checkpoint(run.request, 1), 1)
    manager.finish(run.id, lease, status="cancelled", error=finetune.ITERATION_COMPLETE)
    fresh = _manager(tmp_path, clock)  # durable across processes
    # No fourth run, whatever the preset.
    for name in ("C", "D"):
        with pytest.raises(ValueError, match="BUDGET_EXHAUSTED"):
            fresh.create_or_get_run(_request(name, request_id=f"neural-{name}-fourth"))
    first = fresh.detail(run.id)
    assert first.used_seconds == pytest.approx(5000) and first.checkpoint_epoch == 1
    assert first.report is not None
    # Iteration 2 is a resume of the same run: same used_seconds, same limit.
    second = fresh.retry_run(run.id, RunMutation(request_id="iteration-2", expected_attempt=1))
    assert second.id == run.id and second.attempt == 2
    assert second.used_seconds == pytest.approx(5000)
    lease = token(second)
    fresh.claim(run.id, lease)
    clock[0] += 9400  # 14 400 s reached
    with pytest.raises(TrainingInterrupted, match="BUDGET_EXHAUSTED"):
        fresh.heartbeat(run.id, lease)
    fresh.finish(run.id, lease, status="cancelled", error="RUN_BUDGET_EXHAUSTED")
    assert fresh.detail(run.id).used_seconds == pytest.approx(14400)
    with pytest.raises(TrainingInterrupted, match="BUDGET_EXHAUSTED"):
        fresh.retry_run(run.id, RunMutation(request_id="iteration-3", expected_attempt=2))
    preset = protocol.load_preset("D")[0]
    assert finetune.affordable_train_seconds(preset, 14400, 900, 420) < 0


def test_smoke_request_of_preset_d_is_limited_to_fifty_steps():
    smoke = _request("D", "smoke").model_dump()
    smoke["configuration"]["max_steps"] = 51
    with pytest.raises(ValueError, match="SMOKE_STEP_LIMIT"):
        protocol.NeuralGridRunRequest.model_validate(smoke)


# --- holdout, selection, batches, proposal accuracy ---------------------------------------------


def test_holdout_is_deterministic_permanent_every_fifth_and_guarded():
    photos = {f"src-{i}": hashlib.sha256(str(i).encode()).hexdigest() for i in range(10)}
    forward = finetune.assign_holdout({}, photos, 5, 1)
    backward = finetune.assign_holdout({}, dict(reversed(list(photos.items()))), 5, 1)
    assert forward == backward  # not the order of clicks
    assert sorted(e["position"] for e in forward.values()) == list(range(1, 11))
    assert {e["position"] for e in forward.values() if e["role"] == "holdout"} == {5, 10}
    more = {
        **photos,
        **{f"src-{i}": hashlib.sha256(str(i).encode()).hexdigest() for i in range(10, 16)},
    }
    later = finetune.assign_holdout(forward, more, 5, 2)
    assert all(later[k] == v for k, v in forward.items())  # assignments are permanent
    assert {e["position"] for e in later.values() if e["role"] == "holdout"} == {5, 10, 15}
    holdout = finetune.holdout_ids(later)
    finetune.guard_training_photos(sorted(set(later) - holdout), holdout)
    with pytest.raises(ValueError, match="HOLDOUT_IN_TRAINING"):
        finetune.guard_training_photos([*sorted(set(later) - holdout), min(holdout)], holdout)


def _candidate(index, development, holdout, macro=0.01):
    return {
        "candidate": index,
        "development": {"photo_complete_correct_rate": development, "image_macro": 0.003},
        "holdout": {"photo_complete_correct_rate": holdout, "image_macro": macro},
    }


def test_selection_by_mumie_holdout_under_the_777_guard():
    settings = _settings()
    candidates = [
        _candidate(1, 0.9200, 0.50),
        _candidate(2, 0.9100, 0.90),  # 1.3 pp below run 1: not admissible
        _candidate(3, 0.9190, 0.60),
    ]
    assert finetune.select_candidate(candidates, settings, 5) == (
        3,
        "max_mumie_holdout_with_777_guard",
    )
    assert finetune.select_candidate(candidates, settings, 2) == (
        3,
        "last_admissible_state_holdout_too_small",
    )
    assert finetune.select_candidate([candidates[1]], settings, 5) == (
        None,
        "previous_state_kept_777_development_drop",
    )
    assert finetune.select_candidate(candidates, settings, 0, smoke=True)[0] == 3
    tie = [_candidate(1, 0.93, 0.6, 0.02), _candidate(2, 0.93, 0.6, 0.01)]
    assert finetune.select_candidate(tie, settings, 5)[0] == 2


def test_training_time_grows_with_photos_and_batches_mix_mumie_and_777():
    settings = _settings()
    assert finetune.planned_train_seconds(settings, 1) == 300
    assert finetune.planned_train_seconds(settings, 8) == 480
    assert finetune.planned_train_seconds(settings, 40) == 900
    sampler = iter(finetune.MixedBatchSampler(3, 100, 12, 4, 7))
    for _ in range(20):
        batch = next(sampler)
        assert len(batch) == 12 and sum(i < 3 for i in batch) == 4
    assert next(iter(finetune.MixedBatchSampler(3, 100, 12, 4, 7))) == next(
        iter(finetune.MixedBatchSampler(3, 100, 12, 4, 7))
    )


def test_proposal_accuracy_of_the_last_batch():
    def board(origin, set_id="s0", shift=None):
        return {"origin": origin, "proposalSetId": set_id, "maxCornerShiftPx": shift}

    rows = [
        {"imageId": "old", "activeMs": 1, "boards": [board("manual")]},
        {
            "imageId": "a",
            "activeMs": 60000,
            "boards": [board("proposal_unchanged"), board("proposal_corrected", "s1", 4.0)],
        },
        {"imageId": "b", "activeMs": 120000, "boards": [board("proposal_unchanged", "s1")]},
        {"imageId": "c", "activeMs": 30000, "boards": [board("manual", "")]},
    ]
    result = finetune.proposal_accuracy(rows, {"old"})
    assert result["photos"] == 3 and result["boards"] == 4
    assert result["unchanged_share_of_boards"] == 0.5
    assert result["corrected_share_of_boards"] == 0.25
    assert result["manual_share_of_boards"] == 0.25
    assert result["by_proposal_set"] == {
        "s0": {"proposal_unchanged": 1},
        "s1": {"proposal_corrected": 1, "proposal_unchanged": 1},
    }
    assert result["active_seconds_per_photo"]["median"] == 60


def test_finetune_module_is_torch_free_at_import():
    code = (
        "import sys\n"
        "import game_predictor_worker.vision_lab.neural_grid_finetune\n"
        "import game_predictor_worker.vision_lab.assisted_annotation\n"
        "assert 'torch' not in sys.modules, 'torch imported'\n"
        "assert not [m for m in sys.modules if m.startswith('psycopg') or '.storage' in m]\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


# --- the iteration command end to end (CPU) ----------------------------------------------------


def _tiny_preset():
    preset = protocol.load_preset("D")[0]
    settings = preset.finetune
    return preset.model_copy(
        update={
            "optimization": preset.optimization.model_copy(
                update={"batch_images": 2, "data_workers": 0}
            ),
            "board": preset.board.model_copy(update={"boards_per_image": 1}),
            "screen": preset.screen.model_copy(update={"train_canvas": (160, 128)}),
            "schedule": preset.schedule.model_copy(update={"minimum_round_seconds": 0.5}),
            "finetune": settings.model_copy(
                update={
                    "mumie_images_per_batch": 1,
                    "candidates_per_iteration": 2,
                    "holdout_every": 2,
                    "train_seconds_per_mumie_photo": 1.0,
                    "iteration_train_seconds_min": 1.0,
                    "iteration_train_seconds_max": 2.0,
                    "init": settings.init.model_copy(
                        update={"development_photo_complete_correct_rate": 0.0}
                    ),
                }
            ),
        }
    )


def test_iterate_end_to_end(tmp_path, monkeypatch):
    pytest.importorskip("torch")
    from game_predictor_worker.vision_lab import neural_grid_inference
    from game_predictor_worker.vision_lab.neural_grid_model import NeuralGridNetwork
    from game_predictor_worker.vision_lab.neural_grid_runs import NeuralGridRunManager, validator

    catalog, store, training, bundle = lab(tmp_path)
    base = publish(tmp_path, catalog, store, training, bundle)
    workspace = assisted.Workspace(catalog, store.root, tmp_path / "proposals", games=("mumie",))
    first, _ = first_photo(workspace, 0)
    second, _ = first_photo(workspace, 1)
    third, _ = first_photo(workspace, 2)
    accept_all(workspace, first["source_id"])
    state = accept_all(workspace, second["source_id"])
    assert assisted.photo_complete(state, catalog.sources[second["source_id"]])
    # A stand-in for the 777 snapshot in the production reader format (training + development).
    rows = assisted.export_rows(catalog, state, workspace.proposals)
    reference = assisted.write_reader_snapshot(
        rows,
        catalog,
        tmp_path / "reference",
        {rows[0]["imageId"]: "training", rows[1]["imageId"]: "development"},
    )
    root = tmp_path / "r"
    settings = {"python": sys.executable, "pythonpath": "unused", "snapshot": str(reference)}
    launched = []
    # The inline worker below runs in this process; once it returns the attempt is over.
    manager = NeuralGridRunManager(
        root,
        validate=validator(settings),
        models=(protocol.MODEL_VERSION,),
        settings=settings,
        launcher=launched.append,
        state_type=protocol.NeuralGridRunState,
        admit=protocol.admit_run,
        identity=lambda pid: None,
    )
    tiny = _tiny_preset()
    fingerprint = protocol.FROZEN_PRESET_FINGERPRINTS["D"]
    original_initial = finetune.initial_weights

    def initial(manager_, run, settings_, iteration):
        if iteration == 1:  # run-1 weights live outside the test; any network state will do
            return NeuralGridNetwork().state_dict(), [], {"source": "test"}
        return original_initial(manager_, run, settings_, iteration)

    def inline_worker(manager_, run_id, log):
        run = manager_.detail(run_id)
        lease = token(run)
        manager_.claim(run_id, lease)
        finetune.run_iteration_attempt(manager_, run_id, lease, device="cpu")
        return manager_.detail(run_id)

    def fake_export(manager_, run_id, iteration, snapshot):
        _, best, _, checkpoint = finetune.load_iteration_state(manager_, run_id, iteration)
        destination = root / run_id / "exports" / f"iteration{iteration:02d}"
        destination.mkdir(parents=True)
        (destination / "bundle.json").write_text(
            json.dumps(
                {
                    "files": {"screen.onnx": "e" * 64},
                    "weights_sha256": hashlib.sha256(checkpoint.encode()).hexdigest(),
                    "preset_fingerprint": fingerprint,
                    "provenance": {"checkpoint_sha256": checkpoint, "candidate": best["candidate"]},
                }
            )
        )
        return destination

    engine = FakeEngine()
    monkeypatch.setattr(finetune, "load_preset", lambda name: (tiny, fingerprint))
    monkeypatch.setattr(finetune, "validate_request", lambda request: tiny)
    monkeypatch.setattr(finetune, "_manager_for", lambda args: manager)
    monkeypatch.setattr(finetune, "wait_for", inline_worker)
    monkeypatch.setattr(finetune, "initial_weights", initial)
    monkeypatch.setattr(finetune, "export_iteration", fake_export)
    monkeypatch.setattr(neural_grid_inference, "onnx_engine", lambda bundle, threads=None: engine)
    args = argparse.Namespace(
        root=root,
        snapshot=reference,
        init_root=root,
        python=None,
        smoke=False,
        catalog=catalog.root,
        annotations=store.root,
        proposals=tmp_path / "proposals",
        no_wait=False,
        allow_same_data=False,
    )

    finetune.command_iterate(args)
    ledger = finetune.Ledger(root, "train", fingerprint).load()
    assert ledger["iterations"]["1"]["status"] == "done"
    run = manager.detail(ledger["run_id"])
    assert run.attempt == 1 and run.checkpoint_epoch == 1
    assert run.status == "cancelled" and run.error == finetune.ITERATION_COMPLETE
    used = run.used_seconds
    assert used > 0
    plan = finetune.read_plan(root, "train", 1)
    holdout = finetune.holdout_ids(ledger["holdout"])
    assert len(holdout) == 1 and plan["holdout_ids"] == sorted(holdout)
    assert not set(plan["train_ids"]) & holdout
    trained = load_samples(Path(plan["snapshot"]["directory"]), ["training"])
    assert {s.image_id for s in trained} == set(plan["train_ids"])
    report = json.loads(
        (finetune.iteration_directory(root, "train", 1) / "report.json").read_text("utf-8")
    )
    measurements = report["measurements"]
    assert measurements["mumie_holdout"]["photos"] == 1
    assert measurements["mumie_holdout"]["small_sample"]
    assert measurements["development_777"]["delta_percentage_points"] is not None
    assert measurements["proposal_accuracy_last_batch"]["photos"] == 2
    assert measurements["proposal_accuracy_last_batch"]["unchanged_share_of_boards"] == 1.0
    assert report["training"]["selected_candidate"] == 2
    # New proposals: a separate immutable set from the iteration model, incomplete photos only.
    proposals = workspace.refresh_proposals()
    assert proposals.generation == 1 and proposals.sets[0] == base.set_id
    newest = read_checked(tmp_path / "proposals" / proposals.set_id / "proposals.json")
    assert newest["model"]["iteration"] == 1 and newest["model"]["run_id"] == run.id
    assert [item["source_id"] for item in newest["items"]] == [third["source_id"]]
    assert "Iteracja 1" in (finetune.iteration_directory(root, "train", 1) / "report.md").read_text(
        "utf-8"
    )

    # Same data again: refused before any training, nothing charged.
    with pytest.raises(SystemExit, match="NO_NEW_PHOTOS"):
        finetune.command_iterate(args)
    assert manager.detail(run.id).used_seconds == used and manager.detail(run.id).attempt == 1

    # Next batch; the iterate command is interrupted after launching the attempt.
    accept_all(workspace, third["source_id"])
    finetune.command_iterate(argparse.Namespace(**{**vars(args), "no_wait": True}))
    queued = manager.detail(run.id)
    assert queued.attempt == 2 and queued.status == "queued"
    ledger = finetune.Ledger(root, "train", fingerprint).load()
    assert ledger["iterations"]["2"]["status"] == "planned"
    # Re-running continues the same iteration and does not plan or launch another one.
    finetune.command_iterate(args)
    run = manager.detail(run.id)
    assert run.attempt == 2 and run.checkpoint_epoch == 2 and run.used_seconds > used
    ledger = finetune.Ledger(root, "train", fingerprint).load()
    assert [ledger["iterations"][k]["status"] for k in ("1", "2")] == ["done", "done"]
    assert ledger["iterations"]["2"]["proposals"] is None  # every Mumie photo is complete
    history = finetune.load_iteration_state(manager, run.id, 2)[2]
    assert history["init"]["source"] == "previous_iteration"
    # Roles given in iteration 1 are kept; the new photo got the next number.
    registry = ledger["holdout"]
    assert {registry[s["source_id"]]["iteration"] for s in (first, second)} == {1}
    assert registry[third["source_id"]] | {"iteration": 2} == registry[third["source_id"]]
    assert registry[third["source_id"]]["position"] == 3
    assert finetune.holdout_ids(registry) == holdout
