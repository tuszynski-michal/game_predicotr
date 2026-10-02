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


# --- preset E: rules revision after iteration 1 of preset D (D-490) ----------------------------


def test_preset_e_is_frozen_rules_only_and_pins_the_run1_reference():
    preset_d, fingerprint_d = protocol.load_preset("D")
    preset_e, fingerprint_e = protocol.load_preset("E")
    assert fingerprint_e == protocol.FROZEN_PRESET_FINGERPRINTS["E"] != fingerprint_d
    assert fingerprint_d == "b94a9627df4c2d0886b43776f1a80b406de5d124c36c997ada2b5f93c5d1cbd9"
    assert preset_d.finetune.guard_777 is None
    assert protocol.training_equivalent(preset_d, preset_e)
    guard = preset_e.finetune.guard_777
    assert guard.applies_from_iteration == protocol.RULES_FROM_ITERATION == 2
    assert guard.replaces_preset_fingerprint == fingerprint_d
    assert (guard.level, guard.run1_level_photo_complete_correct, guard.run1_level_photos) == (
        "B",
        298,
        300,
    )
    assert guard.run1_image_macro == preset_d.finetune.init.development_image_macro
    assert guard.level_max_drop == 0.005 and guard.min_detection_recall == 1.0
    assert guard.max_false_boards == 0
    changed = preset_e.model_copy(
        update={"optimization": preset_e.optimization.model_copy(update={"learning_rate": 2e-4})}
    )
    assert not protocol.training_equivalent(preset_d, changed)
    with pytest.raises(ValueError, match="RULES_PRESET_NOT_A_RUN"):  # never a run of its own
        _request("E")
    payload = _request("D").model_dump()
    payload["preset"] = "E"
    with pytest.raises(ValueError):  # nor can a request name it
        protocol.NeuralGridRunRequest.model_validate(payload)


def _development(level_correct=297, macro=0.00287, recall=1.0, false_boards=0):
    return {
        "photo_complete_correct_rate": 0.90,  # the preset-D measure no longer guards
        "image_macro": macro,
        "detection_recall": recall,
        "false_boards": false_boards,
        "by_level": {
            "B": {
                "photos": 300,
                "photo_complete_correct": level_correct,
                "photo_complete_correct_rate": level_correct / 300,
            }
        },
    }


def test_guard_e_conditions_each_fail_alone():
    guard = protocol.load_preset("E")[0].finetune.guard_777
    passing = finetune.guard_777(_development(), guard)
    assert passing["admissible"] and passing["failed"] == []
    assert passing["level_photo_complete_correct"] == 297
    cases = {
        "a_level_rate": _development(level_correct=296),  # 98.67% < 99.33% - 0.5 pp
        "b_image_macro": _development(macro=0.0028704),
        "c_detection_recall": _development(recall=5399 / 5400),
        "c_false_boards": _development(false_boards=1),
    }
    for condition, development in cases.items():
        result = finetune.guard_777(development, guard)
        assert result["failed"] == [condition] and not result["admissible"]
    missing = finetune.guard_777({"image_macro": 0.002}, guard)
    assert set(missing["failed"]) == {"a_level_rate", "c_detection_recall", "c_false_boards"}
    exact = _development(macro=guard.run1_image_macro)
    assert finetune.guard_777(exact, guard)["admissible"]  # "not worse" includes equal


