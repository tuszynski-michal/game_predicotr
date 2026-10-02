"""Read-only dev/validation proposal coverage. Never starts a run or touches holdout pixels."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from game_predictor_worker.vision_lab.annotations import read_checked
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.hybrid_data import prepare_partition
from game_predictor_worker.vision_lab.hybrid_protocol import (
    MODEL_VERSION,
    PREPROCESSING_VERSION,
    WEIGHTS_FILENAME,
    protocol,
    protocol_digest,
    validate_protocol,
)
from game_predictor_worker.vision_lab.run_contracts import StartRunRequest, TrainingConfiguration
from game_predictor_worker.vision_lab.training_manifest import ManifestAdapter

parser = argparse.ArgumentParser()
parser.add_argument("--snapshot", type=Path, required=True)
parser.add_argument("--annotations", type=Path, required=True)
parser.add_argument("--manifest", type=Path, required=True)
parser.add_argument("--partition", choices=["development", "validation"], required=True)
parser.add_argument("--offset", type=int, default=0)
parser.add_argument("--limit", type=int, default=8)
args = parser.parse_args()
state_path = args.annotations / "state.json"
before = hashlib.sha256(state_path.read_bytes()).hexdigest()
request = StartRunRequest(
    request_id="hybrid-readonly-preflight",
    manifest_id=args.manifest.stem,
    model_version=MODEL_VERSION,
    preprocessing_version=PREPROCESSING_VERSION,
    protocol_digest=protocol_digest(),
    seed=20260927,
    purpose="smoke",
    configuration=TrainingConfiguration(
        epochs=1, batch_size=8, learning_rate=0.001, max_steps=50, max_seconds=1800
    ),
)
validate_protocol(request, args.manifest.parent.parent / "cache" / WEIGHTS_FILENAME)
catalog = Catalog(args.snapshot)
inputs = ManifestAdapter(args.manifest.parent, catalog, args.annotations)(request)
targets = getattr(inputs, args.partition)
ids = sorted({target.source_id for target in targets})[args.offset : args.offset + args.limit]
selected = tuple(target for target in targets if target.source_id in ids)
_, coverage = prepare_partition(
    inputs, selected, lambda: print("preflight source (dev/val only)", file=sys.stderr, flush=True)
)
assert hashlib.sha256(state_path.read_bytes()).hexdigest() == before
print(
    json.dumps(
        {
            "partition": args.partition,
            "offset": args.offset,
            "coverage": coverage,
            "protocol": protocol(),
            "protocol_digest": protocol_digest(),
            "manifest_id": args.manifest.stem,
            "state_sha256": before,
            "annotation_revision": read_checked(state_path)["state"]["revision"],
            "decoded_source_ids": ids,
            "holdout_decodes": 0,
            "started_runs": 0,
        }
    )
)
