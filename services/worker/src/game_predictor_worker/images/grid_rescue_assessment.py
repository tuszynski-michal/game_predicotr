"""Evaluate the exported, admitted path on controls without optimizer access."""

import hashlib
import json
from pathlib import Path
from typing import Any

from game_predictor_api.domain.grid_rescue_policy import require_rescue_evidence
from game_predictor_api.storage.grid_content_bundle import read_content_bundle_bytes

from ..geometry_core.rescue import GridRescueVariantV1
from .grid_rescue_strategy import RescueResult, execute_path


def load_assessment_engine(directory: Path, expected_sha: str, threads: int) -> Any:
    """Apply the assessment limit before ONNX construction reads the bundle."""
    from ..geometry_core.inference import onnx_engine

    payload = read_content_bundle_bytes(directory / "bundle.json")
    if hashlib.sha256(payload).hexdigest() != expected_sha:
        raise ValueError("GRID_RESCUE_BUNDLE_CHANGED")
    return assessment_engine(
        onnx_engine(directory, threads, expected_bundle_sha256=expected_sha, bundle_bytes=payload),
        directory,
        expected_sha,
    )


class RescueAssessmentEngine:
    def __init__(self, engine: Any, proof: dict[str, Any]) -> None:
        self.engine = engine
        self.path = proof["selection"]["selectedPath"]
        self.variant = GridRescueVariantV1.model_validate(proof["recipe"]["variant"])
        self.routing = proof["selection"]["pathProofs"][self.path].get("routing")
        self.last_baseline: list[Any] = []
        self.last_result: RescueResult | None = None

    def analyse(self, rgb: Any) -> list[Any]:
        baseline = self.engine.analyse(rgb)
        self.last_baseline = baseline
        self.last_result = execute_path(
            baseline,
            width=rgb.shape[1],
            height=rgb.shape[0],
            variant=self.variant,
            path=self.path,
            expected_positions=set(range(9)),
            routing=self.routing,
            detect=lambda geometry: self.engine.detect(rgb, geometry=geometry),
            recrop=lambda position, detection, geometry: self.engine.recrop(
                rgb, detection, geometry=geometry
            ),
        )
        return self.last_result.detections


def assessment_engine(engine: Any, directory: Path, expected_sha: str) -> Any:
    path = directory / "bundle.json"
    payload = read_content_bundle_bytes(path)
    if hashlib.sha256(payload).hexdigest() != expected_sha:
        raise ValueError("GRID_RESCUE_BUNDLE_CHANGED")
    bundle = json.loads(payload)
    if "contentRescue" in bundle:
        from game_predictor_api.domain.grid_content_experiment_evidence import (
            require_content_experiment_evidence,
        )

        from .grid_content_experiment_data import ContentAssessmentEngine

        require_content_experiment_evidence(bundle)
        rescue = bundle["contentRescue"]
        return (
            engine
            if rescue["selectedPath"] is None
            else ContentAssessmentEngine(engine, rescue["routing"])
        )
    if "rescue" not in bundle:
        return engine
    proof = require_rescue_evidence(bundle)
    return (
        engine
        if proof["selection"]["selectedPath"] is None
        else RescueAssessmentEngine(engine, proof)
    )