def test_selection_e_lowest_holdout_image_macro_among_admissible():
    settings = protocol.load_preset("E")[0].finetune

    def candidate(index, holdout_macro, development=None):
        return {
            "candidate": index,
            "development": development or _development(),
            "holdout": {"photo_complete_correct_rate": 1.0, "image_macro": holdout_macro},
        }

    candidates = [
        candidate(1, 0.0054),
        candidate(2, 0.0040, _development(level_correct=290)),  # best holdout, guard fails
        candidate(3, 0.0051),
        candidate(4, 0.0052),
    ]
    assert finetune.select_candidate(candidates, settings, 5) == (3, finetune.GUARD_RULE)
    # Small holdout: the same rule (not "last admissible"); the report flags the sample.
    assert finetune.select_candidate(candidates, settings, 2) == (3, finetune.GUARD_RULE)
    tie = [
        candidate(1, 0.005, _development(macro=0.0028)),
        candidate(2, 0.005, _development(macro=0.0027)),
        candidate(3, 0.005, _development(macro=0.0027)),
    ]
    assert finetune.select_candidate(tie, settings, 5)[0] == 2
    assert finetune.select_candidate([candidates[1]], settings, 5) == (
        None,
        finetune.GUARD_REJECTED,
    )
    assert finetune.select_candidate(candidates, settings, 0, smoke=True)[0] == 4


def test_iteration_1_candidates_of_preset_d_pass_the_e_guard():
    """Iteration 1 numbers of run 5bc98156 (level B from the checkpoint history: 300/300)."""

    settings = protocol.load_preset("E")[0].finetune
    observed = [(1, 0.0027834310782030676, 0.005398694697877696)]
    observed += [(2, 0.002710458041773426, 0.005114510983644488)]
    observed += [(3, 0.0027255787444075063, 0.005064611201606301)]
    candidates = [
        {
            "candidate": index,
            "development": _development(level_correct=300, macro=macro),
            "holdout": {"image_macro": holdout},
        }
        for index, macro, holdout in observed
    ]
    assert all(
        finetune.guard_777(c["development"], settings.guard_777)["admissible"] for c in candidates
    )
    assert finetune.select_candidate(candidates, settings, 2) == (3, finetune.GUARD_RULE)


def test_rules_revision_continues_the_same_run_and_budget(tmp_path, monkeypatch):
    clock = [1000.0]
    manager = _manager(tmp_path, clock)
    for name in ("A", "B"):
        run = manager.create_or_get_run(_request(name))
        manager.cancel_run(run.id, RunMutation(request_id=f"cancel-{name}", expected_attempt=1))
    run = manager.create_or_get_run(_request("D"))
    lease = token(run)
    manager.claim(run.id, lease)
    clock[0] += 682
    manager.heartbeat(run.id, lease)
    manager.checkpoint(run.id, lease, _checkpoint(run.request, 1), 1)
    manager.finish(run.id, lease, status="cancelled", error=finetune.ITERATION_COMPLETE)
    preset_d, fingerprint_d = protocol.load_preset("D")
    ledger = {"run_id": run.id, "holdout": {}, "iterations": {"1": {"status": "done"}}}
    assert finetune.rules_revision(ledger, 1, fingerprint_d, preset_d) == {
        "preset": "D",
        "preset_fingerprint": fingerprint_d,
    }
    assert "rules_revisions" not in ledger
    rules = finetune.rules_revision(ledger, 2, fingerprint_d, preset_d)
    assert rules["preset"] == "E" and rules["run_preset_fingerprint"] == fingerprint_d
    assert rules["preset_fingerprint"] == protocol.FROZEN_PRESET_FINGERPRINTS["E"]
    [revision] = ledger["rules_revisions"]
    assert revision["from_iteration"] == 2 and revision["run_id"] == run.id
    assert revision["replaces_preset_fingerprint"] == fingerprint_d
    assert finetune.rules_revision(ledger, 3, fingerprint_d, preset_d)["from_iteration"] == 2
    assert len(ledger["rules_revisions"]) == 1
    # Worker side: the plan's rules are accepted only with E's frozen fingerprint.
    plan = {"preset_fingerprint": fingerprint_d, "rules": rules}
    assert finetune.plan_rules(plan, preset_d)[0].name == "E"
    assert finetune.plan_rules({"preset_fingerprint": fingerprint_d}, preset_d)[0] is preset_d
    with pytest.raises(ValueError, match="RULES_PRESET_MISMATCH"):
        finetune.plan_rules({**plan, "rules": {**rules, "preset_fingerprint": "0" * 64}}, preset_d)
    # No fourth run: the budget run D continues; used seconds are carried, not reset.
    with pytest.raises(ValueError, match="BUDGET_EXHAUSTED"):
        manager.create_or_get_run(_request("C", request_id="neural-C-fourth"))
    second = manager.retry_run(run.id, RunMutation(request_id="iteration-2", expected_attempt=1))
    assert second.id == run.id and second.attempt == 2
    assert second.used_seconds == pytest.approx(682)
    assert second.request.preset == "D" and second.request.preset_fingerprint == fingerprint_d
    assert second.request.configuration.max_seconds == 14400
    # A rules preset that changes training is refused on both sides.
    preset_e, fingerprint_e = protocol.load_preset("E")
    changed = preset_e.model_copy(
        update={"optimization": preset_e.optimization.model_copy(update={"learning_rate": 2e-4})}
    )
    monkeypatch.setattr(finetune, "load_preset", lambda name: (changed, fingerprint_e))
    with pytest.raises(ValueError, match="TRAINING_MISMATCH"):
        finetune.plan_rules(plan, preset_d)
    with pytest.raises(ValueError, match="TRAINING_MISMATCH"):
        finetune.rules_revision({"run_id": run.id}, 2, fingerprint_d, preset_d)


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


