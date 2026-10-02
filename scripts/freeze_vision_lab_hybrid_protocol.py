"""Create-only protocol registration and exact proposed requests; never starts training."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal, cast

from game_predictor_worker.vision_lab.hybrid_protocol import (
    MODEL_VERSION,
    PREPROCESSING_VERSION,
    WEIGHTS_FILENAME,
    WEIGHTS_SHA256,
    freeze_protocol,
    protocol,
    protocol_digest,
    validate_protocol,
)
from game_predictor_worker.vision_lab.run_contracts import StartRunRequest, TrainingConfiguration

parser = argparse.ArgumentParser()
parser.add_argument("--cache", type=Path, required=True)
parser.add_argument("--manifest-id", required=True)
args = parser.parse_args()
weights = args.cache / WEIGHTS_FILENAME
if hashlib.sha256(weights.read_bytes()).hexdigest() != WEIGHTS_SHA256:
    raise ValueError("RUN_PROTOCOL_MISMATCH")
registration = freeze_protocol(args.cache)
requests = {}
for purpose, epochs, steps in (("smoke", 1, 50), ("train", 20, 10000)):
    request = StartRunRequest(
        request_id=f"d457-hybrid-v1-{purpose}-20260927",
        manifest_id=args.manifest_id,
        model_version=MODEL_VERSION,
        preprocessing_version=PREPROCESSING_VERSION,
        protocol_digest=protocol_digest(),
        seed=20260927,
        purpose=cast(Literal["smoke", "train"], purpose),
        configuration=TrainingConfiguration(
            epochs=epochs, batch_size=8, learning_rate=0.001, max_steps=steps, max_seconds=1800
        ),
    )
    validate_protocol(request, weights)
    requests[purpose] = request.model_dump()
print(
    json.dumps(
        {
            "protocol": protocol(),
            "protocol_digest": protocol_digest(),
            "registration": str(registration),
            "requests": requests,
            "started_runs": 0,
        }
    )
)
