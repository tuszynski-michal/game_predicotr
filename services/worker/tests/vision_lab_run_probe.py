"""Bounded subprocess fixture; never registered as an API training model."""

import sys
import time
from pathlib import Path

from game_predictor_worker.vision_lab.runs import RunManager

root, run_id, attempt, fence, lease, mode = sys.argv[1:]
manager = RunManager(Path(root), validate=lambda request: None, models=("test",))
identity = (int(attempt), int(fence), lease)
if mode == "watchdog":
    from game_predictor_worker.vision_lab import run_worker
    from game_predictor_worker.vision_lab.run_worker import execute
    from game_predictor_worker.vision_lab.training_adapter import TRAINERS
    from game_predictor_worker.vision_lab.training_manifest import TrainingInputs
    from test_vision_lab_runs import checkpoint_content

    run_worker.validate_runtime = lambda: None
    manager.validate = lambda request: TrainingInputs(request.manifest_id, "split", (), (), None)

    def hang(inputs, request, control):
        current = manager.detail(run_id)
        control.checkpoint(checkpoint_content(current, 0), 0)
        time.sleep(10)
        raise AssertionError("watchdog did not stop worker")

    TRAINERS["test"] = hang
    execute(manager, run_id, identity)
    sys.exit(0)
manager.claim(run_id, identity)
from test_vision_lab_runs import checkpoint_content  # noqa: E402

run = manager.detail(run_id)
manager.checkpoint(run_id, identity, checkpoint_content(run, 0), 0)
if mode == "crash":
    manager.heartbeat(run_id, identity, reserve_step=True)
    sys.exit(7)
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    try:
        run = manager.heartbeat(run_id, identity)
        if mode == "success" or run.cancel_requested:
            manager.checkpoint(run_id, identity, checkpoint_content(run, 1), 1)
            manager.finish(run_id, identity, status="succeeded")
            sys.exit(0)
    except ValueError as error:
        if str(error) != "ANNOTATION_STORE_BUSY":
            raise
    time.sleep(0.05)
raise TimeoutError("probe deadline")
