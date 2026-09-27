"""One tiny synthetic end-to-end worker proof; never a pilot run or operator image."""

import argparse
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import cast

os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

import numpy as np
import torch
from game_predictor_worker.vision_lab import hybrid_data
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.contracts import GeometryResult, Topology
from game_predictor_worker.vision_lab.hybrid_protocol import (
    MODEL_VERSION,
    PREPROCESSING_VERSION,
    WEIGHTS_FILENAME,
    protocol_digest,
    validate_protocol,
)
from game_predictor_worker.vision_lab.run_contracts import StartRunRequest, TrainingConfiguration
from game_predictor_worker.vision_lab.run_worker import execute
from game_predictor_worker.vision_lab.runs import RunManager, token
from game_predictor_worker.vision_lab.training_adapter import TRAINERS
from game_predictor_worker.vision_lab.training_manifest import TrainingInputs, TrainingTarget
from numpy.typing import NDArray
from PIL import Image


class FixtureEngine:
    def detect(self, source_id: str, rgb: NDArray[np.uint8], topology: Topology) -> GeometryResult:
        quad = np.array([[30, 30], [180, 30], [180, 150], [30, 150]], dtype=np.float32)
        board = hybrid_data.grid_from_quad(quad, 224, 224, 0)
        return GeometryResult(
            source_id=source_id,
            topology=topology,
            model_version="fixture-only",
            status="detected",
            boards=[board],
            width=224,
            height=224,
        )


parser = argparse.ArgumentParser()
parser.add_argument("--cache", type=Path, required=True)
args = parser.parse_args()
torch.set_num_threads(1)
hybrid_data.BaselineEngine = FixtureEngine  # type: ignore[assignment,attr-defined]
catalog = SimpleNamespace(
    sources={name: name for name in ("fixture-dev", "fixture-val")},
    image=lambda source: Image.fromarray(np.full((224, 224, 3), 127, dtype=np.uint8)),
)
quad = np.array([[31, 31], [181, 31], [181, 151], [31, 151]], dtype=np.float32)
target_nodes = tuple(
    (point.x, point.y) for point in hybrid_data.grid_from_quad(quad, 224, 224, 0).nodes
)
inputs = TrainingInputs(
    "a" * 64,
    "b" * 64,
    (TrainingTarget("fixture-dev", 0, 1, target_nodes),),
    (TrainingTarget("fixture-val", 0, 1, target_nodes),),
    cast(Catalog, catalog),
)


def validate(request: StartRunRequest) -> TrainingInputs:
    validate_protocol(request, args.cache / WEIGHTS_FILENAME)
    return inputs


with tempfile.TemporaryDirectory(prefix="hybrid-worker-fixture-") as temporary:
    root = Path(temporary)
    settings = {"manifests": str(args.cache.parent / "manifests"), "python": "fixture-not-spawned"}
    manager = RunManager(
        root,
        validate=validate,
        models=tuple(TRAINERS),
        settings=settings,
        launcher=lambda run: None,
    )
    request = StartRunRequest(
        request_id="synthetic-integration-only",
        manifest_id=inputs.manifest_id,
        model_version=MODEL_VERSION,
        preprocessing_version=PREPROCESSING_VERSION,
        protocol_digest=protocol_digest(),
        seed=20260927,
        purpose="smoke",
        configuration=TrainingConfiguration(
            epochs=1, batch_size=8, learning_rate=0.001, max_steps=1, max_seconds=90
        ),
    )
    run = manager.create_or_get_run(request)
    execute(manager, run.id, token(run))
    # New manager proves the result comes from durable state, not a returned object.
    observed = RunManager(root, validate=validate, models=tuple(TRAINERS)).detail(run.id)
    assert observed.status == "succeeded"
    assert observed.report is not None
    assert observed.checkpoint_epoch == 1 and observed.best_epoch == 1
    assert observed.reserved_steps == 1 and set(observed.artifacts) == {"onnx", "best_weights"}
    print(
        json.dumps(
            {
                "fixture": "synthetic-only",
                "operator_images": 0,
                "lab_runs": 0,
                "worker_pid": observed.pid,
                "status": observed.status,
                "epoch": observed.checkpoint_epoch,
                "artifacts": {key: value.sha256 for key, value in observed.artifacts.items()},
                "report_sha": observed.report.sha256,
                "used_seconds": observed.used_seconds,
            }
        )
    )
