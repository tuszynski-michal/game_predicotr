"""Read-only verification of a frozen pilot using the production manifest adapter."""

import argparse
import json
from pathlib import Path

from game_predictor_worker.vision_lab.annotations import read_checked
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.run_contracts import StartRunRequest, TrainingConfiguration
from game_predictor_worker.vision_lab.training_manifest import ManifestAdapter

parser = argparse.ArgumentParser()
parser.add_argument("--snapshot", type=Path, required=True)
parser.add_argument("--annotations", type=Path, required=True)
parser.add_argument("--manifest", type=Path, required=True)
args = parser.parse_args()
before = read_checked(args.annotations / "state.json")
adapter = ManifestAdapter(args.manifest.parent, Catalog(args.snapshot), args.annotations)
request = StartRunRequest(
    request_id="readonly-manifest-check",
    manifest_id=args.manifest.stem,
    model_version="not-started",
    preprocessing_version="not-started",
    seed=1,
    purpose="smoke",
    configuration=TrainingConfiguration(max_steps=1),
)
inputs = adapter(request)
assert read_checked(args.annotations / "state.json") == before
print(
    json.dumps(
        {
            "manifest_id": inputs.manifest_id,
            "split_fingerprint": inputs.split_fingerprint,
            "development": len(inputs.development),
            "validation": len(inputs.validation),
            "annotation_revision": before["state"]["revision"],
            "annotation_payload_unchanged": True,
            "decoded_images": 0,
            "started_runs": 0,
        }
    )
)