def test_iteration_2_under_preset_e_reuses_data_after_an_unselected_iteration(
    tmp_path, monkeypatch
):
    """Iteration 1 (rules D) selects nothing; iteration 2 runs on the same photos under the
    rules of E in the same run (new attempt, used seconds carried, no new run)."""

    pytest.importorskip("torch")
    from game_predictor_worker.vision_lab.neural_grid_model import NeuralGridNetwork
    from game_predictor_worker.vision_lab.neural_grid_runs import NeuralGridRunManager, validator

    catalog, store, training, bundle = lab(tmp_path)
    publish(tmp_path, catalog, store, training, bundle)
    workspace = assisted.Workspace(catalog, store.root, tmp_path / "proposals", games=("mumie",))
    first, _ = first_photo(workspace, 0)
    second, _ = first_photo(workspace, 1)
    accept_all(workspace, first["source_id"])
    state = accept_all(workspace, second["source_id"])
    rows = assisted.export_rows(catalog, state, workspace.proposals)
    reference = assisted.write_reader_snapshot(
        rows,
        catalog,
        tmp_path / "reference",
        {rows[0]["imageId"]: "training", rows[1]["imageId"]: "development"},
    )
    root = tmp_path / "r"
    settings = {"python": sys.executable, "pythonpath": "unused", "snapshot": str(reference)}
    manager = NeuralGridRunManager(
        root,
        validate=validator(settings),
        models=(protocol.MODEL_VERSION,),
        settings=settings,
        launcher=lambda run: None,
        state_type=protocol.NeuralGridRunState,
        admit=protocol.admit_run,
        identity=lambda pid: None,
    )
    base = _tiny_preset()
    # Rules D reject every candidate: run 1's development rate is pinned at 100%.
    tiny_d = base.model_copy(
        update={
            "finetune": base.finetune.model_copy(
                update={
                    "development_max_drop": 0.0,
                    "init": base.finetune.init.model_copy(
                        update={"development_photo_complete_correct_rate": 1.0}
                    ),
                }
            )
        }
    )
    guard = protocol.load_preset("E")[0].finetune.guard_777
    tiny_e = tiny_d.model_copy(
        update={
            "name": "E",
            "hypothesis": "rules only",
            "finetune": tiny_d.finetune.model_copy(
                update={"version": "neural-grid-finetune-v2", "guard_777": guard}
            ),
        }
    )
    fingerprints = protocol.FROZEN_PRESET_FINGERPRINTS
    original_initial = finetune.initial_weights

    def initial(manager_, run, settings_, iteration):
        if iteration == 1:
            return NeuralGridNetwork().state_dict(), [], {"source": "test"}
        return original_initial(manager_, run, settings_, iteration)

    def inline_worker(manager_, run_id, log):
        run = manager_.detail(run_id)
        lease = token(run)
        manager_.claim(run_id, lease)
        finetune.run_iteration_attempt(manager_, run_id, lease, device="cpu")
        return manager_.detail(run_id)

    monkeypatch.setattr(
        finetune,
        "load_preset",
        lambda name: (tiny_e, fingerprints["E"]) if name == "E" else (tiny_d, fingerprints["D"]),
    )
    monkeypatch.setattr(finetune, "validate_request", lambda request: tiny_d)
    monkeypatch.setattr(finetune, "_manager_for", lambda args: manager)
    monkeypatch.setattr(finetune, "wait_for", inline_worker)
    monkeypatch.setattr(finetune, "initial_weights", initial)
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
    ledger = finetune.Ledger(root, "train", fingerprints["D"]).load()
    assert ledger["iterations"]["1"]["model_unchanged"] is True
    assert ledger["iterations"]["1"]["rules_preset"] == "D"
    assert "rules" not in finetune.read_plan(root, "train", 1)
    first_report = finetune.iteration_directory(root, "train", 1) / "report.json"
    frozen = first_report.read_bytes()
    run = manager.detail(ledger["run_id"])
    used = run.used_seconds
    assert used > 0

    # Same photos again: allowed because iteration 1 kept its start state.
    finetune.command_iterate(args)
    ledger = finetune.Ledger(root, "train", fingerprints["D"]).load()
    assert [ledger["iterations"][k]["status"] for k in ("1", "2")] == ["done", "done"]
    [revision] = ledger["rules_revisions"]
    assert revision["preset"] == "E" and revision["from_iteration"] == 2
    assert revision["preset_fingerprint"] == fingerprints["E"]
    assert revision["replaces_preset_fingerprint"] == fingerprints["D"]
    plan = finetune.read_plan(root, "train", 2)
    assert plan["same_data"] == {
        "reused": True,
        "reason": "previous_iteration_selected_no_state",
        "previous_iteration": 1,
    }
    assert plan["rules"]["preset"] == "E" and plan["preset_fingerprint"] == fingerprints["D"]
    after = manager.detail(run.id)
    assert after.attempt == 2 and after.checkpoint_epoch == 2 and after.used_seconds > used
    train_runs = [r for r in manager.list(0, 100).runs if r.request.purpose == "train"]
    assert [r.id for r in train_runs] == [run.id]  # no new run
    assert first_report.read_bytes() == frozen  # iteration 1 stays untouched
    history = finetune.load_iteration_state(manager, run.id, 2)[2]
    assert history["init"]["previous_selected_candidate"] is None
    assert history["rules"]["preset"] == "E"
    report = json.loads(
        (finetune.iteration_directory(root, "train", 2) / "report.json").read_text("utf-8")
    )
    assert report["rules"]["preset"] == "E" and "D-490" in report["rules"]["note"]
    # Lab photos are not level B, so condition (a) fails and the start state is kept.
    assert report["training"]["selection_rule"] == finetune.GUARD_REJECTED
    for candidate in report["training"]["candidates"]:
        assert "a_level_rate" in candidate["guard"]["failed"]
        assert set(candidate["holdout_change"]) == {
            "image_macro_before",
            "image_macro_after",
            "nme_median_before",
            "nme_median_after",
        }
    assert report["data"]["same_data_as_previous_iteration"]["reused"]
    assert report["measurements"]["development_777"]["guard_777"]["level"] == "B"
    markdown = (finetune.iteration_directory(root, "train", 2) / "report.md").read_text("utf-8")
    assert "Reguły wyboru: preset E" in markdown and "(a) poziom B" in markdown
