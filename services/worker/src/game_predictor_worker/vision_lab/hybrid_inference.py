"""Checksum-bound opt-in ORT geometry; no manual targets enter the image engine."""

import json

import numpy as np
import onnxruntime as ort  # type: ignore[import-untyped]
from numpy.typing import NDArray

from .annotations import read_checked
from .catalog import Catalog
from .contracts import GeometryResult, Topology
from .hybrid_data import normalized_batch, proposals, result_from_deltas
from .hybrid_protocol import MODEL_VERSION, protocol_digest
from .run_files import verify_artifact
from .runs import RunManager
from .training_manifest import TrainingInputs


class HybridGeometryEngine:
    def __init__(self, model: bytes) -> None:
        self.session = ort.InferenceSession(model, providers=["CPUExecutionProvider"])

    def detect(self, source_id: str, rgb: NDArray[np.uint8], topology: Topology) -> GeometryResult:
        if topology.columns != 5:
            return GeometryResult(
                source_id=source_id,
                topology=topology,
                model_version=MODEL_VERSION,
                status="unsupported",
                reasons=["HYBRID_TOPOLOGY_UNSUPPORTED"],
            )
        values, errors = proposals(source_id, rgb)
        predictions = []
        for start in range(0, len(values), 8):
            predictions.append(
                self.session.run(
                    ["delta"], {"pixels": normalized_batch(values[start : start + 8])}
                )[0]
            )
        deltas = np.concatenate(predictions) if predictions else np.empty((0, 8), dtype=np.float32)
        result = result_from_deltas(source_id, rgb.shape[1], rgb.shape[0], values, deltas)
        result.reasons.extend(errors)
        return result


def authorized_engine(
    manager: RunManager, run_id: str, catalog: Catalog, source_id: str
) -> HybridGeometryEngine:
    run = manager.detail(run_id)
    if run.status != "succeeded" or run.request.model_version != MODEL_VERSION:
        raise ValueError("HYBRID_RUN_NOT_READY")
    inputs = manager.validate(run.request)
    if not isinstance(inputs, TrainingInputs) or run.request.protocol_digest != protocol_digest():
        raise ValueError("RUN_PROTOCOL_MISMATCH")
    allowed = {target.source_id for target in (*inputs.development, *inputs.validation)}
    if source_id not in allowed:
        # Only metadata consulted before returning; no source image decoding.
        if manager.settings is None:
            raise ValueError("SOURCE_NOT_IN_TRAINING_PARTITIONS")
        from pathlib import Path

        from .snapshot import safe_file

        payload = read_checked(
            safe_file(Path(manager.settings["manifests"]), f"{run.request.manifest_id}.json")
        )
        source = catalog.sources[source_id]
        partition = payload["game_partitions"].get(source.game_id)
        raise ValueError(
            "HOLDOUT_NOT_RELEASED"
            if partition in {"final_test", "unseen_game"}
            else "SOURCE_NOT_IN_TRAINING_PARTITIONS"
        )
    if run.report is None or set(run.artifacts) != {"onnx", "best_weights"}:
        raise ValueError("RUN_SUCCESS_ARTIFACT_MISSING")
    report = json.loads(verify_artifact(manager.root, run.report).read_bytes())
    if report.get("artifacts") != {
        name: value.model_dump() for name, value in run.artifacts.items()
    }:
        raise ValueError("RUN_ARTIFACT_BINDING_MISMATCH")
    if report["metrics"].get("protocol_digest") != protocol_digest():
        raise ValueError("RUN_PROTOCOL_MISMATCH")
    return HybridGeometryEngine(verify_artifact(manager.root, run.artifacts["onnx"]).read_bytes())
